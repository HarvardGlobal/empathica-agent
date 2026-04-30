from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DailyMedClient:
    """HTTP client for the DailyMed SPL REST API v2."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=30.0)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        response = self._client.get(url, params=params or {})
        response.raise_for_status()
        return response.json()

    def fetch_label_by_setid(self, set_id: str) -> dict[str, Any]:
        """Fetch a single SPL label by its set ID.  GET /spls/{set_id}.json"""
        return self._get(f"/spls/{set_id}.json")

    def fetch_recent_labels(self, days_back: int = 7) -> list[dict[str, Any]]:
        """
        Fetch labels updated within the last `days_back` days.
        Uses date_from / date_to query params (YYYY-MM-DD format).
        """
        today = date.today()
        date_from = (today - timedelta(days=days_back)).isoformat()
        date_to = today.isoformat()

        results: list[dict[str, Any]] = []
        offset = 0
        limit = 100

        while True:
            try:
                response = self._get(
                    "/spls.json",
                    params={
                        "date_from": date_from,
                        "date_to": date_to,
                        "limit": limit,
                        "offset": offset,
                    },
                )
            except httpx.HTTPError as exc:
                logger.error("DailyMed fetch_recent_labels failed at offset %d: %s", offset, exc)
                break

            data = response.get("data", [])
            if not data:
                break

            results.extend(data)
            metadata = response.get("metadata", {})
            total = metadata.get("total_elements", len(results))
            offset += limit
            if offset >= total:
                break

        return results

    def fetch_full_export_index(self) -> list[dict[str, Any]]:
        """
        Fetch the full SPL index via paginated requests.
        GET /spls.json with limit/offset pagination.
        """
        results: list[dict[str, Any]] = []
        offset = 0
        limit = 100

        while True:
            try:
                response = self._get(
                    "/spls.json",
                    params={"limit": limit, "offset": offset},
                )
            except httpx.HTTPError as exc:
                logger.error("DailyMed fetch_full_export_index failed at offset %d: %s", offset, exc)
                break

            data = response.get("data", [])
            if not data:
                break

            results.extend(data)
            metadata = response.get("metadata", {})
            total = metadata.get("total_elements", len(results))
            offset += limit
            if offset >= total:
                break

        return results

    def fetch_spls_page(self, page: int = 1, pagesize: int = 100) -> dict[str, Any]:
        """
        Fetch one page from the SPL index endpoint.

        Returns the raw response with:
          - data: list[dict]
          - metadata: paging info including total_pages / current_page
        """
        return self._get(
            "/spls.json",
            params={"page": page, "pagesize": pagesize},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DailyMedClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
