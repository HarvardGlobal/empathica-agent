"""Drug lookup + DailyMed label-context utilities."""

from __future__ import annotations

import logging
from typing import Any, Optional
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

_DAILYMED_BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
_TIMEOUT = 12.0
_LABEL_CACHE: dict[str, dict[str, Any]] = {}


def _clean(value: str) -> str:
    return (value or "").strip()


def _clean_setid(value: str) -> str:
    return _clean(value).lower()


def _http_get_json(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any] | None:
    try:
        r = httpx.get(url, params=params, timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _extract_spl_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("data", "spls", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def _pick_best_item(items: list[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], bool]:
    if not items:
        return None, False

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        title = str(item.get("title", "") or "")
        published = str(item.get("published_date", "") or "")
        score = 1 if "human" in title.lower() else 0
        return (score, published)

    sorted_items = sorted(items, key=sort_key, reverse=True)
    return sorted_items[0], len(items) > 1


def _resolve_from_rxcui(rxcui: str) -> tuple[Optional[dict[str, Any]], Optional[str], bool]:
    payload = _http_get_json(f"{_DAILYMED_BASE}/spls.json", params={"rxcui": rxcui})
    if not payload:
        return None, f"RxCUI {rxcui}: no DailyMed match found.", False
    items = _extract_spl_items(payload)
    best, multiple = _pick_best_item(items)
    if not best:
        return None, f"RxCUI {rxcui}: no DailyMed match found.", False
    setid = best.get("setid") or best.get("set_id")
    if not setid:
        return None, f"RxCUI {rxcui}: DailyMed result had no setid.", False
    return best, None, multiple


def _resolve_from_ndc(ndc: str) -> tuple[Optional[dict[str, Any]], Optional[str], bool]:
    payload = _http_get_json(f"{_DAILYMED_BASE}/spls.json", params={"ndc": ndc})
    if not payload:
        return None, f"NDC {ndc}: could not be reliably resolved with available DailyMed endpoint.", False
    items = _extract_spl_items(payload)
    best, multiple = _pick_best_item(items)
    if not best or not (best.get("setid") or best.get("set_id")):
        return None, f"NDC {ndc}: could not be reliably resolved with available DailyMed endpoint.", False
    return best, None, multiple


def _resolve_from_drug_name(name: str) -> tuple[Optional[dict[str, Any]], Optional[str], bool]:
    payload = _http_get_json(f"{_DAILYMED_BASE}/spls.json", params={"drug_name": name})
    if not payload:
        return None, f"Drug name {name!r}: no reliable DailyMed match found.", False
    items = _extract_spl_items(payload)
    if not items:
        return None, f"Drug name {name!r}: no reliable DailyMed match found.", False

    exact = [i for i in items if str(i.get("title", "")).strip().lower() == name.strip().lower()]
    if len(exact) == 1:
        return exact[0], None, len(items) > 1
    if len(exact) > 1:
        best, multiple = _pick_best_item(exact)
        if best:
            return best, None, multiple
        return None, f"Drug name {name!r}: ambiguous exact matches; provide Set ID or RxCUI.", True

    # If there is no exact title match, prefer a best-effort resolution over failing.
    best, multiple = _pick_best_item(items)
    if best:
        return best, None, multiple
    return None, f"Drug name {name!r}: ambiguous or low-confidence match; provide Set ID or RxCUI.", len(items) > 1


def _find_section_texts(root: ET.Element) -> dict[str, str]:
    sections = root.findall(".//{*}section")
    targets = [
        ("boxed_warning", ["boxed warning"]),
        ("contraindications", ["contraindications", "contraindication"]),
        ("warnings_precautions", ["warnings and precautions", "warnings & precautions", "warnings", "precautions"]),
        ("drug_interactions", ["drug interactions", "interactions"]),
        ("adverse_reactions", ["adverse reactions", "adverse events", "side effects"]),
        ("indications_usage", ["indications and usage", "indications"]),
        ("dosage_administration", ["dosage and administration", "dosage", "administration"]),
        ("use_specific_populations", ["use in specific populations", "specific populations", "pregnancy", "lactation", "pediatric use", "geriatric use"]),
        ("patient_counseling", ["patient counseling information", "information for patients", "patient information", "counseling"]),
    ]

    out: dict[str, str] = {}
    for section in sections:
        title_el = section.find("./{*}title")
        title = ""
        if title_el is not None:
            title = " ".join("".join(title_el.itertext()).split()).strip().lower()
        if not title:
            continue

        text_el = section.find("./{*}text")
        if text_el is None:
            continue
        text = " ".join("".join(text_el.itertext()).split()).strip()
        if not text:
            continue

        for key, patterns in targets:
            if key in out:
                continue
            if any(p in title for p in patterns):
                out[key] = text
                break
    return out


def _fetch_label_context_by_setid(setid: str, title_hint: str | None = None) -> dict[str, Any]:
    setid_clean = _clean_setid(setid)
    if setid_clean in _LABEL_CACHE:
        return _LABEL_CACHE[setid_clean]

    urls = [
        f"{_DAILYMED_BASE}/spls/{setid_clean}.xml",
        f"https://dailymed.nlm.nih.gov/dailymed/downloads/{setid_clean}.xml",
    ]

    xml_text = None
    used_url = ""
    for url in urls:
        try:
            logger.info("dailymed_fetch setid=%s url=%s", setid_clean, url)
            r = httpx.get(url, timeout=_TIMEOUT)
            if r.status_code == 200 and r.text.strip():
                xml_text = r.text
                used_url = url
                break
        except Exception:
            continue

    if not xml_text:
        payload = {
            "ok": False,
            "setid": setid_clean,
            "title": title_hint,
            "context": f"Set ID {setid_clean}: label could not be retrieved.",
            "source_url": "",
            "sections": {},
        }
        _LABEL_CACHE[setid_clean] = payload
        return payload

    try:
        root = ET.fromstring(xml_text)
        sections = _find_section_texts(root)
        if not sections:
            payload = {
                "ok": False,
                "setid": setid_clean,
                "title": title_hint,
                "context": f"Set ID {setid_clean}: label could not be retrieved (no relevant clinical sections found).",
                "source_url": used_url,
                "sections": {},
            }
            _LABEL_CACHE[setid_clean] = payload
            return payload

        pretty = {
            "boxed_warning": "Boxed Warning",
            "contraindications": "Contraindications",
            "warnings_precautions": "Warnings and Precautions",
            "drug_interactions": "Drug Interactions",
            "adverse_reactions": "Adverse Reactions",
            "indications_usage": "Indications and Usage",
            "dosage_administration": "Dosage and Administration",
            "use_specific_populations": "Use in Specific Populations",
            "patient_counseling": "Patient Counseling Information",
        }
        ordered = list(pretty.keys())

        lines = [f"Drug label: {title_hint or 'Unknown title'}", f"Set ID: {setid_clean}"]
        for key in ordered:
            if key in sections:
                lines.append(f"- {pretty[key]}: {sections[key]}")

        payload = {
            "ok": True,
            "setid": setid_clean,
            "title": title_hint,
            "context": "\n".join(lines),
            "source_url": used_url,
            "sections": sections,
        }
        _LABEL_CACHE[setid_clean] = payload
        return payload
    except Exception as exc:
        payload = {
            "ok": False,
            "setid": setid_clean,
            "title": title_hint,
            "context": f"Set ID {setid_clean}: label could not be retrieved ({type(exc).__name__}).",
            "source_url": used_url,
            "sections": {},
        }
        _LABEL_CACHE[setid_clean] = payload
        return payload


def build_dailymed_context(
    drug_set_ids: list[str] | None = None,
    drug_names: list[str] | None = None,
    rxcuis: list[str] | None = None,
    ndcs: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    provided = any([bool(drug_set_ids), bool(drug_names), bool(rxcuis), bool(ndcs)])

    meta: dict[str, Any] = {
        "drug_identifiers_provided": provided,
        "set_ids_resolved": 0,
        "labels_retrieved": 0,
        "labels_failed": 0,
        "unresolved_identifiers": [],
        "retrieved_labels": [],
    }

    if not provided:
        return "No DailyMed drug label context was provided.", meta

    resolved: dict[str, dict[str, Any]] = {}

    for raw in drug_set_ids or []:
        setid = _clean_setid(raw)
        if setid:
            resolved[setid] = {"setid": setid, "title": None, "source": "drug_set_id"}

    for raw in rxcuis or []:
        rxcui = _clean(raw)
        if not rxcui:
            continue
        item, err, multiple = _resolve_from_rxcui(rxcui)
        if err or not item:
            meta["unresolved_identifiers"].append({"type": "rxcui", "value": rxcui, "reason": err})
            continue
        setid = _clean_setid(str(item.get("setid") or item.get("set_id") or ""))
        if not setid:
            meta["unresolved_identifiers"].append({"type": "rxcui", "value": rxcui, "reason": "no setid"})
            continue
        resolved[setid] = {
            "setid": setid,
            "title": item.get("title"),
            "published_date": item.get("published_date"),
            "source": "rxcui",
            "rxcui": rxcui,
            "multiple_matches": multiple,
        }

    for raw in ndcs or []:
        ndc = _clean(raw)
        if not ndc:
            continue
        item, err, multiple = _resolve_from_ndc(ndc)
        if err or not item:
            meta["unresolved_identifiers"].append({"type": "ndc", "value": ndc, "reason": err})
            continue
        setid = _clean_setid(str(item.get("setid") or item.get("set_id") or ""))
        if not setid:
            meta["unresolved_identifiers"].append({"type": "ndc", "value": ndc, "reason": "no setid"})
            continue
        resolved[setid] = {
            "setid": setid,
            "title": item.get("title"),
            "published_date": item.get("published_date"),
            "source": "ndc",
            "ndc": ndc,
            "multiple_matches": multiple,
        }

    for raw in drug_names or []:
        name = _clean(raw)
        if not name:
            continue
        item, err, multiple = _resolve_from_drug_name(name)
        if err or not item:
            meta["unresolved_identifiers"].append({"type": "drug_name", "value": name, "reason": err})
            continue
        setid = _clean_setid(str(item.get("setid") or item.get("set_id") or ""))
        if not setid:
            meta["unresolved_identifiers"].append({"type": "drug_name", "value": name, "reason": "no setid"})
            continue
        resolved[setid] = {
            "setid": setid,
            "title": item.get("title"),
            "published_date": item.get("published_date"),
            "source": "drug_name",
            "drug_name": name,
            "multiple_matches": multiple,
        }

    meta["set_ids_resolved"] = len(resolved)

    if not resolved:
        return "No DailyMed drug label context was provided.", meta

    contexts = []
    for setid, info in resolved.items():
        fetched = _fetch_label_context_by_setid(setid, title_hint=info.get("title"))
        contexts.append(fetched["context"])
        if fetched["ok"]:
            meta["labels_retrieved"] += 1
            meta["retrieved_labels"].append(
                {
                    "setid": fetched["setid"],
                    "title": fetched.get("title"),
                    "published_date": info.get("published_date"),
                    "source": info.get("source"),
                    "multiple_matches": info.get("multiple_matches", False),
                    "source_url": fetched.get("source_url", ""),
                    "sections": fetched.get("sections", {}),
                }
            )
        else:
            meta["labels_failed"] += 1

    if meta["labels_retrieved"] == 0:
        return "No DailyMed drug label context was provided.\n" + "\n\n".join(contexts), meta

    return "\n\n".join(contexts), meta


def drug_lookup(drug_name: str) -> dict:
    query = _clean(drug_name)
    if not query:
        return {
            "status": "error",
            "drug_name": drug_name,
            "message": "Drug name is required.",
        }

    item, err, multiple = _resolve_from_drug_name(query)
    if err or not item:
        return {
            "status": "error",
            "drug_name": query,
            "message": err or f"No reliable DailyMed match found for {query!r}.",
        }

    setid = _clean_setid(str(item.get("setid") or item.get("set_id") or ""))
    if not setid:
        return {
            "status": "error",
            "drug_name": query,
            "message": f"DailyMed lookup for {query!r} returned no setid.",
        }

    label = _fetch_label_context_by_setid(setid, title_hint=item.get("title"))
    if not label.get("ok"):
        return {
            "status": "error",
            "drug_name": query,
            "setid": setid,
            "title": item.get("title"),
            "message": label.get("context")
            or f"DailyMed label retrieval failed for setid {setid}.",
        }

    return {
        "status": "ok",
        "drug_name": query,
        "setid": setid,
        "title": item.get("title"),
        "published_date": item.get("published_date"),
        "multiple_matches": multiple,
        "label_context": label.get("context", ""),
    }
