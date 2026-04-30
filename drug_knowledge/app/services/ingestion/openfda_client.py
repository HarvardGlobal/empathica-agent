from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class OpenFDAClient:
    """HTTP client for the openFDA drug label API."""

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=30.0)

    def _build_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self._api_key:
            params["api_key"] = self._api_key
        if extra:
            params.update(extra)
        return params

    def _get(self, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        try:
            response = self._client.get(self._base_url, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.error("OpenFDA request failed: %s", exc)
            raise

    def fetch_label_by_generic_name(self, name: str) -> Optional[dict[str, Any]]:
        """
        Fetch a drug label record by generic name from openFDA.
        Returns None on 404 or if no results found.
        """
        params = self._build_params(
            {
                "search": f'openfda.generic_name:"{name}"',
                "limit": 1,
            }
        )
        result = self._get(params)
        if result is None:
            return None
        results_list = result.get("results", [])
        if not results_list:
            return None
        return results_list[0]

    def fetch_label_by_setid(self, set_id: str) -> Optional[dict[str, Any]]:
        """
        Fetch a drug label by SPL set ID from openFDA.
        Returns None on 404.
        """
        params = self._build_params(
            {
                "search": f'openfda.spl_set_id:"{set_id}"',
                "limit": 1,
            }
        )
        result = self._get(params)
        if result is None:
            return None
        results_list = result.get("results", [])
        if not results_list:
            return None
        return results_list[0]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenFDAClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
