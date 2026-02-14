#!/usr/bin/env python3
"""Generate automatic firm overrides from raw HTML evidence.

Outputs: /opt/gpti/gpti-site/data/firm-overrides.auto.json
Manual overrides remain in firm-overrides.json and take precedence.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
from datetime import datetime, timezone
import time
from pathlib import Path
from typing import Any

import psycopg
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

from gpti_bot.agents.rules_extractor import extract_rules_multi_pass
from gpti_bot.minio import client as minio_client

AUTO_OUTPUT = "/opt/gpti/gpti-site/data/firm-overrides.auto.json"
DEFAULT_ENV = "/opt/gpti/docker/.env"
MAX_HTML_BYTES = int(os.getenv("GPTI_OVERRIDE_MAX_HTML_BYTES", "2000000"))
MAX_PDF_BYTES = int(os.getenv("GPTI_OVERRIDE_MAX_PDF_BYTES", "5000000"))
MAX_PDF_CHARS = int(os.getenv("GPTI_OVERRIDE_MAX_PDF_CHARS", "40000"))
ENABLE_OCR = os.getenv("GPTI_OVERRIDE_ENABLE_OCR", "0") == "1"
MAX_OCR_PAGES = int(os.getenv("GPTI_OVERRIDE_MAX_OCR_PAGES", "3"))
MAX_FIRMS = int(os.getenv("GPTI_OVERRIDE_LIMIT", "50"))
MAX_SCAN = int(os.getenv("GPTI_OVERRIDE_SCAN_LIMIT", "500"))
LOG_EVERY = int(os.getenv("GPTI_OVERRIDE_LOG_EVERY", "25"))
MAX_FIRM_SECONDS = float(os.getenv("GPTI_OVERRIDE_FIRM_SECONDS", "6"))
MAX_EVIDENCE_PER_KEY = int(os.getenv("GPTI_OVERRIDE_EVIDENCE_PER_KEY", "3"))
USE_WIKI = os.getenv("GPTI_OVERRIDE_USE_WIKI", "0") == "1"
WIKI_TIMEOUT = int(os.getenv("GPTI_OVERRIDE_WIKI_TIMEOUT", "8"))
USE_OPENCORPORATES = os.getenv("GPTI_OVERRIDE_USE_OPENCORPORATES", "0") == "1"
OPENCORPORATES_TIMEOUT = int(os.getenv("GPTI_OVERRIDE_OC_TIMEOUT", "10"))

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
USE_LLM = os.getenv("GPTI_OVERRIDE_USE_LLM", "0") == "1"
LLM_MODEL = os.getenv("GPTI_OVERRIDE_LLM_MODEL") or os.getenv("GPTI_RULES_MODEL")
USE_PLAYWRIGHT = os.getenv("GPTI_OVERRIDE_USE_PLAYWRIGHT", "0") == "1"
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("GPTI_OVERRIDE_PLAYWRIGHT_TIMEOUT_MS", "15000"))


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _load_env_file(path: str) -> dict[str, str]:
    data: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return data
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def _database_url() -> str:
    url = _env("DATABASE_URL")
    if url:
        return url
    env = _load_env_file(DEFAULT_ENV)
    return "postgresql://{user}:{pwd}@localhost:5434/{db}".format(
        user=env.get("POSTGRES_USER"),
        pwd=env.get("POSTGRES_PASSWORD"),
        db=env.get("POSTGRES_DB"),
    )


def _html_to_text(html_bytes: bytes, max_chars: int = 20000) -> str:
    html_bytes = html_bytes[:MAX_HTML_BYTES]
    try:
        soup = BeautifulSoup(html_bytes.decode("utf-8", errors="ignore"), "html.parser")
    except Exception:
        soup = BeautifulSoup(html_bytes.decode("utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        try:
            tag.decompose()
        except Exception:
            pass
    return (soup.get_text(" ", strip=True) or "")[:max_chars]


def _get_bytes_limited(m, bucket: str, obj: str, max_bytes: int) -> bytes:
    response = m.get_object(bucket, obj)
    try:
        return response.read(max_bytes)
    finally:
        response.close()
        response.release_conn()


def _pdf_to_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages[:10]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = " ".join(parts).strip()
    if len(text) > MAX_PDF_CHARS:
        text = text[:MAX_PDF_CHARS]
    return text


def _pdf_to_text_ocr(pdf_bytes: bytes) -> str:
    if not ENABLE_OCR:
        return ""
    try:
        import fitz  # pymupdf
        import pytesseract
        from PIL import Image
    except Exception:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return ""
    parts: list[str] = []
    for page_index in range(min(MAX_OCR_PAGES, doc.page_count)):
        try:
            page = doc.load_page(page_index)
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
            if text:
                parts.append(text)
        except Exception:
            continue
    doc.close()
    text = " ".join(parts).strip()
    if len(text) > MAX_PDF_CHARS:
        text = text[:MAX_PDF_CHARS]
    return text


def _render_html_playwright(url: str) -> str:
    if not USE_PLAYWRIGHT:
        return ""
    node_script = f"""
const {{ chromium }} = require('playwright');
(async()=>{{
  const browser = await chromium.launch({{ headless: true }});
  const page = await browser.newPage();
  await page.goto({json.dumps(url)}, {{ waitUntil: 'networkidle', timeout: {PLAYWRIGHT_TIMEOUT_MS} }});
  const content = await page.content();
  await browser.close();
  console.log(content);
}})().catch(err=>{{
  console.error('playwright-error', err.message || String(err));
  process.exit(1);
}});
"""
    try:
        proc = subprocess.run(
            ["node", "-e", node_script],
            check=False,
            capture_output=True,
            text=True,
            cwd="/opt/gpti/gpti-site",
            env={
                **os.environ,
                "NODE_PATH": "/opt/gpti/gpti-site/node_modules",
            },
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _regex_pick_frequency(text: str) -> str | None:
    lowered = text.lower()
    if "payout" not in lowered and "withdraw" not in lowered:
        return None
    for token in (
        "on demand",
        "on-demand",
        "daily",
        "weekly",
        "biweekly",
        "bi-weekly",
        "monthly",
        "quarterly",
        "annually",
        "yearly",
    ):
        if token in lowered:
            return token.replace("-", "_").replace(" ", "_")
    match = re.search(r"payout[^\n]{0,40}(\d{1,2})\s*days", lowered)
    if match:
        try:
            days = int(match.group(1))
        except ValueError:
            return None
        if days <= 3:
            return "daily"
        if days <= 9:
            return "weekly"
        if days <= 16:
            return "biweekly"
        if days <= 45:
            return "monthly"
    return None


def _regex_pick_percent(text: str, label: str) -> float | None:
    import re

    pattern = rf"{label}[^0-9]{{0,50}}(\d{{1,2}}(?:\.\d{{1,2}})?)\s*%"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _regex_pick_rule_change(text: str) -> str | None:
    import re

    pattern = r"rules? (change|update)[^\n]{0,40}(daily|weekly|monthly|quarterly|annually|yearly)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(2).lower()


def _regex_pick_founded_year(text: str) -> int | None:
    if not text:
        return None
    pattern = r"(?:founded|established|since|launched|incorporated)\s*(?:in\s*)?(19\d{2}|20\d{2})"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _regex_pick_headquarters(text: str) -> str | None:
    if not text:
        return None
    patterns = [
        r"headquartered\s+in\s+([A-Z][A-Za-z\-\.\s]{2,60})",
        r"head office\s+in\s+([A-Z][A-Za-z\-\.\s]{2,60})",
        r"based\s+in\s+([A-Z][A-Za-z\-\.\s]{2,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip().strip(".,;")
            if value:
                return value
    return None


def _parse_percent_from_text(value: str | None) -> float | None:
    if not value or not isinstance(value, str):
        return None
    match = re.search(r"(\d{1,2}(?:\.\d{1,2})?)\s*%", value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _normalize_frequency(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    lowered = value.strip().lower().replace("-", " ")
    if "on demand" in lowered:
        return "on_demand"
    if "daily" in lowered:
        return "daily"
    if "biweekly" in lowered or "bi weekly" in lowered:
        return "biweekly"
    if "weekly" in lowered:
        return "weekly"
    if "monthly" in lowered:
        return "monthly"
    if "quarterly" in lowered:
        return "quarterly"
    if "annually" in lowered or "yearly" in lowered:
        return "yearly"
    return None


def _llm_extract_rules(text: str) -> dict[str, Any]:
    if not USE_LLM:
        return {}
    try:
        result = extract_rules_multi_pass(text, model=LLM_MODEL)
    except Exception:
        return {}
    if not isinstance(result, dict) or result.get("error"):
        return {}
    return {
        "payout_frequency": _normalize_frequency(result.get("payout_frequency")),
        "max_drawdown_rule": _parse_percent_from_text(result.get("max_drawdown")),
        "daily_drawdown_rule": _parse_percent_from_text(result.get("daily_drawdown")),
        "rule_changes_frequency": _normalize_frequency(result.get("rule_changes_frequency")),
    }


def _extract_rules(text: str) -> dict[str, Any]:
    max_drawdown = (
        _regex_pick_percent(text, "max drawdown")
        or _regex_pick_percent(text, "maximum drawdown")
        or _regex_pick_percent(text, "max loss")
        or _regex_pick_percent(text, "maximum loss")
        or _regex_pick_percent(text, "loss limit")
    )
    daily_drawdown = (
        _regex_pick_percent(text, "daily drawdown")
        or _regex_pick_percent(text, "daily loss")
        or _regex_pick_percent(text, "loss limit per day")
    )
    return {
        "payout_frequency": _regex_pick_frequency(text),
        "max_drawdown_rule": max_drawdown,
        "daily_drawdown_rule": daily_drawdown,
        "rule_changes_frequency": _regex_pick_rule_change(text),
    }


def _extract_profile(text: str) -> dict[str, Any]:
    return {
        "founded_year": _regex_pick_founded_year(text),
        "headquarters": _regex_pick_headquarters(text),
    }


def _has_missing_rules(fields: dict[str, Any]) -> bool:
    return any(fields.get(key) in (None, "", [], {}) for key in (
        "payout_frequency",
        "max_drawdown_rule",
        "daily_drawdown_rule",
        "rule_changes_frequency",
    ))


def _parse_raw_path(raw_object_path: str) -> tuple[str, str] | None:
    if not raw_object_path:
        return None
    cleaned = raw_object_path.replace("s3://", "").lstrip("/")
    if "/" not in cleaned:
        return None
    bucket, obj = cleaned.split("/", 1)
    return bucket, obj


def _load_firm_names(conn) -> dict[str, str]:
    cur = conn.cursor()
    cur.execute("SELECT firm_id, COALESCE(brand_name, name) FROM firms")
    return {row[0]: (row[1] or "") for row in cur.fetchall() if row[0]}


def _wiki_extract_profile(name: str) -> dict[str, Any]:
    if not USE_WIKI or not name:
        return {}
    import urllib.parse
    import urllib.request

    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/{}".format(
            urllib.parse.quote(name)
        )
        with urllib.request.urlopen(url, timeout=WIKI_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}
    text = payload.get("extract") or ""
    if not text:
        return {}
    return _extract_profile(text)


def _opencorporates_extract_profile(name: str) -> dict[str, Any]:
    if not USE_OPENCORPORATES or not name:
        return {}
    import urllib.parse
    import urllib.request

    try:
        url = "https://api.opencorporates.com/v0.4/companies/search?q={}".format(
            urllib.parse.quote(name)
        )
        with urllib.request.urlopen(url, timeout=OPENCORPORATES_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}
    results = payload.get("results", {}).get("companies", [])
    if not results:
        return {}
    company = results[0].get("company", {})
    founded_year = None
    incorporation_date = company.get("incorporation_date")
    if isinstance(incorporation_date, str) and len(incorporation_date) >= 4:
        try:
            founded_year = int(incorporation_date[:4])
        except ValueError:
            founded_year = None
    headquarters = None
    address = company.get("registered_address_in_full")
    if isinstance(address, str) and address.strip():
        headquarters = address.strip()
    if founded_year is None and headquarters is None:
        return {}
    data: dict[str, Any] = {}
    if founded_year is not None:
        data["founded_year"] = founded_year
    if headquarters is not None:
        data["headquarters"] = headquarters
    return data


def main() -> int:
    url = _database_url()
    conn = psycopg.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(
        """
        SELECT firm_id, key, raw_object_path, source_url
        FROM evidence
        WHERE key IN ('rules_html','pricing_html','rules_pdf','pricing_pdf','profile_html','profile_pdf')
        ORDER BY created_at DESC
        """
    )
    rows = cur.fetchall()

    firm_names = _load_firm_names(conn)

    evidence_map: dict[str, dict[str, list[tuple[str, str | None]]]] = {}
    for firm_id, key, raw_object_path, source_url in rows:
        if not raw_object_path:
            continue
        firm_bucket = evidence_map.setdefault(firm_id, {})
        key_list = firm_bucket.setdefault(key, [])
        entry = (raw_object_path, source_url)
        if entry not in key_list:
            key_list.append(entry)

    overrides: dict[str, Any] = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "auto_raw_regex",
        }
    }

    m = minio_client()

    processed = 0
    scanned = 0
    start = time.monotonic()
    for firm_id, evidence in evidence_map.items():
        if MAX_SCAN > 0 and scanned >= MAX_SCAN:
            break
        if MAX_FIRMS > 0 and processed >= MAX_FIRMS:
            break
        scanned += 1
        firm_start = time.monotonic()
        extracted: dict[str, Any] = {}
        sources: dict[str, str] = {}
        text_parts: list[str] = []
        for key in ("rules_html", "pricing_html", "rules_pdf", "pricing_pdf", "profile_html", "profile_pdf"):
            raw_paths = evidence.get(key, [])[:MAX_EVIDENCE_PER_KEY]
            for raw_path, source_url in raw_paths:
                parsed = _parse_raw_path(raw_path)
                if not parsed:
                    continue
                bucket, obj = parsed
                try:
                    max_bytes = MAX_PDF_BYTES if obj.lower().endswith(".pdf") else MAX_HTML_BYTES
                    html = _get_bytes_limited(m, bucket, obj, max_bytes)
                except Exception:
                    continue
                source_tag = "html"
                if obj.lower().endswith(".pdf"):
                    text = _pdf_to_text(html)
                    source_tag = "pdf"
                    if not text:
                        text = _pdf_to_text_ocr(html)
                        source_tag = "pdf_ocr" if text else source_tag
                else:
                    text = _html_to_text(html)
                if text:
                    text_parts.append(text)
                data = _extract_rules(text)
                profile = _extract_profile(text)
                for k, v in data.items():
                    if v is None:
                        continue
                    if k not in extracted:
                        extracted[k] = v
                        sources[k] = source_tag
                for k, v in profile.items():
                    if v is None:
                        continue
                    if k not in extracted:
                        extracted[k] = v
                        sources[k] = source_tag
                if USE_PLAYWRIGHT and _has_missing_rules(extracted) and source_url:
                    rendered = _render_html_playwright(source_url)
                    if rendered:
                        rendered_text = _html_to_text(rendered.encode("utf-8"))
                        if rendered_text:
                            text_parts.append(rendered_text)
                            data = _extract_rules(rendered_text)
                            profile = _extract_profile(rendered_text)
                            for k, v in data.items():
                                if v is None:
                                    continue
                                if k not in extracted:
                                    extracted[k] = v
                                    sources[k] = "playwright"
                            for k, v in profile.items():
                                if v is None:
                                    continue
                                if k not in extracted:
                                    extracted[k] = v
                                    sources[k] = "playwright"
                if MAX_FIRM_SECONDS > 0 and (time.monotonic() - firm_start) > MAX_FIRM_SECONDS:
                    break
            if MAX_FIRM_SECONDS > 0 and (time.monotonic() - firm_start) > MAX_FIRM_SECONDS:
                break

        if USE_LLM and text_parts and _has_missing_rules(extracted):
            combined = "\n\n".join(text_parts)
            llm_data = _llm_extract_rules(combined)
            for k, v in llm_data.items():
                if v is None:
                    continue
                if extracted.get(k) in (None, "", [], {}):
                    extracted[k] = v
                    sources[k] = "llm"
        if USE_WIKI and (extracted.get("founded_year") is None or extracted.get("headquarters") is None):
            wiki_data = _wiki_extract_profile(firm_names.get(firm_id, ""))
            for k, v in wiki_data.items():
                if v is None:
                    continue
                if extracted.get(k) in (None, "", [], {}):
                    extracted[k] = v
                    sources[k] = "wikipedia"
        if USE_OPENCORPORATES and (extracted.get("founded_year") is None or extracted.get("headquarters") is None):
            oc_data = _opencorporates_extract_profile(firm_names.get(firm_id, ""))
            for k, v in oc_data.items():
                if v is None:
                    continue
                if extracted.get(k) in (None, "", [], {}):
                    extracted[k] = v
                    sources[k] = "opencorporates"
        if extracted:
            extracted["_sources"] = sources
            overrides[firm_id] = extracted
            processed += 1
        if LOG_EVERY > 0 and scanned % LOG_EVERY == 0:
            elapsed = time.monotonic() - start
            print(f"[overrides] scanned={scanned} extracted={processed} elapsed={elapsed:.1f}s")

    Path(AUTO_OUTPUT).write_text(json.dumps(overrides, indent=2))
    print(f"[overrides] wrote {AUTO_OUTPUT} ({len(overrides) - 1} firms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
