from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.drug import IngestionRun
from app.services.ingestion.dailymed_client import DailyMedClient
from app.services.ingestion.loader import DBLoader
from app.services.ingestion.normalizer import LabelNormalizer
from app.services.ingestion.openfda_client import OpenFDAClient
from app.services.ingestion.parser import LabelParser
from app.services.utils.text import chunk_label_section

logger = logging.getLogger(__name__)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class IngestionUpdater:
    """
    Orchestrates full and incremental ETL runs from DailyMed and openFDA
    into the local database.
    """

    def __init__(
        self,
        db: Session,
        dailymed_client: DailyMedClient,
        openfda_client: OpenFDAClient,
        parser: LabelParser,
        normalizer: LabelNormalizer,
        loader: DBLoader,
    ) -> None:
        self._db = db
        self._dailymed = dailymed_client
        self._openfda = openfda_client
        self._parser = parser
        self._normalizer = normalizer
        self._loader = loader

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def run_full_ingest(self, limit: int = 100) -> IngestionRun:
        """
        Orchestrate a full ETL run:
        1. Fetch the DailyMed full export index (paginated).
        2. For each record up to `limit`, fetch and parse the full label.
        3. Optionally supplement with openFDA data.
        4. Normalize, load sections, and create chunks.
        5. Create and return an IngestionRun record.
        """
        run = self._create_run(source_name="dailymed", run_type="full")

        try:
            index_records = self._dailymed.fetch_full_export_index()
        except Exception as exc:
            logger.error("Failed to fetch DailyMed index: %s", exc)
            run.status = "failed"
            run.notes = f"Index fetch failed: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            self._db.commit()
            return run

        records_to_process = index_records[:limit]
        run.records_seen = len(records_to_process)

        for record in records_to_process:
            set_id = record.get("set_id", record.get("setid", ""))
            if not set_id:
                run.records_failed += 1
                continue
            try:
                self._process_dailymed_record(record, run)
            except Exception as exc:
                logger.error("Failed to process set_id=%s: %s", set_id, exc)
                run.records_failed += 1

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        self._db.commit()
        return run

    def run_incremental_update(self, days_back: int = 7) -> IngestionRun:
        """
        Orchestrate an incremental update:
        Fetch labels updated in the last `days_back` days and upsert them.
        """
        run = self._create_run(source_name="dailymed", run_type="incremental")

        try:
            recent_records = self._dailymed.fetch_recent_labels(days_back=days_back)
        except Exception as exc:
            logger.error("Failed to fetch recent DailyMed labels: %s", exc)
            run.status = "failed"
            run.notes = f"Recent fetch failed: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            self._db.commit()
            return run

        run.records_seen = len(recent_records)

        for record in recent_records:
            set_id = record.get("set_id", record.get("setid", ""))
            if not set_id:
                run.records_failed += 1
                continue
            try:
                self._process_dailymed_record(record, run)
            except Exception as exc:
                logger.error("Failed to process set_id=%s: %s", set_id, exc)
                run.records_failed += 1

        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        self._db.commit()
        return run

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_run(self, source_name: str, run_type: str) -> IngestionRun:
        run = IngestionRun(
            id=_new_uuid(),
            source_name=source_name,
            run_type=run_type,
            status="running",
            records_seen=0,
            records_inserted=0,
            records_updated=0,
            records_failed=0,
        )
        self._db.add(run)
        self._db.flush()
        return run

    def _process_dailymed_record(self, record: dict, run: IngestionRun) -> None:
        """
        Fetch, parse, normalize and load a single DailyMed label record.
        Updates the IngestionRun counters in-place.
        Per-record failures are logged and counted; they do not halt the run.
        """
        set_id = record.get("set_id", record.get("setid", ""))

        # DailyMed's individual label endpoint (/spls/{set_id}.json) returns XML (415).
        # Use openFDA as primary source for the full structured label JSON.
        raw: dict | None = None
        try:
            raw = self._openfda.fetch_label_by_setid(set_id)
        except Exception as exc:
            logger.warning("openFDA fetch failed for set_id=%s: %s", set_id, exc)

        if not raw:
            # Fall back to the index record (title/setid only) so at least the drug row is created
            raw = record

        # Choose parser based on the source of the raw data
        source_system = raw.get("source_system", "")
        if "openfda" in source_system or "openfda" in raw.get("set_id", "") or raw.get("openfda"):
            parsed = self._parser.parse_openfda_label(raw)
        else:
            parsed = self._parser.parse_dailymed_label(raw)
        normalized = self._normalizer.normalize(parsed)

        # Track insert vs update before upserting
        from app.models.drug import Drug as DrugModel

        existing = (
            self._db.query(DrugModel)
            .filter(DrugModel.source_set_id == normalized.set_id)
            .first()
        )
        is_new = existing is None

        drug = self._loader.upsert_drug(normalized)
        self._loader.upsert_structured_facts(drug, normalized)
        sections = self._loader.upsert_label_sections(drug, normalized.sections)

        for section in sections:
            if section.section_text:
                chunks_text = chunk_label_section(section.section_text, section.section_type)
                self._loader.upsert_chunks(drug, section, chunks_text)

        if is_new:
            run.records_inserted += 1
        else:
            run.records_updated += 1
