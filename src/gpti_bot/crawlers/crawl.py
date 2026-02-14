from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning
import warnings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gpti_bot.db import fetchall, insert_datapoint, insert_evidence
from gpti_bot.minio import put_bytes
from gpti_bot.agents.rules_verifier import extract_rules_multi_pass
from gpti_bot.agents.score_auditor import audit_rules
from gpti_bot.agents.meta_verifier import verify_pipeline_output

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

RULE_KEYWORDS = [
    "rule", "rules", "faq", "terms", "conditions", "payout", "withdraw", "refund",
    "policy", "agreement", "legal", "trading-rules", "consistency", "drawdown",
]

FALLBACK_PATHS = [
    "/rules", "/trading-rules", "/rulebook", "/faq", "/faqs", "/help",
    "/terms", "/terms-and-conditions", "/legal", "/agreement", "/policies",
    "/payout", "/payouts", "/withdrawal", "/refund", "/fees",
]

@dataclass
class FetchResult:
    url: str
    status_code: int
    content: bytes

def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET","HEAD"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": os.getenv("GPTI_UA", "GPTI-UniverseBot/0.2 (+data; contact: admin@gpti.example)"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def html_to_text(html_bytes: bytes, max_chars: int = 20000, max_bytes: int = 2_000_000) -> str:
    # Protect memory: cap bytes before decoding
    if len(html_bytes) > max_bytes:
        html_bytes = html_bytes[:max_bytes]

    html = html_bytes.decode("utf-8", errors="ignore")
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        return f"[parse_error] {str(e)}"

    # Remove heavy/noisy tags
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text

def extract_ruleish_links(root: str, html_bytes: bytes, max_links: int = 20, max_bytes: int = 2_000_000) -> list[str]:
    if len(html_bytes) > max_bytes:
        html_bytes = html_bytes[:max_bytes]
    html = html_bytes.decode("utf-8", errors="ignore")
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []

    links = [a.get("href") for a in soup.select("a[href]")]
    links = [l for l in links if l and not l.startswith(("#", "mailto:", "javascript:"))]

    abs_links = [urljoin(root, l) for l in links]
    out: List[str] = []
    for u in abs_links:
        low = u.lower()
        if any(k in low for k in RULE_KEYWORDS) and u not in out:
            out.append(u)

    # Also include a small set of normalized fallbacks (if same host)
    base = urlparse(root)
    for p in FALLBACK_PATHS:
        u = urljoin(root, p)
        if urlparse(u).netloc == base.netloc and u not in out:
            out.append(u)

    return out[:max_links]

def _fetch(session: requests.Session, url: str, *, timeout_s: int = 20, max_bytes: int = 2_000_000) -> FetchResult:
    r = session.get(url, timeout=timeout_s, allow_redirects=True)
    status = int(r.status_code)
    content = (r.content or b"")
    if len(content) > max_bytes:
        content = content[:max_bytes]
    return FetchResult(url=r.url, status_code=status, content=content)

def _store_raw_html(firm_id: str, url: str, html: bytes) -> tuple[str, str]:
    sha = _sha256(html)
    object_path = f"raw/{firm_id}/{sha}.html"
    put_bytes(object_path, html, content_type="text/html")
    return sha, object_path

def _evidence_excerpt(text: str, max_len: int = 480) -> str:
    t = " ".join(text.split())
    return t[:max_len]

def crawl_firms(*, limit: int, statuses: list[str], max_links: int = 20, max_bytes: int = 2_000_000, max_chars: int = 20_000, sleep_s: float = 0.4, llm_on: bool = True) -> None:
    # Pick firms
    rows = fetchall(
        """
        SELECT firm_id, brand_name, website_root, model_type, status
        FROM firms
        WHERE status = ANY(%(statuses)s)
        ORDER BY updated_at ASC
        LIMIT %(limit)s
        """,
        {"statuses": statuses, "limit": limit},
    )

    s = _session()
    model_rules = os.getenv("OLLAMA_MODEL_RULES", "llama3.1:latest")
    for row in rows:
        firm_id = row["firm_id"]
        root = str(row["website_root"]).rstrip("/")

        # Fetch homepage
        try:
            home = _fetch(s, root + "/", timeout_s=20, max_bytes=max_bytes)
            if home.status_code >= 400:
                insert_datapoint(firm_id=firm_id, key="http_error", value_json={"status": home.status_code}, value_text=f"{home.status_code}", source_url=home.url)
                continue
        except Exception as e:
            insert_datapoint(firm_id=firm_id, key="crawl_error", value_json={"error": "fetch_failed"}, value_text=str(e)[:1000], source_url=root)
            continue

        # Discover candidate links
        links = extract_ruleish_links(home.url, home.content, max_links=max_links, max_bytes=max_bytes)
        insert_datapoint(firm_id=firm_id, key="discovered_links", value_json={"count": len(links), "links": links}, value_text=None, source_url=home.url)

        # For speed: pick top few (prioritize likely rule pages)
        def score(u: str) -> int:
            u = u.lower()
            pri = 0
            for kw in ("rules","trading-rules","rulebook","terms","faq","payout","withdraw"):
                if kw in u:
                    pri += 10
            return pri
        links = sorted(links, key=score, reverse=True)[:6] or [home.url]

        # Fetch + store evidence + extract
        combined_text_parts: List[str] = []
        used_urls: List[str] = []
        for u in links:
            try:
                fr = _fetch(s, u, timeout_s=25, max_bytes=max_bytes)
                if fr.status_code >= 400:
                    insert_datapoint(firm_id=firm_id, key="http_error", value_json={"status": fr.status_code}, value_text=f"{fr.status_code}", source_url=fr.url)
                    continue
                sha, obj_path = _store_raw_html(firm_id, fr.url, fr.content)
                text = html_to_text(fr.content, max_chars=max_chars, max_bytes=max_bytes)
                excerpt = _evidence_excerpt(text)
                insert_evidence(firm_id=firm_id, key="raw_html_v0", source_url=fr.url, sha256=sha, excerpt=excerpt, raw_object_path=obj_path)
                combined_text_parts.append(text)
                used_urls.append(fr.url)
            except Exception as e:
                insert_datapoint(firm_id=firm_id, key="crawl_error", value_json={"error": "page_fetch_failed"}, value_text=str(e)[:1000], source_url=u)
            time.sleep(max(sleep_s, 0.0))

        combined_text = "\n\n".join(combined_text_parts).strip()
        if not combined_text:
            insert_datapoint(firm_id=firm_id, key="rules_not_found_v0", value_json={"reason": "no_text_extracted", "checked_urls": used_urls}, value_text=None, source_url=home.url)
            continue

        if not llm_on:
            insert_datapoint(firm_id=firm_id, key="rules_extracted_v0", value_json={"skipped": True, "checked_urls": used_urls}, value_text=None, source_url=home.url)
            continue

        # Agent A: extract rules using LLM in multi-pass chunks
        try:
            rules = extract_rules_multi_pass(combined_text, model=model_rules)
        except Exception as e:
            rules = {"error": "llm_call_failed", "detail": str(e)[:1000]}

        # Attach sources
        if isinstance(rules, dict) and "error" not in rules:
            rules["source_urls"] = list(dict.fromkeys((rules.get("source_urls") or []) + used_urls))

        # Agent B: audit
        audit = audit_rules(rules if isinstance(rules, dict) else {"error":"bad_rules_type"})

        # Oversight Gate: meta-verify
        meta = verify_pipeline_output(rules if isinstance(rules, dict) else {"error":"bad_rules_type"}, audit)

        insert_datapoint(
            firm_id=firm_id,
            key="rules_extracted_v0",
            value_json={"rules": rules, "audit": audit, "meta": meta, "checked_urls": used_urls},
            value_text=None,
            source_url=home.url,
            evidence_hash=_sha256(combined_text.encode("utf-8", errors="ignore")),
        )
