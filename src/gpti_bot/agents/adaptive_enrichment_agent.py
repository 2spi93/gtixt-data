from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gpti_bot.db import connect, insert_datapoint
from gpti_bot.crawl import html_to_text, _regex_extract_rules, _is_pdf, _pdf_to_text

try:
    from gpti_bot.crawl import _render_with_playwright
except Exception:  # pragma: no cover
    _render_with_playwright = None


RULE_KEYWORDS = [
    "rules",
    "trading-rules",
    "rulebook",
    "terms",
    "conditions",
    "faq",
    "payout",
    "withdraw",
    "withdrawal",
    "policy",
    "legal",
]

PRICING_KEYWORDS = [
    "pricing",
    "prices",
    "plan",
    "plans",
    "fees",
    "fee",
    "challenge",
    "evaluation",
    "packages",
    "program",
    "accounts",
    "payout",
    "profit-split",
]

RULE_FALLBACK_PATHS = [
    "/rules",
    "/trading-rules",
    "/rulebook",
    "/faq",
    "/terms",
    "/terms-and-conditions",
    "/legal",
    "/policy",
    "/payout",
    "/withdrawal",
]

PRICING_FALLBACK_PATHS = [
    "/pricing",
    "/plans",
    "/fees",
    "/challenge",
    "/evaluation",
    "/packages",
    "/program",
    "/accounts",
    "/payout",
]


@dataclass
class AgentConfig:
    max_urls: int = 10
    timeout_s: int = 8
    enable_js: bool = True
    enable_pdf: bool = True
    min_text_chars: int = 600


def _build_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": os.getenv(
                "GPTI_AGENT_UA", "GTIXT-Agent/1.0 (+https://gtixt.com)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return session


def _normalize_root(root: str) -> str:
    root = (root or "").strip()
    if not root:
        return ""
    if not root.startswith("http://") and not root.startswith("https://"):
        root = "https://" + root
    return root.rstrip("/")


def _candidate_roots(root: str) -> List[str]:
    root = _normalize_root(root)
    if not root:
        return []
    parsed = urlparse(root)
    host = parsed.netloc
    candidates = [root]
    if host.startswith("www."):
        candidates.append(parsed._replace(netloc=host[4:]).geturl())
    else:
        candidates.append(parsed._replace(netloc="www." + host).geturl())
    return list(dict.fromkeys(candidates))


def _extract_links(html: bytes, base_url: str, keywords: Iterable[str], max_urls: int) -> List[str]:
    try:
        soup = BeautifulSoup(html.decode("utf-8", errors="ignore"), "lxml")
    except Exception:
        return []
    links = [a.get("href") for a in soup.select("a[href]")]
    links = [l for l in links if l and not l.startswith(("#", "mailto:", "javascript:"))]
    out: List[str] = []
    for link in links:
        url = urljoin(base_url, link)
        low = url.lower()
        if any(k in low for k in keywords):
            if url not in out:
                out.append(url)
        if len(out) >= max_urls:
            break
    return out


def _fetch(session: requests.Session, url: str, timeout_s: int) -> Tuple[int, bytes, str]:
    res = session.get(url, timeout=timeout_s, allow_redirects=True)
    return res.status_code, res.content or b"", res.headers.get("content-type", "")


def _prioritize(urls: List[str], keywords: Iterable[str]) -> List[str]:
    def score(u: str) -> int:
        low = u.lower()
        return sum(10 for k in keywords if k in low)

    return sorted(urls, key=score, reverse=True)


def _extract_text(
    html: bytes,
    content_type: str,
    url: str,
    config: AgentConfig,
) -> str:
    is_pdf = _is_pdf(content_type, url, html)
    if is_pdf and not config.enable_pdf:
        return ""
    if is_pdf:
        return _pdf_to_text(html)
    text = html_to_text(html, max_chars=20000)
    if config.enable_js and len(text) < config.min_text_chars and _render_with_playwright:
        rendered = _render_with_playwright(url)
        if rendered:
            text = html_to_text(rendered, max_chars=20000)
    return text


def _has_rule_data(payload: Dict[str, Any]) -> bool:
    return any(
        payload.get(key) not in (None, "", [], {})
        for key in ("payout_frequency", "max_drawdown", "daily_drawdown", "rule_changes_frequency")
    )


def _sitemap_urls(session: requests.Session, root: str, timeout_s: int) -> List[str]:
    candidates = [urljoin(root, "/sitemap.xml"), urljoin(root, "/sitemap_index.xml")]
    out: List[str] = []
    for url in candidates:
        try:
            status, body, _ctype = _fetch(session, url, timeout_s)
            if status >= 400 or not body:
                continue
            text = body.decode("utf-8", errors="ignore")
            for loc in re.findall(r"<loc>([^<]+)</loc>", text):
                out.append(loc.strip())
            if out:
                break
        except Exception:
            continue
    return out


class AdaptiveEnrichmentAgent:
    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self.config = config or AgentConfig()
        self.session = _build_session()

    def enrich_firm(self, firm_id: str, website_root: str) -> Dict[str, Any]:
        config = self.config
        visited: List[str] = []
        extracted_rules: Dict[str, Any] = {}
        extracted_pricing: Dict[str, Any] = {}
        errors: List[str] = []

        roots = _candidate_roots(website_root)
        for root in roots:
            try:
                status, body, ctype = _fetch(self.session, root, config.timeout_s)
                if status >= 400:
                    continue
                visited.append(root)
                home_links_rules = _extract_links(body, root, RULE_KEYWORDS, config.max_urls)
                home_links_pricing = _extract_links(body, root, PRICING_KEYWORDS, config.max_urls)

                rule_urls = _prioritize(
                    home_links_rules + [urljoin(root, p) for p in RULE_FALLBACK_PATHS],
                    RULE_KEYWORDS,
                )
                pricing_urls = _prioritize(
                    home_links_pricing + [urljoin(root, p) for p in PRICING_FALLBACK_PATHS],
                    PRICING_KEYWORDS,
                )

                sitemap_urls = _sitemap_urls(self.session, root, config.timeout_s)
                for url in sitemap_urls:
                    low = url.lower()
                    if any(k in low for k in RULE_KEYWORDS) and url not in rule_urls:
                        rule_urls.append(url)
                    if any(k in low for k in PRICING_KEYWORDS) and url not in pricing_urls:
                        pricing_urls.append(url)

                rule_urls = rule_urls[: config.max_urls]
                pricing_urls = pricing_urls[: config.max_urls]

                for url in rule_urls:
                    try:
                        status, body, ctype = _fetch(self.session, url, config.timeout_s)
                        if status >= 400:
                            continue
                        visited.append(url)
                        text = _extract_text(body, ctype, url, config)
                        if not text:
                            continue
                        extracted = _regex_extract_rules(text)
                        extracted["source_url"] = url
                        extracted["checked_urls"] = list(dict.fromkeys(visited))
                        extracted_rules = extracted
                        if _has_rule_data(extracted):
                            break
                    except Exception as exc:
                        errors.append(f"rules:{url}:{exc}")

                for url in pricing_urls:
                    try:
                        status, body, ctype = _fetch(self.session, url, config.timeout_s)
                        if status >= 400:
                            continue
                        visited.append(url)
                        text = _extract_text(body, ctype, url, config)
                        if not text:
                            continue
                        extracted = _regex_extract_rules(text)
                        extracted["source_url"] = url
                        extracted["checked_urls"] = list(dict.fromkeys(visited))
                        extracted_pricing = extracted
                        if _has_rule_data(extracted):
                            break
                    except Exception as exc:
                        errors.append(f"pricing:{url}:{exc}")

                if extracted_rules or extracted_pricing:
                    break
            except Exception as exc:
                errors.append(f"root:{root}:{exc}")

        return {
            "rules": extracted_rules,
            "pricing": extracted_pricing,
            "visited": visited,
            "errors": errors,
        }


def _latest_datapoint(conn, firm_id: str, key: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT value_json
            FROM datapoints
            WHERE firm_id = %s AND key = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (firm_id, key),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _missing_fields(payload: Optional[Dict[str, Any]]) -> bool:
    if not payload:
        return True
    return not _has_rule_data(payload)


def run_targeted_enrichment(
    *,
    limit: int = 50,
    enable_js: bool = True,
    enable_pdf: bool = True,
    max_urls: int = 10,
    timeout_s: int = 8,
) -> Dict[str, Any]:
    verbose = os.getenv("GPTI_AGENT_VERBOSE", "1") == "1"
    config = AgentConfig(
        max_urls=max_urls,
        timeout_s=timeout_s,
        enable_js=enable_js,
        enable_pdf=enable_pdf,
    )
    agent = AdaptiveEnrichmentAgent(config)

    processed = 0
    enriched = 0
    errors = 0

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT firm_id, website_root
                FROM firms
                WHERE coalesce(website_root, '') <> ''
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

        for firm_id, website_root in rows:
            rules = _latest_datapoint(conn, firm_id, "rules_extracted_v0")
            pricing = _latest_datapoint(conn, firm_id, "pricing_extracted_v0")

            if not _missing_fields(rules) and not _missing_fields(pricing):
                continue

            processed += 1
            if verbose:
                print(f"[adaptive-enrichment] firm={firm_id} url={website_root}")
            result = agent.enrich_firm(str(firm_id), str(website_root))
            try:
                if result.get("rules"):
                    insert_datapoint(
                        conn,
                        firm_id=str(firm_id),
                        key="rules_extracted_v0",
                        value_json=result["rules"],
                        value_text=None,
                        source_url=result["rules"].get("source_url"),
                        evidence_hash=None,
                    )
                if result.get("pricing"):
                    insert_datapoint(
                        conn,
                        firm_id=str(firm_id),
                        key="pricing_extracted_v0",
                        value_json=result["pricing"],
                        value_text=None,
                        source_url=result["pricing"].get("source_url"),
                        evidence_hash=None,
                    )
                if result.get("rules") or result.get("pricing"):
                    enriched += 1
                    if verbose:
                        print(f"[adaptive-enrichment] enriched firm={firm_id}")
                elif verbose:
                    print(f"[adaptive-enrichment] no_data firm={firm_id}")
            except Exception:
                errors += 1
                if verbose:
                    print(f"[adaptive-enrichment] error firm={firm_id}")

    return {
        "processed": processed,
        "enriched": enriched,
        "errors": errors,
    }
