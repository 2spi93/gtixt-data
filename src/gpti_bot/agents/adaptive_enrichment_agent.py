from __future__ import annotations

import os
import re
import time
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gpti_bot.db import connect, insert_datapoint
from gpti_bot.crawl import html_to_text, _regex_extract_rules, _is_pdf, _pdf_to_text, fetch_external_evidence
from gpti_bot.external_sources import rank_candidates_diverse
from gpti_bot.extract_from_evidence import run_extract_from_evidence_for_firm

try:
    from gpti_bot.crawl import _render_with_playwright, _render_with_playwright_meta
except Exception:  # pragma: no cover
    _render_with_playwright = None
    _render_with_playwright_meta = None


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

BLACKLIST_KEYWORDS = [
    "blog",
    "news",
    "press",
    "affiliate",
    "partners",
    "cookie",
    "privacy",
    "login",
    "signup",
    "register",
    "careers",
    "jobs",
    "contact",
    "support-ticket",
]

CAPTCHA_MARKERS = [
    "captcha",
    "g-recaptcha",
    "recaptcha",
    "hcaptcha",
    "cf-challenge",
    "cloudflare",
    "verify you are human",
]

DEFAULT_USER_AGENT = os.getenv(
    "GPTI_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
)
FIRM_SEED_PATH = os.getenv(
    "GPTI_FIRM_SEED_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "seeds", "firm_url_seeds.json")),
)
_FIRM_SEED_URLS: dict[str, dict] | None = None

DOMAIN_DELAY_S = float(os.getenv("GPTI_DOMAIN_DELAY_S", "0.4"))
_LAST_REQUEST_AT: dict[str, float] = {}

COMMON_TYPO_MAP = {
    "princing": "pricing",
    "prcing": "pricing",
    "pricng": "pricing",
    "tradding": "trading",
    "tradng": "trading",
    "challange": "challenge",
    "chalenge": "challenge",
    "withdawal": "withdrawal",
    "withdrawl": "withdrawal",
    "payouts": "payout",
}


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
    proxy = os.getenv("GPTI_PROXY") or os.getenv("GPTI_HTTP_PROXY")
    https_proxy = os.getenv("GPTI_HTTPS_PROXY") or proxy
    if proxy or https_proxy:
        session.proxies.update({
            "http": proxy or "",
            "https": https_proxy or proxy or "",
        })
    session.headers.update(
        {
            "User-Agent": os.getenv("GPTI_AGENT_UA", DEFAULT_USER_AGENT),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7",
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


def _load_firm_seed_urls() -> dict[str, dict]:
    global _FIRM_SEED_URLS
    if _FIRM_SEED_URLS is not None:
        return _FIRM_SEED_URLS
    try:
        with open(FIRM_SEED_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            _FIRM_SEED_URLS = {str(k).lower(): v for k, v in data.items() if not str(k).startswith("_")}
        else:
            _FIRM_SEED_URLS = {}
    except Exception:
        _FIRM_SEED_URLS = {}
    return _FIRM_SEED_URLS


def _seed_urls_for_firm(firm_id: str, root: str, kind: str) -> List[str]:
    data = _load_firm_seed_urls()
    entry = data.get((firm_id or "").lower())
    if not isinstance(entry, dict):
        return []
    seeds = entry.get(kind) or entry.get("all") or []
    if not isinstance(seeds, list):
        return []
    out: List[str] = []
    for u in seeds:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u:
            continue
        out.append(urljoin(root, u) if u.startswith("/") else u)
    return out


def _extract_links(html: bytes, base_url: str, keywords: Iterable[str], max_urls: int) -> List[str]:
    try:
        soup = BeautifulSoup(html.decode("utf-8", errors="ignore"), "lxml")
    except Exception:
        return []
    anchors = soup.select("a[href]")
    scored: list[tuple[int, str]] = []
    for anchor in anchors:
        link = anchor.get("href")
        if not link or link.startswith(("#", "mailto:", "javascript:")):
            continue
        url = urljoin(base_url, link)
        low = url.lower()
        if any(bad in low for bad in BLACKLIST_KEYWORDS):
            continue
        anchor_text = " ".join(anchor.stripped_strings).lower()
        score = 0
        if any(k in low for k in keywords):
            score += 6
        if any(k in anchor_text for k in keywords):
            score += 4
        parent = anchor.find_parent(["nav", "header", "footer", "li", "section", "div"])
        if parent:
            parent_text = " ".join(parent.stripped_strings).lower()
            if any(k in parent_text for k in keywords):
                score += 2
        if score > 0:
            scored.append((score, url))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[str] = []
    for _score, url in scored:
        if url not in out:
            out.append(url)
        if len(out) >= max_urls:
            break
    return out


def _throttle_request(url: str) -> None:
    if DOMAIN_DELAY_S <= 0:
        return
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return
    if not host:
        return
    last = _LAST_REQUEST_AT.get(host)
    now = time.monotonic()
    if last is not None:
        wait_s = DOMAIN_DELAY_S - (now - last)
        if wait_s > 0:
            time.sleep(wait_s)
    _LAST_REQUEST_AT[host] = time.monotonic()


def _fetch(session: requests.Session, url: str, timeout_s: int) -> Tuple[int, bytes, str]:
    _throttle_request(url)
    res = session.get(url, timeout=timeout_s, allow_redirects=True)
    if res.status_code < 400:
        return res.status_code, res.content or b"", res.headers.get("content-type", "")
    for candidate in _repair_url_candidates(url):
        try:
            retry = session.get(candidate, timeout=timeout_s, allow_redirects=True)
        except Exception:
            continue
        if retry.status_code < 400:
            return retry.status_code, retry.content or b"", retry.headers.get("content-type", "")
    return res.status_code, res.content or b"", res.headers.get("content-type", "")


def _repair_url_candidates(url: str) -> List[str]:
    if not url:
        return []
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    clean_path = re.sub(r"/{2,}", "/", path)

    variants = {url}
    if clean_path != path:
        variants.add(parsed._replace(path=clean_path).geturl())

    if clean_path.endswith("/") and clean_path != "/":
        variants.add(parsed._replace(path=clean_path.rstrip("/")).geturl())
    else:
        variants.add(parsed._replace(path=clean_path + "/").geturl())

    for typo, fix in COMMON_TYPO_MAP.items():
        if typo in clean_path:
            variants.add(parsed._replace(path=clean_path.replace(typo, fix)).geturl())

    if host.startswith("www."):
        variants.add(parsed._replace(netloc=host[4:]).geturl())
    else:
        variants.add(parsed._replace(netloc="www." + host).geturl())

    if parsed.scheme == "http":
        variants.add(parsed._replace(scheme="https").geturl())
    elif parsed.scheme == "https":
        variants.add(parsed._replace(scheme="http").geturl())

    return [u for u in variants if u]


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
) -> tuple[str, bool]:
    is_pdf = _is_pdf(content_type, url, html)
    if is_pdf and not config.enable_pdf:
        return "", False
    if is_pdf:
        return _pdf_to_text(html), False
    text = html_to_text(html, max_chars=20000)
    captcha_detected = _looks_like_captcha(text)
    if config.enable_js and len(text) < config.min_text_chars and _render_with_playwright:
        rendered = None
        if _render_with_playwright_meta:
            rendered, meta = _render_with_playwright_meta(url)
            if meta.get("captcha_detected"):
                return "", True
        else:
            rendered = _render_with_playwright(url)
        if rendered:
            text = html_to_text(rendered, max_chars=20000)
            captcha_detected = _looks_like_captcha(text)
    return text, captcha_detected


def _looks_like_captcha(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in CAPTCHA_MARKERS)


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
        captcha_urls: List[str] = []

        roots = _candidate_roots(website_root)
        for root in roots:
            try:
                status, body, ctype = _fetch(self.session, root, config.timeout_s)
                if status >= 400:
                    continue
                visited.append(root)
                home_links_rules = _extract_links(body, root, RULE_KEYWORDS, config.max_urls)
                home_links_pricing = _extract_links(body, root, PRICING_KEYWORDS, config.max_urls)

                seed_rules = _seed_urls_for_firm(firm_id, root, "rules")
                seed_pricing = _seed_urls_for_firm(firm_id, root, "pricing")
                rule_urls = _prioritize(
                    seed_rules + home_links_rules + [urljoin(root, p) for p in RULE_FALLBACK_PATHS],
                    RULE_KEYWORDS,
                )
                pricing_urls = _prioritize(
                    seed_pricing + home_links_pricing + [urljoin(root, p) for p in PRICING_FALLBACK_PATHS],
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
                        text, captcha = _extract_text(body, ctype, url, config)
                        if captcha:
                            captcha_urls.append(url)
                            continue
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
                        text, captcha = _extract_text(body, ctype, url, config)
                        if captcha:
                            captcha_urls.append(url)
                            continue
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
            "captcha": list(dict.fromkeys(captcha_urls)),
        }


def _external_fallback(
    conn,
    firm_id: str,
    brand_name: str | None,
    website_root: str | None,
    *,
    verbose: bool = False,
) -> Dict[str, Any]:
    external_limit = int(os.getenv("GPTI_EXTERNAL_MAX_URLS", "10"))
    urls = rank_candidates_diverse(
        brand_name,
        firm_id,
        website_root,
        limit=external_limit,
        per_slug=2,
    )
    stored = fetch_external_evidence(firm_id, urls)
    evidence = run_extract_from_evidence_for_firm(firm_id) if stored > 0 else {"processed": 0}
    rules = _latest_datapoint(conn, firm_id, "rules_extracted_v0")
    pricing = _latest_datapoint(conn, firm_id, "pricing_extracted_v0")
    enriched = not _missing_fields(rules) or not _missing_fields(pricing)
    insert_datapoint(
        conn,
        firm_id=firm_id,
        key="external_fallback",
        value_json={
            "urls": urls,
            "stored": stored,
            "evidence": evidence,
            "enriched": enriched,
        },
        value_text=None,
        source_url=website_root,
        evidence_hash=None,
    )
    if verbose:
        print(
            f"[adaptive-enrichment] external_fallback firm={firm_id} stored={stored} enriched={enriched}"
        )
    return {
        "urls": urls,
        "stored": stored,
        "evidence": evidence,
        "enriched": enriched,
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
                SELECT firm_id, website_root, brand_name
                FROM firms
                WHERE coalesce(website_root, '') <> ''
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

        for firm_id, website_root, brand_name in rows:
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
                else:
                    fallback = _external_fallback(
                        conn,
                        str(firm_id),
                        brand_name,
                        website_root,
                        verbose=verbose,
                    )
                    if fallback.get("enriched"):
                        enriched += 1
                        if verbose:
                            print(f"[adaptive-enrichment] enriched_external firm={firm_id}")
                    elif verbose:
                        print(f"[adaptive-enrichment] no_data firm={firm_id}")
                if result.get("captcha"):
                    insert_datapoint(
                        conn,
                        firm_id=str(firm_id),
                        key="captcha_detected",
                        value_json={"urls": result.get("captcha")},
                        value_text=None,
                        source_url=website_root,
                        evidence_hash=None,
                    )
            except Exception:
                errors += 1
                if verbose:
                    print(f"[adaptive-enrichment] error firm={firm_id}")

    return {
        "processed": processed,
        "enriched": enriched,
        "errors": errors,
    }


def run_targeted_enrichment_for_firm(
    firm_id: str,
    *,
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

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT firm_id, website_root, brand_name
                FROM firms
                WHERE firm_id = %s
                LIMIT 1
                """,
                (firm_id,),
            )
            row = cur.fetchone()
        if not row:
            return {"processed": 0, "enriched": 0, "errors": 1, "error": "firm_not_found"}

        target_id, website_root, brand_name = row
        if not website_root:
            return {"processed": 0, "enriched": 0, "errors": 1, "error": "missing_website_root"}

        if verbose:
            print(f"[adaptive-enrichment] firm={target_id} url={website_root}")
        result = agent.enrich_firm(str(target_id), str(website_root))

        enriched = 0
        errors = 0
        try:
            if result.get("rules"):
                insert_datapoint(
                    conn,
                    firm_id=str(target_id),
                    key="rules_extracted_v0",
                    value_json=result["rules"],
                    value_text=None,
                    source_url=result["rules"].get("source_url"),
                    evidence_hash=None,
                )
            if result.get("pricing"):
                insert_datapoint(
                    conn,
                    firm_id=str(target_id),
                    key="pricing_extracted_v0",
                    value_json=result["pricing"],
                    value_text=None,
                    source_url=result["pricing"].get("source_url"),
                    evidence_hash=None,
                )
            if result.get("rules") or result.get("pricing"):
                enriched = 1
                if verbose:
                    print(f"[adaptive-enrichment] enriched firm={target_id}")
            else:
                fallback = _external_fallback(
                    conn,
                    str(target_id),
                    brand_name,
                    website_root,
                    verbose=verbose,
                )
                if fallback.get("enriched"):
                    enriched = 1
                    if verbose:
                        print(f"[adaptive-enrichment] enriched_external firm={target_id}")
                elif verbose:
                    print(f"[adaptive-enrichment] no_data firm={target_id}")
            if result.get("captcha"):
                insert_datapoint(
                    conn,
                    firm_id=str(target_id),
                    key="captcha_detected",
                    value_json={"urls": result.get("captcha")},
                    value_text=None,
                    source_url=website_root,
                    evidence_hash=None,
                )
        except Exception:
            errors = 1
            if verbose:
                print(f"[adaptive-enrichment] error firm={target_id}")

    return {
        "processed": 1,
        "enriched": enriched,
        "errors": errors,
    }
