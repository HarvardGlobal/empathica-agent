#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.db import SessionLocal, init_db
from app.models.drug import Drug
from app.services.ingestion.dailymed_client import DailyMedClient
from app.services.ingestion.loader import DBLoader
from app.services.ingestion.normalizer import LabelNormalizer
from app.services.ingestion.openfda_client import OpenFDAClient
from app.services.ingestion.parser import LabelParser
from app.services.ingestion.updater import IngestionUpdater

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingest_all_drugs")

CHECKPOINT_PATH = Path(".ingest_checkpoint.json")
PAGESIZE = 100
PROGRESS_EVERY = 20


class _RunShim:
    def __init__(self) -> None:
        self.records_inserted = 0
        self.records_updated = 0
        self.records_failed = 0


def load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text())
    return {"page": 1, "processed": 0, "inserted": 0, "updated": 0, "failed": 0}


def save_checkpoint(state: dict) -> None:
    CHECKPOINT_PATH.write_text(json.dumps(state, indent=2))


def main() -> None:
    logger.info("Starting full ingest across all DailyMed SPL pages")
    init_db()

    state = load_checkpoint()
    page = int(state.get("page", 1))
    processed = int(state.get("processed", 0))
    inserted = int(state.get("inserted", 0))
    updated = int(state.get("updated", 0))
    failed = int(state.get("failed", 0))

    db = SessionLocal()
    dailymed = DailyMedClient(settings.DAILYMED_BASE_URL)
    openfda = OpenFDAClient(settings.OPENFDA_BASE_URL, settings.OPENFDA_API_KEY)
    updater = IngestionUpdater(
        db=db,
        dailymed_client=dailymed,
        openfda_client=openfda,
        parser=LabelParser(),
        normalizer=LabelNormalizer(),
        loader=DBLoader(db),
    )

    try:
        first_page = dailymed.fetch_spls_page(page=1, pagesize=1)
        total_pages = int(first_page.get("metadata", {}).get("total_pages", 1))
        total_elements = int(first_page.get("metadata", {}).get("total_elements", 0))
        logger.info("DailyMed reports total_elements=%d total_pages=%d", total_elements, total_pages)

        run_shim = _RunShim()

        while page <= total_pages:
            logger.info("processing page=%d/%d", page, total_pages)
            resp = dailymed.fetch_spls_page(page=page, pagesize=PAGESIZE)
            rows = resp.get("data", []) or []
            if not rows:
                logger.info("No rows at page=%d; finishing", page)
                break

            for row in rows:
                set_id = row.get("setid") or row.get("set_id")
                existing = db.query(Drug).filter(Drug.source_set_id == set_id).first()
                try:
                    updater._process_dailymed_record(row, run=run_shim)
                    processed += 1
                    if existing is None:
                        inserted += 1
                    else:
                        updated += 1
                except Exception as exc:
                    processed += 1
                    failed += 1
                    logger.warning("record failed set_id=%s err=%s", set_id, exc)

                if processed % PROGRESS_EVERY == 0:
                    db.commit()
                    state.update(
                        {
                            "page": page,
                            "processed": processed,
                            "inserted": inserted,
                            "updated": updated,
                            "failed": failed,
                            "total_pages": total_pages,
                            "total_elements": total_elements,
                            "last_update_ts": time.time(),
                        }
                    )
                    save_checkpoint(state)
                    logger.info(
                        "progress processed=%d/%d inserted=%d updated=%d failed=%d page=%d/%d",
                        processed,
                        total_elements,
                        inserted,
                        updated,
                        failed,
                        page,
                        total_pages,
                    )

            db.commit()
            page += 1
            state.update(
                {
                    "page": page,
                    "processed": processed,
                    "inserted": inserted,
                    "updated": updated,
                    "failed": failed,
                    "total_pages": total_pages,
                    "total_elements": total_elements,
                    "last_update_ts": time.time(),
                }
            )
            save_checkpoint(state)

        db.commit()
        logger.info(
            "DONE processed=%d inserted=%d updated=%d failed=%d",
            processed,
            inserted,
            updated,
            failed,
        )
    finally:
        dailymed.close()
        openfda.close()
        db.close()


if __name__ == "__main__":
    main()
