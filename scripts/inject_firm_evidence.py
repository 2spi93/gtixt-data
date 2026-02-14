#!/usr/bin/env python3
"""
Inject rules/pricing evidence for target firms by crawling their main and candidate pages.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import psycopg
import requests
from bs4 import BeautifulSoup
from gpti_bot.db import insert_evidence
from gpti_bot.minio import client as minio_client, put_bytes

TARGET_FILE = "/opt/gpti/gpti-data-bot/data/target_firm_urls.txt"
SECONDARY_FILE = "/opt/gpti/gpti-data-bot/scripts/target_firm_urls.txt"
DEFAULT_ENV = "/opt/gpti/docker/.env"
RAW_BUCKET = "gpti-raw"
MAX_HTML_BYTES = int(os.getenv("GPTI_MAX_HTML_BYTES", "5000000"))
MAX_PAGES = int(os.getenv("GPTI_INJECT_MAX_PAGES", "12"))
USE_PLAYWRIGHT = os.getenv("GPTI_INJECT_USE_PLAYWRIGHT", "0") == "1"
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("GPTI_INJECT_PLAYWRIGHT_TIMEOUT_MS", "15000"))

RULE_CANDIDATES = [
    "rules",
    "trading-rules",
    "trading-objectives",
    "objectives",
    "trading-conditions",
    "risk",
    "limits",
    "drawdown",
    "loss",
    "faq",
    "help",
    "support",
    "terms",
    "policy",
    "payout",
    "withdrawal",
    "agreement",
    "legal",
    "kyc",
    "refund",
]
PRICING_CANDIDATES = [
    "pricing",
    "plans",
    "fees",
    "challenge",
    "evaluation",
    "accounts",
    "packages",
    "profit-split",
    "funding",
]
PROFILE_CANDIDATES = [
    "about",
    "about-us",
    "aboutus",
    "company",
    "our-story",
    "our-team",
    "team",
    "leadership",
    "contact",
    "contact-us",
    "contactus",
    "who-we-are",
    "who-we-are",
    "legal",
    "imprint",
]

DB_URL = os.getenv("DATABASE_URL", "postgresql://gpti:superpassword@localhost:5434/gpti")


def _load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _load_urls() -> list[str]:
    for path in (TARGET_FILE, SECONDARY_FILE):
        p = Path(path)
        if not p.exists():
            continue
        return [
            line.strip()
            for line in p.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    raise FileNotFoundError(
        f"Missing target URL list. Looked for {TARGET_FILE} and {SECONDARY_FILE}."
    )


def normalize_host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def host_to_brand(host: str) -> str:
    return host.replace("-", " ").replace(".", " ").strip().title() or host


def host_fallbacks(host: str) -> list[str]:
    parts = host.split(".")
    fallbacks = [host]
    if len(parts) > 2:
        fallbacks.append(".".join(parts[-2:]))
    if len(parts) > 3:
        fallbacks.append(".".join(parts[-3:]))
    return list(dict.fromkeys(fallbacks))


def extract_candidate_links(html: bytes, base_url: str) -> list[str]:
    try:
        soup = BeautifulSoup(html.decode("utf-8", errors="ignore"), "html.parser")
    except Exception:
        return []
    keywords = set(RULE_CANDIDATES + PRICING_CANDIDATES + PROFILE_CANDIDATES)
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#"):
            continue
        text = (a.get_text(" ", strip=True) or "").lower()
        target = href.lower()
        if any(k in target or k in text for k in keywords):
            links.append(urljoin(base_url, href))
    return links


def get_candidate_urls(base_url, homepage_html: bytes | None):
    urls = [base_url]
    for path in RULE_CANDIDATES + PRICING_CANDIDATES + PROFILE_CANDIDATES:
        urls.append(urljoin(base_url, f"/{path}"))
    if homepage_html:
        urls.extend(extract_candidate_links(homepage_html, base_url))
    seen = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    return seen[:MAX_PAGES]


def fetch_content(url: str) -> tuple[bytes, str] | None:
    def _render_with_playwright(target_url: str) -> bytes | None:
        if not USE_PLAYWRIGHT:
            return None
        node_script = f"""
const {{ chromium }} = require('playwright');
(async()=>{{
  const browser = await chromium.launch({{ headless: true }});
  const page = await browser.newPage();
  await page.goto({json.dumps(target_url)}, {{ waitUntil: 'networkidle', timeout: {PLAYWRIGHT_TIMEOUT_MS} }});
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
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.encode("utf-8")[:MAX_HTML_BYTES]

    def _extract_redirect_target(html: bytes) -> str | None:
        try:
            text = html.decode("utf-8", errors="ignore")
        except Exception:
            return None
        match = re.search(r"window\.location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"url=([^;\"']+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("'\"")
        return None

    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent": "GTIXT EvidenceBot/1.0"})
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get("Content-Type", "")
        content = resp.content[:MAX_HTML_BYTES]
        if "application/pdf" in content_type:
            return content, content_type
        if "text/html" not in content_type:
            return None
        target = _extract_redirect_target(content)
        if target:
            try:
                redirect_url = urljoin(url, target)
                follow = requests.get(redirect_url, timeout=12, headers={"User-Agent": "GTIXT EvidenceBot/1.0"})
                follow_type = follow.headers.get("Content-Type", "")
                if follow.status_code == 200 and "application/pdf" in follow_type:
                    return follow.content[:MAX_HTML_BYTES], follow_type
                if follow.status_code == 200 and "text/html" in follow_type:
                    return follow.content[:MAX_HTML_BYTES], follow_type
            except Exception:
                return content, content_type
        if USE_PLAYWRIGHT and len(content) < 2000:
            rendered = _render_with_playwright(url)
            if rendered:
                return rendered, "text/html"
        return content, content_type
    except Exception:
        return None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inject_evidence():
    _load_env_file(DEFAULT_ENV)
    os.environ.setdefault("MINIO_ENDPOINT", os.getenv("MINIO_ENDPOINT", "http://localhost:9002"))
    if not os.getenv("MINIO_ACCESS_KEY"):
        os.environ.setdefault("MINIO_ACCESS_KEY", os.getenv("MINIO_ROOT_USER", ""))
    if not os.getenv("MINIO_SECRET_KEY"):
        os.environ.setdefault("MINIO_SECRET_KEY", os.getenv("MINIO_ROOT_PASSWORD", ""))
    m = minio_client()
    conn = psycopg.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()
    urls = _load_urls()
    cur.execute("SELECT firm_id, website_root FROM firms WHERE website_root IS NOT NULL")
    firm_map: dict[str, str] = {}
    for firm_id, website_root in cur.fetchall():
        host = normalize_host(website_root)
        if host:
            firm_map[host] = firm_id
    injected = 0
    for url in urls:
        host = normalize_host(url)
        firm_id = None
        for h in host_fallbacks(host):
            firm_id = firm_map.get(h)
            if firm_id:
                break
        if not firm_id:
            firm_id = host.replace(".", "").replace("-", "")
            brand_name = host_to_brand(host)
            cur.execute(
                """
                INSERT INTO firms (firm_id, brand_name, website_root, model_type, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (firm_id) DO UPDATE SET
                    brand_name = EXCLUDED.brand_name,
                    website_root = EXCLUDED.website_root,
                    model_type = EXCLUDED.model_type,
                    status = EXCLUDED.status,
                    updated_at = now();
                """,
                (firm_id, brand_name, url, "CFD_FX", "candidate"),
            )
            firm_map[host] = firm_id

        home_content = fetch_content(url)
        home_html = home_content[0] if home_content and "text/html" in home_content[1] else None
        candidates = get_candidate_urls(url, home_html)
        for c_url in candidates:
            if c_url == url:
                content = home_content
            else:
                content = fetch_content(c_url)
            if not content:
                continue
            payload, content_type = content
            is_pdf = "application/pdf" in content_type or c_url.lower().endswith(".pdf")
            ext = "pdf" if is_pdf else "html"
            obj_key = f"evidence/{firm_id}/{int(time.time())}_{c_url.split('/')[-1]}.{ext}"
            put_bytes(m, RAW_BUCKET, obj_key, payload, content_type=content_type)
            # Insert evidence record
            is_rules = any(k in c_url for k in RULE_CANDIDATES)
            is_pricing = any(k in c_url for k in PRICING_CANDIDATES)
            is_profile = any(k in c_url for k in PROFILE_CANDIDATES)
            if is_profile and not is_rules and not is_pricing:
                key = "profile_pdf" if is_pdf else "profile_html"
            else:
                if is_pdf:
                    key = "rules_pdf" if is_rules else "pricing_pdf"
                else:
                    key = "rules_html" if is_rules else "pricing_html"
            sha = sha256_bytes(payload)
            insert_evidence(
                conn,
                firm_id=firm_id,
                key=key,
                source_url=c_url,
                sha256=sha,
                excerpt=None,
                raw_object_path=f"s3://{RAW_BUCKET}/{obj_key}",
            )
            injected += 1
            print(f"[inject] {firm_id} {key} {c_url} -> {obj_key}")
    print(f"[inject] injected {injected} evidence objects.")


if __name__ == "__main__":
    inject_evidence()
