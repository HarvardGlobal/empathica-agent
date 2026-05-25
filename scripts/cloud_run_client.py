#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx
import google.auth.transport.requests
from google.oauth2 import id_token


def _fetch_id_token(audience: str) -> str:
    req = google.auth.transport.requests.Request()
    return id_token.fetch_id_token(req, audience)


def _headers(service_url: str) -> dict[str, str]:
    token = _fetch_id_token(service_url)
    return {"Authorization": f"Bearer {token}"}


def cmd_health(args: argparse.Namespace) -> int:
    url = f"{args.service_url.rstrip('/')}/healthz"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=_headers(args.service_url))
    print(resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    return 0 if resp.status_code < 400 else 1


def cmd_chat(args: argparse.Namespace) -> int:
    url = f"{args.service_url.rstrip('/')}/chat"
    payload: dict[str, Any] = {
        "user_id": args.user_id,
        "message": args.message,
        "literacy_level": args.literacy_level,
        "empathy_level": args.empathy_level,
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers={**_headers(args.service_url), "Content-Type": "application/json"}, json=payload)
    print(resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    return 0 if resp.status_code < 400 else 1


def cmd_onboard(args: argparse.Namespace) -> int:
    fhir_path = Path(args.structured_fhir_file)
    doc_path = Path(args.unstructured_file)
    if not fhir_path.exists():
        raise SystemExit(f"FHIR file not found: {fhir_path}")
    if not doc_path.exists():
        raise SystemExit(f"Unstructured file not found: {doc_path}")

    url = f"{args.service_url.rstrip('/')}/onboarding/upload"
    data: dict[str, str] = {
        "user_id": args.user_id,
        "tenant": args.tenant,
        "status": args.status,
    }
    if args.target_document_types:
        data["target_document_types"] = args.target_document_types

    with httpx.Client(timeout=120.0) as client:
        with fhir_path.open("rb") as fhir_fp, doc_path.open("rb") as doc_fp:
            files = {
                "structured_fhir_file": (fhir_path.name, fhir_fp, "application/json"),
                "unstructured_file": (doc_path.name, doc_fp, "text/markdown"),
            }
            resp = client.post(url, headers=_headers(args.service_url), data=data, files=files)
    print(resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)
    return 0 if resp.status_code < 400 else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Authenticated client for empathica-agents Cloud Run API")
    p.add_argument("--service-url", required=True, help="Cloud Run service URL, e.g. https://...run.app")
    sub = p.add_subparsers(dest="command", required=True)

    h = sub.add_parser("health", help="Call /healthz")
    h.set_defaults(func=cmd_health)

    c = sub.add_parser("chat", help="Call /chat")
    c.add_argument("--user-id", required=True)
    c.add_argument("--message", required=True)
    c.add_argument("--literacy-level", default="medium", choices=["low", "medium", "high"])
    c.add_argument("--empathy-level", default="medium", choices=["low", "medium", "high"])
    c.set_defaults(func=cmd_chat)

    o = sub.add_parser("onboard", help="Call /onboarding/upload")
    o.add_argument("--user-id", required=True)
    o.add_argument("--structured-fhir-file", required=True)
    o.add_argument("--unstructured-file", required=True)
    o.add_argument("--tenant", default="default")
    o.add_argument("--status", default="active")
    o.add_argument(
        "--target-document-types",
        default="",
        help="Optional comma-separated typed-folder hints, e.g. medication_management,oncology_notes",
    )
    o.set_defaults(func=cmd_onboard)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

