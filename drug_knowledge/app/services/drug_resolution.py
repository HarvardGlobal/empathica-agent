from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.drug import Drug
from app.schemas.drug import DrugResolutionResult
from app.services.utils.matching import fuzzy_score, normalize_drug_name


class DrugResolutionService:
    """Resolves free-text drug names to canonical Drug records in the database."""

    FUZZY_THRESHOLD = 0.8
    AMBIGUITY_MAX_CANDIDATES = 5

    def __init__(self, db: Session) -> None:
        self._db = db

    def resolve_drug(self, query_name: str) -> DrugResolutionResult:
        """
        Attempt to resolve a drug name string to a canonical Drug record.

        Resolution order:
        1. Exact match on normalized_generic_name
        2. Exact match inside brand_names JSON array
        3. Alias/substring match (query is a substring of any drug name)
        4. Fuzzy match with threshold 0.8
        5. Return candidates if ambiguous, never silently guess
        """
        if not query_name or not query_name.strip():
            return DrugResolutionResult(
                matched=False,
                match_type="none",
                confidence=0.0,
                candidate_names=[],
            )

        normalized_query = normalize_drug_name(query_name)

        # 1. Exact match on normalized_generic_name
        drug = (
            self._db.query(Drug)
            .filter(Drug.normalized_generic_name == normalized_query)
            .first()
        )
        if drug is not None:
            return DrugResolutionResult(
                matched=True,
                drug_id=drug.id,
                matched_name=drug.generic_name,
                match_type="exact_generic",
                confidence=1.0,
                candidate_names=[drug.generic_name],
            )

        # 2. Exact match inside brand_names JSON array
        all_drugs = self._db.query(Drug).all()
        for drug in all_drugs:
            brand_names: list[str] = drug.brand_names or []
            normalized_brands = [normalize_drug_name(b) for b in brand_names]
            if normalized_query in normalized_brands:
                matched_brand = brand_names[normalized_brands.index(normalized_query)]
                return DrugResolutionResult(
                    matched=True,
                    drug_id=drug.id,
                    matched_name=matched_brand,
                    match_type="exact_brand",
                    confidence=1.0,
                    candidate_names=[matched_brand],
                )

        # 3. Alias / substring match
        alias_matches: list[tuple[Drug, str]] = []
        for drug in all_drugs:
            # Query appears as substring in generic name
            if normalized_query in drug.normalized_generic_name:
                alias_matches.append((drug, drug.generic_name))
                continue
            # Any brand name contains the query as substring
            for brand in drug.brand_names or []:
                if normalized_query in normalize_drug_name(brand):
                    alias_matches.append((drug, brand))
                    break

        if len(alias_matches) == 1:
            drug, name = alias_matches[0]
            return DrugResolutionResult(
                matched=True,
                drug_id=drug.id,
                matched_name=name,
                match_type="alias",
                confidence=0.9,
                candidate_names=[name],
            )
        elif len(alias_matches) > 1:
            # Ambiguous — return candidates rather than guess
            candidates = [name for _, name in alias_matches[: self.AMBIGUITY_MAX_CANDIDATES]]
            return DrugResolutionResult(
                matched=False,
                match_type="alias",
                confidence=0.5,
                candidate_names=candidates,
            )

        # 4. Fuzzy match
        scored: list[tuple[Drug, str, float]] = []
        for drug in all_drugs:
            names_to_check = [drug.normalized_generic_name] + [
                normalize_drug_name(b) for b in (drug.brand_names or [])
            ]
            best_score = max(fuzzy_score(normalized_query, n) for n in names_to_check)
            if best_score >= self.FUZZY_THRESHOLD:
                scored.append((drug, drug.generic_name, best_score))

        if len(scored) == 1:
            drug, name, score = scored[0]
            return DrugResolutionResult(
                matched=True,
                drug_id=drug.id,
                matched_name=name,
                match_type="fuzzy",
                confidence=round(score, 4),
                candidate_names=[name],
            )
        elif len(scored) > 1:
            # Multiple fuzzy hits — return candidates
            scored.sort(key=lambda x: x[2], reverse=True)
            candidates = [name for _, name, _ in scored[: self.AMBIGUITY_MAX_CANDIDATES]]
            best_score = scored[0][2]
            return DrugResolutionResult(
                matched=False,
                match_type="fuzzy",
                confidence=round(best_score, 4),
                candidate_names=candidates,
            )

        # 5. No match
        return DrugResolutionResult(
            matched=False,
            match_type="none",
            confidence=0.0,
            candidate_names=[],
        )

    def resolve_multiple_drugs(self, names: list[str]) -> list[DrugResolutionResult]:
        """Resolve a list of drug name strings, returning one result per name."""
        return [self.resolve_drug(name) for name in names]
