from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.drug import Drug, DrugLabelChunk, DrugLabelSection, DrugStructuredFacts
from app.services.ingestion.normalizer import NormalizedLabel
from app.services.utils.text import chunk_label_section, estimate_token_count


@dataclass
class LoadResult:
    drugs_inserted: int = 0
    drugs_updated: int = 0
    sections_inserted: int = 0
    sections_updated: int = 0
    chunks_inserted: int = 0
    chunks_updated: int = 0
    errors: list[str] = field(default_factory=list)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class DBLoader:
    """Idempotent loader that upserts normalized label data into the database."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert_drug(self, normalized: NormalizedLabel) -> Drug:
        """
        Upsert a Drug record identified by source_set_id.
        If the record exists, update all fields. Otherwise insert.
        """
        drug = (
            self._db.query(Drug)
            .filter(Drug.source_set_id == normalized.set_id)
            .first()
        )

        if drug is None:
            drug = Drug(
                id=_new_uuid(),
                generic_name=normalized.generic_name,
                normalized_generic_name=normalized.normalized_generic_name,
                brand_names=normalized.brand_names,
                manufacturer_name=normalized.manufacturer or None,
                labeler_name=normalized.labeler or None,
                active_ingredients=normalized.active_ingredients,
                drug_classes=normalized.drug_classes,
                dosage_forms=normalized.dosage_forms,
                routes=normalized.routes,
                source_set_id=normalized.set_id,
                source_spl_id=normalized.spl_id or None,
                source_system=normalized.source_system or None,
                source_url=normalized.source_url or None,
            )
            self._db.add(drug)
        else:
            drug.generic_name = normalized.generic_name
            drug.normalized_generic_name = normalized.normalized_generic_name
            drug.brand_names = normalized.brand_names
            drug.manufacturer_name = normalized.manufacturer or None
            drug.labeler_name = normalized.labeler or None
            drug.active_ingredients = normalized.active_ingredients
            drug.drug_classes = normalized.drug_classes
            drug.dosage_forms = normalized.dosage_forms
            drug.routes = normalized.routes
            drug.source_spl_id = normalized.spl_id or None
            drug.source_system = normalized.source_system or None
            drug.source_url = normalized.source_url or None

        self._db.flush()
        return drug

    def upsert_structured_facts(
        self, drug: Drug, normalized: NormalizedLabel
    ) -> DrugStructuredFacts:
        """
        Upsert the DrugStructuredFacts record for a drug.
        """
        facts = (
            self._db.query(DrugStructuredFacts)
            .filter(DrugStructuredFacts.drug_id == drug.id)
            .first()
        )

        boxed_section = normalized.sections.get("boxed_warning", "")
        boxed_summary = boxed_section[:500] if boxed_section else None

        contraindication_text = normalized.sections.get("contraindications", "")
        contraindication_summary = contraindication_text[:1000] if contraindication_text else None

        warnings_text = normalized.sections.get("warnings_and_precautions", "")
        warnings_summary = warnings_text[:1000] if warnings_text else None

        pop_text = normalized.sections.get("use_in_specific_populations", "")
        pregnancy_summary = _extract_subsection(pop_text, ["pregnancy"])
        breastfeeding_summary = _extract_subsection(pop_text, ["lactation", "breastfeeding", "breast-feeding"])
        renal_summary = _extract_subsection(pop_text, ["renal", "kidney"])
        hepatic_summary = _extract_subsection(pop_text, ["hepatic", "liver"])

        if facts is None:
            facts = DrugStructuredFacts(
                id=_new_uuid(),
                drug_id=drug.id,
                plain_language_purpose=normalized.plain_language_purpose or None,
                moderate_purpose=normalized.plain_language_purpose or None,
                technical_purpose=normalized.sections.get("indications_and_usage", "") or None,
                common_indications=[],
                common_side_effects=normalized.common_side_effects,
                serious_side_effects=[],
                boxed_warning_flag=normalized.boxed_warning_flag,
                boxed_warning_summary=boxed_summary,
                contraindication_summary=contraindication_summary,
                warnings_precautions_summary=warnings_summary,
                pregnancy_summary=pregnancy_summary,
                breastfeeding_summary=breastfeeding_summary,
                renal_summary=renal_summary,
                hepatic_summary=hepatic_summary,
                alcohol_summary=None,
                food_interaction_summary=None,
                monitoring_summary=None,
            )
            self._db.add(facts)
        else:
            facts.plain_language_purpose = normalized.plain_language_purpose or None
            facts.moderate_purpose = normalized.plain_language_purpose or None
            facts.technical_purpose = normalized.sections.get("indications_and_usage", "") or None
            facts.common_side_effects = normalized.common_side_effects
            facts.boxed_warning_flag = normalized.boxed_warning_flag
            facts.boxed_warning_summary = boxed_summary
            facts.contraindication_summary = contraindication_summary
            facts.warnings_precautions_summary = warnings_summary
            facts.pregnancy_summary = pregnancy_summary
            facts.breastfeeding_summary = breastfeeding_summary
            facts.renal_summary = renal_summary
            facts.hepatic_summary = hepatic_summary

        self._db.flush()
        return facts

    def upsert_label_sections(
        self, drug: Drug, sections: dict[str, str]
    ) -> list[DrugLabelSection]:
        """
        Upsert label sections for a drug.
        One section per section_type; updates text if already present.
        """
        existing: dict[str, DrugLabelSection] = {
            s.section_type: s
            for s in self._db.query(DrugLabelSection)
            .filter(DrugLabelSection.drug_id == drug.id)
            .all()
        }

        result: list[DrugLabelSection] = []
        for rank, (section_type, text) in enumerate(sections.items()):
            if not text or not text.strip():
                continue

            if section_type in existing:
                sec = existing[section_type]
                sec.section_text = text
                sec.section_rank = rank
                sec.source_url = drug.source_url
                sec.source_set_id = drug.source_set_id
                sec.source_system = drug.source_system
            else:
                sec = DrugLabelSection(
                    id=_new_uuid(),
                    drug_id=drug.id,
                    section_type=section_type,
                    section_title=section_type.replace("_", " ").title(),
                    section_text=text,
                    source_url=drug.source_url,
                    source_set_id=drug.source_set_id,
                    source_system=drug.source_system,
                    section_rank=rank,
                )
                self._db.add(sec)

            result.append(sec)

        self._db.flush()
        return result

    def upsert_chunks(
        self,
        drug: Drug,
        section: DrugLabelSection,
        chunks: list[str],
    ) -> list[DrugLabelChunk]:
        """
        Upsert label chunks for a section. Replaces all chunks for that section.
        """
        # Delete existing chunks for this section
        self._db.query(DrugLabelChunk).filter(
            DrugLabelChunk.section_id == section.id
        ).delete()

        result: list[DrugLabelChunk] = []
        for idx, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue
            chunk = DrugLabelChunk(
                id=_new_uuid(),
                drug_id=drug.id,
                section_id=section.id,
                section_type=section.section_type,
                chunk_index=idx,
                chunk_text=chunk_text,
                token_count_estimate=estimate_token_count(chunk_text),
                embedding_model=None,
                source_url=drug.source_url,
            )
            self._db.add(chunk)
            result.append(chunk)

        self._db.flush()
        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_subsection(text: str, keywords: list[str]) -> str | None:
    """Extract a sentence or paragraph from text that contains any of the keywords."""
    if not text:
        return None
    lower_text = text.lower()
    for keyword in keywords:
        idx = lower_text.find(keyword.lower())
        if idx != -1:
            # Take the surrounding sentence (up to 500 chars)
            start = max(0, idx - 50)
            end = min(len(text), idx + 450)
            return text[start:end].strip()
    return None
