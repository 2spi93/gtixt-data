from __future__ import annotations

import hashlib
import io
import os
import re
import time
import threading
import json
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
EXTERNAL_JS_RENDER = os.getenv("GPTI_EXTERNAL_JS_RENDER", "0") == "1"
EXTERNAL_JS_MAX_PAGES = int(os.getenv("GPTI_EXTERNAL_JS_MAX_PAGES", "2"))
EXTERNAL_MIN_HTML_BYTES = int(os.getenv("GPTI_EXTERNAL_MIN_HTML_BYTES", "400"))
OCR_ENABLED = os.getenv("GPTI_OCR_ENABLED", "0") == "1"
OCR_MAX_PAGES = int(os.getenv("GPTI_OCR_MAX_PAGES", "2"))
XHR_SNIFF_ENABLED = os.getenv("GPTI_XHR_SNIFF", "0") == "1"
XHR_MAX_ITEMS = int(os.getenv("GPTI_XHR_MAX_ITEMS", "12"))
XHR_MAX_BYTES = int(os.getenv("GPTI_XHR_MAX_BYTES", "200000"))
XHR_WAIT_MS = int(os.getenv("GPTI_XHR_WAIT_MS", "8000"))
CAPTCHA_MARKERS = [
    "captcha",
    "g-recaptcha",
    "recaptcha",
    "hcaptcha",
    "cf-challenge",
    "cloudflare",
    "verify you are human",
]
DOMAIN_DELAY_S = float(os.getenv("GPTI_DOMAIN_DELAY_S", "0.4"))
DEFAULT_USER_AGENT = os.getenv(
    "GPTI_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
)
FIRM_SEED_PATH = os.getenv(
    "GPTI_FIRM_SEED_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "seeds", "firm_url_seeds.json")),
)
_FIRM_SEED_URLS: dict[str, dict] | None = None

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
}

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
LAST_REQUEST_AT: dict[str, float] = {}

_CRAWL_OVERRIDE_KEYS = {
    "MAX_HTML_BYTES",
    "MAX_TEXT_CHARS",
    "MAX_PDF_CHARS",
    "MAX_LINKS",
    "SLEEP_S",
    "HTTP_TIMEOUT_S",
    "CRAWL_WORKERS",
    "SLOW_DOMAIN_S",
    "MAX_DOMAIN_S",
    "MAX_PAGES_PER_FIRM",
    "SITEMAP_MAX_URLS",
    "MAX_RULE_PAGES",
    "MAX_PRICING_PAGES",
    "CRAWL_DEPTH",
    "MAX_DEEP_LINKS",
    "MAX_JS_PAGES",
    "MIN_TEXT_CHARS",
    "ENABLE_JS_RENDER",
    "ENABLE_PDF",
}


def apply_crawl_overrides(overrides: dict) -> dict:
    previous: dict = {}
    for key, value in (overrides or {}).items():
        if key not in _CRAWL_OVERRIDE_KEYS:
            continue
        previous[key] = globals().get(key)
        globals()[key] = value
    return previous


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


def _throttle_request(url: str) -> None:
    if DOMAIN_DELAY_S <= 0:
        return
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return
    if not host:
        return
    with REQUEST_LOCK:
        last = LAST_REQUEST_AT.get(host)
        now = time.monotonic()
        if last is not None:
            wait_s = DOMAIN_DELAY_S - (now - last)
            if wait_s > 0:
                time.sleep(wait_s)
        LAST_REQUEST_AT[host] = time.monotonic()


def _repair_url_candidates(url: str) -> list[str]:
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


def _fetch_with_repairs(
    session: requests.Session,
    url: str,
    *,
    timeout: int,
    max_bytes: int,
) -> FetchResult:
    fr = fetch_limited(session, url, timeout=timeout, max_bytes=max_bytes)
    if fr.status < 400:
        return fr
    for candidate in _repair_url_candidates(url):
        if candidate == url:
            continue
        retry = fetch_limited(session, candidate, timeout=timeout, max_bytes=max_bytes)
        if retry.status < 400:
            return retry
    return fr


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


def _seed_urls_for_firm(firm_id: str, root: str, kind: str) -> list[str]:
    data = _load_firm_seed_urls()
    entry = data.get((firm_id or "").lower())
    if not isinstance(entry, dict):
        return []
    seeds = entry.get(kind) or entry.get("all") or []
    if not isinstance(seeds, list):
        return []
    out: list[str] = []
    for u in seeds:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u:
            continue
        out.append(urljoin(root, u) if u.startswith("/") else u)
    return out


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
    if not text and OCR_ENABLED:
        text = _pdf_to_text_ocr(pdf_bytes)
    if len(text) > MAX_PDF_CHARS:
        text = text[:MAX_PDF_CHARS]
    return text


def _pdf_to_text_ocr(pdf_bytes: bytes) -> str:
    if not OCR_ENABLED:
        return ""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except Exception:
        return ""
    try:
        images = convert_from_bytes(pdf_bytes, first_page=1, last_page=OCR_MAX_PAGES)
    except Exception:
        return ""
    parts: list[str] = []
    for img in images:
        try:
            parts.append(pytesseract.image_to_string(img) or "")
        except Exception:
            continue
    return " ".join(parts).strip()


def _looks_like_captcha(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in CAPTCHA_MARKERS)


def _captcha_kind(text: str) -> str:
    lowered = (text or "").lower()
    if "hcaptcha" in lowered:
        return "hcaptcha"
    if "g-recaptcha" in lowered or "recaptcha" in lowered:
        return "recaptcha"
    if "cloudflare" in lowered or "cf-challenge" in lowered:
        return "cloudflare"
    return "captcha"


def _extract_captcha_sitekey(text: str) -> str | None:
    match = re.search(r"data-sitekey=\"([a-zA-Z0-9_-]+)\"", text)
    if match:
        return match.group(1)
    return None


def _solve_recaptcha_2captcha(sitekey: str, page_url: str) -> str | None:
    api_key = os.getenv("GPTI_CAPTCHA_2CAPTCHA_KEY")
    if not api_key:
        return None
    try:
        create = requests.get(
            "https://2captcha.com/in.php",
            params={
                "key": api_key,
                "method": "userrecaptcha",
                "googlekey": sitekey,
                "pageurl": page_url,
                "json": 1,
            },
            timeout=15,
        )
        payload = create.json()
        if payload.get("status") != 1:
            return None
        captcha_id = payload.get("request")
        if not captcha_id:
            return None
        timeout_s = int(os.getenv("GPTI_CAPTCHA_TIMEOUT_S", "120"))
        poll_s = int(os.getenv("GPTI_CAPTCHA_POLL_S", "5"))
        elapsed = 0
        while elapsed < timeout_s:
            time.sleep(poll_s)
            elapsed += poll_s
            check = requests.get(
                "https://2captcha.com/res.php",
                params={
                    "key": api_key,
                    "action": "get",
                    "id": captcha_id,
                    "json": 1,
                },
                timeout=15,
            )
            data = check.json()
            if data.get("status") == 1:
                return data.get("request")
            if data.get("request") not in ("CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"):
                break
    except Exception:
        return None
    return None


def _render_with_playwright_meta(url: str) -> tuple[bytes | None, dict]:
    if not (ENABLE_JS_RENDER or EXTERNAL_JS_RENDER):
        return None, {"captcha_detected": False}
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None, {"captcha_detected": False}
    try:
        with sync_playwright() as p:
            proxy = os.getenv("GPTI_PROXY")
            launch_args = {"headless": True}
            if proxy:
                launch_args["proxy"] = {"server": proxy}
            browser = p.chromium.launch(**launch_args)
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            for _ in range(3):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(800)
            try:
                page.wait_for_load_state("networkidle", timeout=XHR_WAIT_MS)
            except Exception:
                page.wait_for_timeout(1200)
            html = page.content().encode("utf-8", errors="ignore")
            html_text = html.decode("utf-8", errors="ignore")
            meta = {
                "captcha_detected": _looks_like_captcha(html_text),
                "captcha_kind": _captcha_kind(html_text) if _looks_like_captcha(html_text) else None,
                "captcha_sitekey": _extract_captcha_sitekey(html_text),
                "captcha_solved": False,
                "captcha_solver": None,
            }
            if meta["captcha_detected"]:
                provider = (os.getenv("GPTI_CAPTCHA_PROVIDER") or "").lower()
                if provider == "2captcha" and meta.get("captcha_kind") == "recaptcha":
                    token = _solve_recaptcha_2captcha(meta.get("captcha_sitekey") or "", url)
                    meta["captcha_solver"] = "2captcha"
                    if token:
                        try:
                            page.evaluate(
                                """
                                (token) => {
                                  const el = document.querySelector('textarea[name="g-recaptcha-response"]');
                                  if (el) {
                                    el.value = token;
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                  }
                                  const form = el ? el.closest('form') : document.querySelector('form');
                                  if (form) { form.submit(); }
                                }
                                """,
                                token,
                            )
                            page.wait_for_timeout(2000)
                            try:
                                page.wait_for_load_state("networkidle", timeout=15000)
                            except Exception:
                                page.wait_for_timeout(1200)
                            html = page.content().encode("utf-8", errors="ignore")
                            html_text = html.decode("utf-8", errors="ignore")
                            meta["captcha_solved"] = not _looks_like_captcha(html_text)
                        except Exception:
                            pass
            browser.close()
            return html[:MAX_HTML_BYTES], meta
    except Exception:
        return None, {"captcha_detected": False}


def _render_with_playwright(url: str) -> bytes | None:
    rendered, _meta = _render_with_playwright_meta(url)
    return rendered


def _render_with_playwright_xhr(url: str) -> tuple[bytes | None, list[dict], dict]:
    if not ENABLE_JS_RENDER or not XHR_SNIFF_ENABLED:
        return None, [], {"captcha_detected": False}
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None, [], {"captcha_detected": False}
    try:
        xhr_items: list[dict] = []

        def handle_response(response) -> None:
            if len(xhr_items) >= XHR_MAX_ITEMS:
                return
            try:
                request = response.request
                if request.resource_type not in ("xhr", "fetch"):
                    return
                ctype = (response.headers.get("content-type") or "").lower()
                if "application/json" not in ctype and "text/json" not in ctype:
                    return
                try:
                    body = response.text()
                except Exception:
                    return
                if not body:
                    return
                if len(body) > XHR_MAX_BYTES:
                    body = body[:XHR_MAX_BYTES]
                xhr_items.append({
                    "url": response.url,
                    "body": body,
                })
            except Exception:
                return

        with sync_playwright() as p:
            proxy = os.getenv("GPTI_PROXY")
            launch_args = {"headless": True}
            if proxy:
                launch_args["proxy"] = {"server": proxy}
            browser = p.chromium.launch(**launch_args)
            page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
            page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
            page.on("response", handle_response)
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            for _ in range(3):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(800)
            try:
                page.wait_for_load_state("networkidle", timeout=XHR_WAIT_MS)
            except Exception:
                page.wait_for_timeout(1200)
            html = page.content().encode("utf-8", errors="ignore")
            html_text = html.decode("utf-8", errors="ignore")
            meta = {
                "captcha_detected": _looks_like_captcha(html_text),
                "captcha_kind": _captcha_kind(html_text) if _looks_like_captcha(html_text) else None,
                "captcha_sitekey": _extract_captcha_sitekey(html_text),
                "captcha_solved": False,
                "captcha_solver": None,
            }
            browser.close()
            return html[:MAX_HTML_BYTES], xhr_items, meta
    except Exception:
        return None, [], {"captcha_detected": False}
    try:
        with sync_playwright() as p:
            proxy = os.getenv("GPTI_PROXY")
            launch_args = {"headless": True}
            if proxy:
                launch_args["proxy"] = {"server": proxy}
            browser = p.chromium.launch(**launch_args)
            page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
            page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
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
    proxy = os.getenv("GPTI_PROXY") or os.getenv("GPTI_HTTP_PROXY")
    https_proxy = os.getenv("GPTI_HTTPS_PROXY") or proxy
    if proxy or https_proxy:
        s.proxies.update({
            "http": proxy or "",
            "https": https_proxy or proxy or "",
        })
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
    _throttle_request(url)
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr-FR;q=0.8,fr;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
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


def probe_url(
    session: requests.Session,
    url: str,
    *,
    allow_js: bool = False,
    min_html_bytes: int = 400,
    timeout_s: int | None = None,
) -> dict:
    timeout = HTTP_TIMEOUT_S if timeout_s is None else timeout_s
    result = {
        "ok": False,
        "status": None,
        "final_url": url,
        "content_type": "",
        "bytes": 0,
        "used_js": False,
        "captcha_detected": False,
        "captcha_kind": None,
    }
    try:
        fr = fetch_limited(session, url, timeout=timeout, max_bytes=MAX_HTML_BYTES)
    except Exception:
        fr = None

    if fr is not None:
        result.update(
            {
                "status": fr.status,
                "final_url": fr.final_url,
                "content_type": fr.content_type,
                "bytes": len(fr.body or b""),
            }
        )
        if fr.body:
            is_html = "text/html" in (fr.content_type or "").lower()
            html_text = fr.body.decode("utf-8", errors="ignore") if is_html else ""
            if is_html and html_text:
                result["captcha_detected"] = _looks_like_captcha(html_text)
                result["captcha_kind"] = _captcha_kind(html_text) if result["captcha_detected"] else None
            if fr.status < 400 and (not is_html or len(fr.body) >= min_html_bytes) and not result["captcha_detected"]:
                result["ok"] = True

    if result["ok"] or not allow_js:
        return result

    try:
        rendered, meta = _render_with_playwright_meta(url)
    except Exception:
        rendered, meta = None, {}
    if rendered:
        result.update(
            {
                "ok": len(rendered) >= min_html_bytes,
                "status": 200,
                "content_type": "text/html",
                "bytes": len(rendered),
                "used_js": True,
                "captcha_detected": bool(meta.get("captcha_detected")),
                "captcha_kind": meta.get("captcha_kind"),
            }
        )
        if result["captcha_detected"]:
            result["ok"] = False

    return result


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
        anchors = soup.select("a[href]")
    except Exception:
        return []
    root_host = urlparse(root).netloc.lower()
    scored: list[tuple[int, str]] = []

    for anchor in anchors:
        href = anchor.get("href")
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        url = urljoin(root, href)
        if urlparse(url).netloc.lower() != root_host:
            continue
        low_url = url.lower()
        if any(bad in low_url for bad in BLACKLIST_KEYWORDS):
            continue
        anchor_text = " ".join(anchor.stripped_strings).lower()
        score = 0
        if any(k in low_url for k in keywords):
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
    out: list[str] = []
    for _score, url in scored:
        if url not in out:
            out.append(url)
        if len(out) >= max_links:
            break
    return out


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


def candidate_urls(session: requests.Session, root: str, home_bytes: bytes, *, kind: str, firm_id: str | None = None) -> list[str]:
    if kind == "rules":
        kw = RULE_KEYWORDS
        fallback = RULE_FALLBACK_PATHS
    else:
        kw = PRICING_KEYWORDS
        fallback = PRICING_FALLBACK_PATHS

    out: list[str] = []
    if firm_id:
        for u in _seed_urls_for_firm(firm_id, root, kind):
            if u not in out:
                out.append(u)
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


def _record_captcha(conn, firm_id: str, url: str, label: str, meta: dict) -> None:
    if not meta or not meta.get("captcha_detected"):
        return
    insert_datapoint(
        conn,
        firm_id=firm_id,
        key="captcha_detected",
        value_json={
            "url": url,
            "label": label,
            "kind": meta.get("captcha_kind"),
            "sitekey": meta.get("captcha_sitekey"),
            "solver": meta.get("captcha_solver"),
            "solved": bool(meta.get("captcha_solved")),
        },
        value_text=None,
        source_url=url,
        evidence_hash=None,
    )


def fetch_external_evidence(firm_id: str, urls: list[str]) -> int:
    if not urls:
        return 0
    session = build_session()
    m = minio_client()
    stored = 0
    js_budget = EXTERNAL_JS_MAX_PAGES if EXTERNAL_JS_RENDER else 0

    with connect() as conn:
        for url in urls:
            stored_this = False
            try:
                fr = fetch_limited(session, url, timeout=HTTP_TIMEOUT_S, max_bytes=MAX_HTML_BYTES)
                if fr.status < 400 and fr.body:
                    is_html = "text/html" in (fr.content_type or "").lower()
                    too_small = is_html and len(fr.body) < EXTERNAL_MIN_HTML_BYTES
                    if not too_small:
                        is_pdf = _is_pdf(fr.content_type, fr.final_url, fr.body)
                        key = "external_pdf" if is_pdf else "external_html"
                        h, path = _store_raw(
                            m,
                            firm_id=firm_id,
                            kind="external",
                            body=fr.body,
                            content_type=fr.content_type,
                        )
                        insert_evidence(
                            conn,
                            firm_id=firm_id,
                            key=key,
                            source_url=fr.final_url,
                            sha256=h,
                            excerpt=None,
                            raw_object_path=path,
                        )
                        stored += 1
                        stored_this = True
            except Exception:
                stored_this = False

            if stored_this or js_budget <= 0:
                continue

            rendered = None
            meta: dict = {}
            try:
                rendered, meta = _render_with_playwright_meta(url)
            except Exception:
                rendered = None
                meta = {}
            if rendered:
                js_budget -= 1
                _record_captcha(conn, firm_id, url, "external", meta)
                h, path = _store_raw(
                    m,
                    firm_id=firm_id,
                    kind="external",
                    body=rendered,
                    content_type="text/html",
                )
                insert_evidence(
                    conn,
                    firm_id=firm_id,
                    key="external_html",
                    source_url=url,
                    sha256=h,
                    excerpt=None,
                    raw_object_path=path,
                )
                stored += 1

    return stored


def _timed_fetch(session: requests.Session, conn, firm_id: str, url: str, *, label: str, cache: dict[str, FetchResult]) -> FetchResult:
    if url in cache:
        return cache[url]
    start = time.time()
    fr = _fetch_with_repairs(session, url, timeout=HTTP_TIMEOUT_S, max_bytes=MAX_HTML_BYTES)
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
            if home.status >= 400 and ENABLE_JS_RENDER:
                rendered, meta = _render_with_playwright_meta(root)
                _record_captcha(conn, firm_id, root, "home", meta)
                if rendered:
                    home = FetchResult(
                        status=200,
                        body=rendered,
                        content_type="text/html",
                        final_url=root,
                        truncated=len(rendered) >= MAX_HTML_BYTES,
                    )
            if home.status >= 400:
                insert_datapoint(
                    conn,
                    firm_id=firm_id,
                    key="http_error",
                    value_json={"url": root, "status": home.status},
                    value_text=str(home.status),
                    source_url=root,
                    evidence_hash=None,
                )
                return

            hh, hpath = _store_raw(m, firm_id=firm_id, kind="home", body=home.body, content_type=home.content_type)
            insert_evidence(conn, firm_id=firm_id, key="home_html", source_url=home.final_url, sha256=hh,
                            excerpt=None, raw_object_path=hpath)

            if ENABLE_JS_RENDER and XHR_SNIFF_ENABLED:
                rendered, xhr_items, meta = _render_with_playwright_xhr(home.final_url)
                _record_captcha(conn, firm_id, home.final_url, "home_xhr", meta)
                if rendered and rendered != home.body:
                    rrh, rrpath = _store_raw(m, firm_id=firm_id, kind="home", body=rendered, content_type="text/html")
                    insert_evidence(conn, firm_id=firm_id, key="home_html", source_url=home.final_url, sha256=rrh,
                                    excerpt=None, raw_object_path=rrpath)
                for item in xhr_items:
                    body = item.get("body") or ""
                    if not body:
                        continue
                    raw = body.encode("utf-8", errors="ignore")
                    xh, xpath = _store_raw(m, firm_id=firm_id, kind="xhr", body=raw, content_type="application/json", ext="json")
                    insert_evidence(conn, firm_id=firm_id, key="xhr_json", source_url=item.get("url") or home.final_url,
                                    sha256=xh, excerpt=None, raw_object_path=xpath)

            # DISCOVERY
            rule_candidates = candidate_urls(session, root, home.body, kind="rules", firm_id=firm_id)
            pricing_candidates = candidate_urls(session, root, home.body, kind="pricing", firm_id=firm_id)
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
                    if page.status >= 400 and ENABLE_JS_RENDER:
                        rendered, meta = _render_with_playwright_meta(ru)
                        _record_captcha(conn, firm_id, ru, "rules", meta)
                        if rendered:
                            page = FetchResult(
                                status=200,
                                body=rendered,
                                content_type="text/html",
                                final_url=ru,
                                truncated=len(rendered) >= MAX_HTML_BYTES,
                            )
                    if page.status >= 400:
                        continue
                    is_pdf = _is_pdf(page.content_type, page.final_url, page.body)
                    rh, rpath = _store_raw(m, firm_id=firm_id, kind="rules", body=page.body, content_type=page.content_type)
                    evidence_key = "rules_pdf" if is_pdf else "rules_html"
                    insert_evidence(conn, firm_id=firm_id, key=evidence_key, source_url=page.final_url, sha256=rh,
                                    excerpt=None, raw_object_path=rpath)

                    text = _pdf_to_text(page.body) if is_pdf else html_to_text(page.body)
                    if ENABLE_JS_RENDER and (not text or len(text) < MIN_TEXT_CHARS) and not is_pdf and js_renders < MAX_JS_PAGES:
                        rendered, meta = _render_with_playwright_meta(page.final_url)
                        _record_captcha(conn, firm_id, page.final_url, "rules", meta)
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
                    if page.status >= 400 and ENABLE_JS_RENDER:
                        rendered, meta = _render_with_playwright_meta(pu)
                        _record_captcha(conn, firm_id, pu, "pricing", meta)
                        if rendered:
                            page = FetchResult(
                                status=200,
                                body=rendered,
                                content_type="text/html",
                                final_url=pu,
                                truncated=len(rendered) >= MAX_HTML_BYTES,
                            )
                    if page.status >= 400:
                        continue
                    is_pdf = _is_pdf(page.content_type, page.final_url, page.body)
                    ph, ppath = _store_raw(m, firm_id=firm_id, kind="pricing", body=page.body, content_type=page.content_type)
                    evidence_key = "pricing_pdf" if is_pdf else "pricing_html"
                    insert_evidence(conn, firm_id=firm_id, key=evidence_key, source_url=page.final_url, sha256=ph,
                                    excerpt=None, raw_object_path=ppath)

                    text = _pdf_to_text(page.body) if is_pdf else html_to_text(page.body)
                    if ENABLE_JS_RENDER and (not text or len(text) < MIN_TEXT_CHARS) and not is_pdf and js_renders < MAX_JS_PAGES:
                        rendered, meta = _render_with_playwright_meta(page.final_url)
                        _record_captcha(conn, firm_id, page.final_url, "pricing", meta)
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


def crawl_firm_by_id(firm_id: str) -> bool:
    _reset_limits()
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT firm_id, website_root
            FROM firms
            WHERE firm_id = %s
            LIMIT 1
            """,
            (firm_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        firm = {"firm_id": row[0], "website_root": row[1]}

    crawl_firm(firm)
    return True