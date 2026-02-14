from __future__ import annotations

import hashlib
import io
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import requests
import warnings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .db import connect, fetch_firms, insert_evidence, insert_datapoint
from .minio import client as minio_client, put_bytes
from .agents.pricing_extractor import extract_pricing
from .agents.rules_extractor import extract_rules_multi_pass as extract_rules

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


RAW_BUCKET = "gpti-raw"

MAX_HTML_BYTES = int(os.getenv("GPTI_MAX_HTML_BYTES", "2000000"))  # 2MB
MAX_TEXT_CHARS = int(os.getenv("GPTI_MAX_TEXT_CHARS", "20000"))
MAX_PDF_CHARS = int(os.getenv("GPTI_MAX_PDF_CHARS", "40000"))
MAX_LINKS = int(os.getenv("GPTI_MAX_LINKS", "25"))
SLEEP_S = float(os.getenv("GPTI_CRAWL_SLEEP_S", "0.8"))
VERBOSE = os.getenv("GPTI_VERBOSE", "0") == "1"
HTTP_TIMEOUT_S = int(os.getenv("GPTI_HTTP_TIMEOUT_S", "10"))
CRAWL_WORKERS = int(os.getenv("GPTI_CRAWL_WORKERS", "4"))
SLOW_DOMAIN_S = float(os.getenv("GPTI_SLOW_DOMAIN_S", "8"))
MAX_RUNTIME_S = int(os.getenv("GPTI_MAX_RUNTIME_S", "7200"))
MAX_REQUESTS = int(os.getenv("GPTI_MAX_REQUESTS", "50000"))
MAX_DOMAIN_S = int(os.getenv("GPTI_MAX_DOMAIN_S", "1800"))
MAX_PAGES_PER_FIRM = int(os.getenv("GPTI_MAX_PAGES_PER_FIRM", "100"))
SITEMAP_MAX_URLS = int(os.getenv("GPTI_SITEMAP_MAX_URLS", "60"))
RULES_MODEL = os.getenv("GPTI_RULES_MODEL")
PRICING_MODEL = os.getenv("GPTI_PRICING_MODEL")
MAX_RULE_PAGES = int(os.getenv("GPTI_MAX_RULE_PAGES", "30"))
MAX_PRICING_PAGES = int(os.getenv("GPTI_MAX_PRICING_PAGES", "30"))
CRAWL_DEPTH = int(os.getenv("GPTI_CRAWL_DEPTH", "1"))
MAX_DEEP_LINKS = int(os.getenv("GPTI_MAX_DEEP_LINKS", "20"))
ENABLE_JS_RENDER = os.getenv("GPTI_ENABLE_JS_RENDER", "0") == "1"
ENABLE_PDF = os.getenv("GPTI_ENABLE_PDF", "1") == "1"
MAX_JS_PAGES = int(os.getenv("GPTI_MAX_JS_PAGES", "6"))
MIN_TEXT_CHARS = int(os.getenv("GPTI_MIN_TEXT_CHARS", "800"))

FAST_MODE = os.getenv("GPTI_FAST_MODE", "0") == "1"
if FAST_MODE:
    MAX_HTML_BYTES = int(os.getenv("GPTI_FAST_MAX_HTML_BYTES", "1200000"))
    MAX_TEXT_CHARS = int(os.getenv("GPTI_FAST_MAX_TEXT_CHARS", "12000"))
    MAX_PDF_CHARS = int(os.getenv("GPTI_FAST_MAX_PDF_CHARS", "20000"))
    MAX_LINKS = int(os.getenv("GPTI_FAST_MAX_LINKS", "12"))
    SLEEP_S = float(os.getenv("GPTI_FAST_SLEEP_S", "0.15"))
    HTTP_TIMEOUT_S = int(os.getenv("GPTI_FAST_HTTP_TIMEOUT_S", "5"))
    CRAWL_WORKERS = int(os.getenv("GPTI_FAST_WORKERS", "20"))
    SLOW_DOMAIN_S = float(os.getenv("GPTI_FAST_SLOW_DOMAIN_S", "4"))
    MAX_DOMAIN_S = int(os.getenv("GPTI_FAST_MAX_DOMAIN_S", "240"))
    MAX_PAGES_PER_FIRM = int(os.getenv("GPTI_FAST_MAX_PAGES_PER_FIRM", "25"))
    SITEMAP_MAX_URLS = int(os.getenv("GPTI_FAST_SITEMAP_MAX_URLS", "30"))
    MAX_RULE_PAGES = int(os.getenv("GPTI_FAST_MAX_RULE_PAGES", "6"))
    MAX_PRICING_PAGES = int(os.getenv("GPTI_FAST_MAX_PRICING_PAGES", "6"))
    CRAWL_DEPTH = int(os.getenv("GPTI_FAST_CRAWL_DEPTH", "0"))
    MAX_DEEP_LINKS = int(os.getenv("GPTI_FAST_MAX_DEEP_LINKS", "8"))
    ENABLE_JS_RENDER = os.getenv("GPTI_FAST_ENABLE_JS_RENDER", "0") == "1"
    ENABLE_PDF = os.getenv("GPTI_FAST_ENABLE_PDF", "0") == "1"
    MAX_JS_PAGES = int(os.getenv("GPTI_FAST_MAX_JS_PAGES", "2"))
    MIN_TEXT_CHARS = int(os.getenv("GPTI_FAST_MIN_TEXT_CHARS", "500"))

RETRY_TOTAL = int(os.getenv("GPTI_HTTP_RETRY_TOTAL", "3"))
RETRY_BACKOFF = float(os.getenv("GPTI_HTTP_RETRY_BACKOFF", "0.4"))

RULE_KEYWORDS = ["rules","faq","terms","conditions","policy","payout","withdraw","agreement","trading-rules","legal","kyc","refund","help","support"]
PRICING_KEYWORDS = ["pricing","price","plans","plan","fees","fee","challenge","evaluation","accounts","packages","program","payout","profit split","funding","refund"]

RULE_FALLBACK_PATHS = [
    "/rules","/trading-rules","/faq","/help","/support","/help-center",
    "/terms","/terms-of-use","/terms-and-conditions",
    "/policy","/policies","/legal","/privacy","/cookie-policy",
    "/payout","/payouts","/payout-policy",
    "/withdrawal","/withdrawals",
]
PRICING_FALLBACK_PATHS = [
    "/pricing","/plans","/plan","/fees","/fee","/challenge","/challenges",
    "/evaluation","/program","/programs","/accounts","/products","/packages",
    "/payouts","/payout","/profit-split",
]

SITEMAP_PATHS = ["/sitemap.xml","/sitemap_index.xml","/sitemap-index.xml"]

REQUEST_LOCK = threading.Lock()
REQUEST_COUNT = 0
START_TIME = 0.0


def _regex_pick_frequency(text: str) -> str | None:
    lowered = text.lower()
    if "payout" not in lowered and "withdraw" not in lowered and "withdrawal" not in lowered:
        return None
    token_map = {
        "on demand": "on_demand",
        "on-demand": "on_demand",
        "daily": "daily",
        "weekly": "weekly",
        "biweekly": "biweekly",
        "bi-weekly": "biweekly",
        "monthly": "monthly",
        "quarterly": "quarterly",
        "annually": "annually",
        "yearly": "annually",
    }
    for token, value in token_map.items():
        if token in lowered:
            return value

    interval_match = re.search(
        r"(?:payouts?|withdrawals?)\s+(?:are\s+)?(?:processed|paid|available)?\s*(?:every|within|after)\s+(\d{1,2})\s+days?",
        lowered,
    )
    if interval_match:
        days = int(interval_match.group(1))
        if days <= 1:
            return "daily"
        if days <= 7:
            return "weekly"
        if days <= 14:
            return "biweekly"
        if days <= 31:
            return "monthly"

    generic_interval = re.search(r"(?:every|within|after)\s+(\d{1,2})\s+(day|week|month)s?", lowered)
    if generic_interval:
        count = int(generic_interval.group(1))
        unit = generic_interval.group(2)
        if unit == "day":
            if count <= 1:
                return "daily"
            if count <= 7:
                return "weekly"
            if count <= 14:
                return "biweekly"
            if count <= 31:
                return "monthly"
        if unit == "week":
            if count == 1:
                return "weekly"
            if count == 2:
                return "biweekly"
            if count >= 4:
                return "monthly"
        if unit == "month":
            if count == 1:
                return "monthly"
            if count == 3:
                return "quarterly"
            if count >= 12:
                return "annually"
    return None


def _regex_pick_percent(text: str, label: str) -> float | None:
    pattern = rf"{label}[^0-9]{{0,40}}(\d{{1,3}}(?:\.\d{{1,2}})?)\s*%"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _regex_pick_rule_change(text: str) -> str | None:
    pattern = r"rules? (change|update)[^\n]{0,40}(daily|weekly|monthly|quarterly|annually|yearly)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(2).lower()


def _regex_extract_rules(text: str) -> dict:
    max_drawdown = (
        _regex_pick_percent(text, "max drawdown")
        or _regex_pick_percent(text, "maximum drawdown")
        or _regex_pick_percent(text, "overall drawdown")
        or _regex_pick_percent(text, "total drawdown")
        or _regex_pick_percent(text, "max loss")
        or _regex_pick_percent(text, "maximum loss")
        or _regex_pick_percent(text, "drawdown limit")
        or _regex_pick_percent(text, "loss limit")
    )
    daily_drawdown = (
        _regex_pick_percent(text, "daily drawdown")
        or _regex_pick_percent(text, "daily loss")
        or _regex_pick_percent(text, "daily loss limit")
        or _regex_pick_percent(text, "loss limit per day")
    )
    return {
        "payout_frequency": _regex_pick_frequency(text),
        "max_drawdown": max_drawdown,
        "daily_drawdown": daily_drawdown,
        "rule_changes_frequency": _regex_pick_rule_change(text),
    }


def _merge_missing_fields(base: dict, supplement: dict) -> dict:
    if not isinstance(base, dict):
        base = {}
    for key, value in supplement.items():
        if value is None:
            continue
        if base.get(key) in (None, "", [], {}):
            base[key] = value
    return base


def _reset_limits() -> None:
    global REQUEST_COUNT, START_TIME
    with REQUEST_LOCK:
        REQUEST_COUNT = 0
        START_TIME = time.monotonic()


def _bump_request() -> int:
    global REQUEST_COUNT
    with REQUEST_LOCK:
        REQUEST_COUNT += 1
        return REQUEST_COUNT


def _should_stop() -> bool:
    if START_TIME <= 0:
        return False
    if MAX_RUNTIME_S > 0 and (time.monotonic() - START_TIME) >= MAX_RUNTIME_S:
        return True
    if MAX_REQUESTS > 0 and REQUEST_COUNT >= MAX_REQUESTS:
        return True
    return False


def _log(*args):
    if VERBOSE:
        print("[crawl]", *args, flush=True)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _is_pdf(content_type: str, url: str, body: bytes) -> bool:
    lowered = (content_type or "").lower()
    if "application/pdf" in lowered:
        return True
    if url.lower().endswith(".pdf"):
        return True
    if body[:4] == b"%PDF":
        return True
    return False


def _pdf_to_text(pdf_bytes: bytes) -> str:
    if not ENABLE_PDF:
        return ""
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


def _render_with_playwright(url: str) -> bytes | None:
    if not ENABLE_JS_RENDER:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            for _ in range(3):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(800)
            page.wait_for_load_state("networkidle", timeout=15000)
            html = page.content().encode("utf-8", errors="ignore")
            browser.close()
            return html[:MAX_HTML_BYTES]
    except Exception:
        return None


def build_session() -> requests.Session:
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=max(1, RETRY_TOTAL - 1),
        status=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=retry, pool_connections=30, pool_maxsize=30)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


@dataclass
class FetchResult:
    status: int
    body: bytes
    content_type: str
    final_url: str
    truncated: bool


def fetch_limited(session: requests.Session, url: str, *, timeout: int = HTTP_TIMEOUT_S, max_bytes: int = MAX_HTML_BYTES) -> FetchResult:
    if _should_stop():
        return FetchResult(status=499, body=b"", content_type="", final_url=url, truncated=False)
    _bump_request()
    headers = {
        "User-Agent": "GPTI-DataBot/0.6 (+https://gpti.site)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7",
    }
    r = session.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
    status = int(r.status_code)
    ctype = r.headers.get("content-type", "")
    final_url = str(r.url)

    buf = bytearray()
    truncated = False
    try:
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) >= max_bytes:
                truncated = True
                buf = buf[:max_bytes]
                break
    finally:
        r.close()

    return FetchResult(status=status, body=bytes(buf), content_type=ctype, final_url=final_url, truncated=truncated)


def _safe_decode(html_bytes: bytes) -> str:
    return html_bytes[:MAX_HTML_BYTES].decode("utf-8", errors="ignore")


def html_to_text(html_bytes: bytes, *, max_chars: int = MAX_TEXT_CHARS) -> str:
    html = _safe_decode(html_bytes)
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        return f"[parse_error] {str(e)[:200]}"
    for tag in soup(["script","style","noscript","svg"]):
        try:
            tag.decompose()
        except Exception:
            pass
    return (soup.get_text(" ", strip=True) or "")[:max_chars]


def extract_links_by_keywords(root: str, html_bytes: bytes, keywords: list[str], *, max_links: int = MAX_LINKS) -> list[str]:
    html = _safe_decode(html_bytes)
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    try:
        links = [a.get("href") for a in soup.select("a[href]")]
    except Exception:
        return []
    links = [l for l in links if l and not l.startswith(("#","mailto:","javascript:"))]
    root_host = urlparse(root).netloc.lower()
    abs_links = [urljoin(root, l) for l in links]

    out: list[str] = []
    for u in abs_links:
        if urlparse(u).netloc.lower() != root_host:
            continue
        low = u.lower()
        if any(k in low for k in keywords):
            if u not in out:
                out.append(u)
    return out[:max_links]


def _expand_candidates(session: requests.Session, root: str, seeds: list[str], keywords: list[str]) -> list[str]:
    if CRAWL_DEPTH <= 0:
        return seeds
    seen = set(seeds)
    frontier = list(seeds)
    depth = 0
    while frontier and depth < CRAWL_DEPTH:
        next_frontier: list[str] = []
        for url in frontier[:MAX_DEEP_LINKS]:
            fr = fetch_limited(session, url, timeout=HTTP_TIMEOUT_S, max_bytes=MAX_HTML_BYTES)
            if fr.status >= 400 or not fr.body:
                continue
            for link in extract_links_by_keywords(root, fr.body, keywords, max_links=MAX_LINKS):
                if link not in seen:
                    seen.add(link)
                    next_frontier.append(link)
        frontier = next_frontier
        depth += 1
    return list(seen)


def sitemaps_from_robots(session: requests.Session, root: str) -> list[str]:
    try:
        fr = fetch_limited(session, urljoin(root, "/robots.txt"), timeout=15, max_bytes=200_000)
        if fr.status >= 400:
            return []
        txt = fr.body.decode("utf-8", errors="ignore")
        out = []
        for line in txt.splitlines():
            if line.lower().startswith("sitemap:"):
                sm = line.split(":", 1)[1].strip()
                if sm:
                    out.append(sm)
        return out[:10]
    except Exception:
        return []


def parse_sitemap_urls(xml_bytes: bytes) -> tuple[list[str], list[str]]:
    urls, children = [], []
    try:
        root = ET.fromstring(xml_bytes.decode("utf-8", errors="ignore"))
        tag = root.tag.lower()
        if tag.endswith("sitemapindex"):
            for loc in root.findall(".//{*}sitemap/{*}loc"):
                if loc.text:
                    children.append(loc.text.strip())
        elif tag.endswith("urlset"):
            for loc in root.findall(".//{*}url/{*}loc"):
                if loc.text:
                    urls.append(loc.text.strip())
    except Exception:
        return ([], [])
    return (urls, children)


def sitemap_urls(session: requests.Session, root: str, *, max_urls: int = SITEMAP_MAX_URLS) -> list[str]:
    candidates = []
    candidates.extend(sitemaps_from_robots(session, root))
    for p in SITEMAP_PATHS:
        candidates.append(urljoin(root, p))

    seen = set()
    out: list[str] = []

    queue = [c for c in candidates if c and c not in seen]
    depth = 0
    while queue and depth < 2 and len(out) < max_urls:
        nxt = []
        for sm in queue[:10]:
            if sm in seen:
                continue
            seen.add(sm)
            fr = fetch_limited(session, sm, timeout=20, max_bytes=MAX_HTML_BYTES)
            if fr.status >= 400 or not fr.body:
                continue
            urls, children = parse_sitemap_urls(fr.body)
            for u in urls:
                out.append(u)
                if len(out) >= max_urls:
                    break
            for c in children:
                if c and c not in seen:
                    nxt.append(c)
            if len(out) >= max_urls:
                break
        queue = nxt
        depth += 1
    return out[:max_urls]


def candidate_urls(session: requests.Session, root: str, home_bytes: bytes, *, kind: str) -> list[str]:
    if kind == "rules":
        kw = RULE_KEYWORDS
        fallback = RULE_FALLBACK_PATHS
    else:
        kw = PRICING_KEYWORDS
        fallback = PRICING_FALLBACK_PATHS

    out: list[str] = []
    for u in extract_links_by_keywords(root, home_bytes, kw):
        if u not in out:
            out.append(u)
    for p in fallback:
        u = urljoin(root, p)
        if u not in out:
            out.append(u)

    # sitemap hints
    for u in sitemap_urls(session, root):
        low = u.lower()
        if any(k in low for k in kw):
            if u not in out:
                out.append(u)

    out = _expand_candidates(session, root, out, kw)

    return out[:MAX_PAGES_PER_FIRM]


def _store_raw(m, *, firm_id: str, kind: str, body: bytes, content_type: str, ext: str | None = None) -> tuple[str, str]:
    h = sha256_bytes(body)
    if not ext:
        lowered = (content_type or "").lower()
        if "application/pdf" in lowered or body[:4] == b"%PDF":
            ext = "pdf"
        elif "text/html" in lowered:
            ext = "html"
        else:
            ext = "bin"
    obj = f"raw/{firm_id}/{kind}/{h}.{ext}"
    put_bytes(m, RAW_BUCKET, obj, body, content_type=content_type or "application/octet-stream")
    return h, f"{RAW_BUCKET}/{obj}"


def _timed_fetch(session: requests.Session, conn, firm_id: str, url: str, *, label: str, cache: dict[str, FetchResult]) -> FetchResult:
    if url in cache:
        return cache[url]
    start = time.time()
    fr = fetch_limited(session, url, timeout=HTTP_TIMEOUT_S, max_bytes=MAX_HTML_BYTES)
    elapsed = time.time() - start
    if elapsed >= SLOW_DOMAIN_S:
        insert_datapoint(
            conn,
            firm_id=firm_id,
            key="slow_domain",
            value_json={"url": url, "label": label, "seconds": round(elapsed, 2)},
            value_text=str(round(elapsed, 2)),
            source_url=url,
            evidence_hash=None,
        )
    cache[url] = fr
    return fr


def crawl_firm(f: dict) -> None:
    if _should_stop():
        return
    session = build_session()
    m = minio_client()
    cache: dict[str, FetchResult] = {}
    firm_start = time.monotonic()
    js_renders = 0

    with connect() as conn:
        firm_id = f["firm_id"]
        root = (f.get("website_root") or "").strip()
        if not root:
            return

        _log("Crawling firm:", firm_id, root)

        try:
            if MAX_DOMAIN_S > 0 and (time.monotonic() - firm_start) >= MAX_DOMAIN_S:
                return
            home = _timed_fetch(session, conn, firm_id, root, label="home", cache=cache)
            if home.status >= 400:
                insert_datapoint(conn, firm_id=firm_id, key="http_error",
                                 value_json={"url": root, "status": home.status},
                                 value_text=str(home.status), source_url=root, evidence_hash=None)
                return

            hh, hpath = _store_raw(m, firm_id=firm_id, kind="home", body=home.body, content_type=home.content_type)
            insert_evidence(conn, firm_id=firm_id, key="home_html", source_url=home.final_url, sha256=hh,
                            excerpt=None, raw_object_path=hpath)

            # DISCOVERY
            rule_candidates = candidate_urls(session, root, home.body, kind="rules")
            pricing_candidates = candidate_urls(session, root, home.body, kind="pricing")
            insert_datapoint(conn, firm_id=firm_id, key="discovered_links",
                             value_json={"rules": rule_candidates[:25], "pricing": pricing_candidates[:25]},
                             value_text=None, source_url=home.final_url, evidence_hash=hh)

            # RULES EXTRACTION
            got_rules = False
            for ru in rule_candidates[:MAX_RULE_PAGES]:
                if MAX_DOMAIN_S > 0 and (time.monotonic() - firm_start) >= MAX_DOMAIN_S:
                    break
                _log("Trying rules URL:", ru)
                try:
                    page = _timed_fetch(session, conn, firm_id, ru, label="rules", cache=cache)
                    if page.status >= 400:
                        continue
                    is_pdf = _is_pdf(page.content_type, page.final_url, page.body)
                    rh, rpath = _store_raw(m, firm_id=firm_id, kind="rules", body=page.body, content_type=page.content_type)
                    evidence_key = "rules_pdf" if is_pdf else "rules_html"
                    insert_evidence(conn, firm_id=firm_id, key=evidence_key, source_url=page.final_url, sha256=rh,
                                    excerpt=None, raw_object_path=rpath)

                    text = _pdf_to_text(page.body) if is_pdf else html_to_text(page.body)
                    if ENABLE_JS_RENDER and (not text or len(text) < MIN_TEXT_CHARS) and not is_pdf and js_renders < MAX_JS_PAGES:
                        rendered = _render_with_playwright(page.final_url)
                        if rendered:
                            js_renders += 1
                            rrh, rrpath = _store_raw(m, firm_id=firm_id, kind="rules", body=rendered, content_type="text/html", ext="html")
                            insert_evidence(conn, firm_id=firm_id, key="rules_html", source_url=page.final_url, sha256=rrh,
                                            excerpt=None, raw_object_path=rrpath)
                            text = html_to_text(rendered)
                    _log("LLM prompt length (rules):", len(text))
                    try:
                        extracted = extract_rules(text, model=RULES_MODEL)
                    except Exception as e:
                        extracted = {"error": str(e)[:300]}

                    extracted = _merge_missing_fields(extracted, _regex_extract_rules(text))

                    insert_datapoint(conn, firm_id=firm_id, key="rules_extracted_v0",
                                     value_json=extracted, value_text=None, source_url=page.final_url, evidence_hash=rh)
                    if any(extracted.get(k) not in (None, "", [], {}) for k in ("payout_frequency", "max_drawdown", "daily_drawdown")):
                        got_rules = True
                        break
                except Exception as e:
                    insert_datapoint(conn, firm_id=firm_id, key="rules_extract_error",
                                     value_json={"error": str(e)[:500]}, value_text=str(e)[:500],
                                     source_url=ru, evidence_hash=None)
                    _log("Extraction error from", ru, ":", str(e)[:100])
                    continue

            if not got_rules:
                text = html_to_text(home.body)
                _log("LLM prompt length (rules fallback):", len(text))
                try:
                    extracted = extract_rules(text, model=RULES_MODEL)
                except Exception as e:
                    extracted = {"error": str(e)[:300]}

                extracted = _merge_missing_fields(extracted, _regex_extract_rules(text))

                insert_datapoint(conn, firm_id=firm_id, key="rules_extracted_from_home_v0",
                                 value_json=extracted, value_text=None, source_url=home.final_url, evidence_hash=hh)

            # PRICING EXTRACTION
            got_pricing = False
            for pu in pricing_candidates[:MAX_PRICING_PAGES]:
                if MAX_DOMAIN_S > 0 and (time.monotonic() - firm_start) >= MAX_DOMAIN_S:
                    break
                _log("Trying pricing URL:", pu)
                try:
                    page = _timed_fetch(session, conn, firm_id, pu, label="pricing", cache=cache)
                    if page.status >= 400:
                        continue
                    is_pdf = _is_pdf(page.content_type, page.final_url, page.body)
                    ph, ppath = _store_raw(m, firm_id=firm_id, kind="pricing", body=page.body, content_type=page.content_type)
                    evidence_key = "pricing_pdf" if is_pdf else "pricing_html"
                    insert_evidence(conn, firm_id=firm_id, key=evidence_key, source_url=page.final_url, sha256=ph,
                                    excerpt=None, raw_object_path=ppath)

                    text = _pdf_to_text(page.body) if is_pdf else html_to_text(page.body)
                    if ENABLE_JS_RENDER and (not text or len(text) < MIN_TEXT_CHARS) and not is_pdf and js_renders < MAX_JS_PAGES:
                        rendered = _render_with_playwright(page.final_url)
                        if rendered:
                            js_renders += 1
                            rrh, rrpath = _store_raw(m, firm_id=firm_id, kind="pricing", body=rendered, content_type="text/html", ext="html")
                            insert_evidence(conn, firm_id=firm_id, key="pricing_html", source_url=page.final_url, sha256=rrh,
                                            excerpt=None, raw_object_path=rrpath)
                            text = html_to_text(rendered)
                    _log("LLM prompt length (pricing):", len(text))
                    try:
                        extracted = extract_pricing(text, model=PRICING_MODEL)
                    except Exception as e:
                        extracted = {"error": str(e)[:300]}

                    extracted = _merge_missing_fields(extracted, _regex_extract_rules(text))

                    insert_datapoint(conn, firm_id=firm_id, key="pricing_extracted_v0",
                                     value_json=extracted, value_text=None, source_url=page.final_url, evidence_hash=ph)
                    if any(extracted.get(k) not in (None, "", [], {}) for k in ("payout_frequency", "max_drawdown", "daily_drawdown")):
                        got_pricing = True
                        break
                except Exception as e:
                    insert_datapoint(conn, firm_id=firm_id, key="pricing_extract_error",
                                     value_json={"error": str(e)[:500]}, value_text=str(e)[:500],
                                     source_url=pu, evidence_hash=None)
                    _log("Extraction error from", pu, ":", str(e)[:100])
                    continue

            if not got_pricing:
                text = html_to_text(home.body)
                _log("LLM prompt length (pricing fallback):", len(text))
                try:
                    extracted = extract_pricing(text, model=PRICING_MODEL)
                except Exception as e:
                    extracted = {"error": str(e)[:300]}

                extracted = _merge_missing_fields(extracted, _regex_extract_rules(text))

                insert_datapoint(conn, firm_id=firm_id, key="pricing_extracted_from_home_v0",
                                 value_json=extracted, value_text=None, source_url=home.final_url, evidence_hash=hh)

            time.sleep(SLEEP_S)

        except Exception as e:
            insert_datapoint(conn, firm_id=firm_id, key="crawl_error",
                             value_json={"error": str(e)[:500]}, value_text=str(e)[:500],
                             source_url=root, evidence_hash=None)
            _log("Fatal crawl error for", firm_id, ":", str(e)[:100])
            return


def crawl_once(*, limit: int = 20) -> None:
    _reset_limits()
    with connect() as conn:
        firms = fetch_firms(conn, limit=limit)

    if CRAWL_WORKERS <= 1:
        for f in firms:
            if _should_stop():
                break
            crawl_firm(f)
        return

    with ThreadPoolExecutor(max_workers=CRAWL_WORKERS) as executor:
        futures = [executor.submit(crawl_firm, f) for f in firms]
        for future in as_completed(futures):
            if _should_stop():
                break
            try:
                future.result()
            except Exception as e:
                _log("Worker error:", str(e)[:200])