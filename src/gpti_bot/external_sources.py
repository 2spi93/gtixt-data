from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple
import re


@dataclass(frozen=True)
class SourceDef:
    name: str
    trust: int
    patterns: List[str]


SOURCES: List[SourceDef] = [
    SourceDef(
        name="thetrustedprop",
        trust=5,
        patterns=[
            "https://thetrustedprop.com/{slug}/",
            "https://thetrustedprop.com/{slug}-challenge-rules/",
            "https://thetrustedprop.com/{slug}-rules/",
        ],
    ),
    SourceDef(
        name="tradingfinder",
        trust=4,
        patterns=[
            "https://www.tradingfinder.com/prop-firms/{slug}-rules/",
            "https://www.tradingfinder.com/prop-firms/{slug}/",
        ],
    ),
    SourceDef(
        name="proptradingfirms",
        trust=3,
        patterns=[
            "https://proptradingfirms.net/prop-firms/{slug}/",
            "https://proptradingfirms.net/prop-firm/{slug}/",
        ],
    ),
    SourceDef(
        name="propfirmmatch",
        trust=3,
        patterns=[
            "https://propfirmmatch.com/prop-firm/{slug}/",
            "https://propfirmmatch.com/prop-firm-challenges/{slug}/",
        ],
    ),
]


def _slugify(text: str) -> str:
    value = (text or "").strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def _strip_tld(value: str) -> str:
    value = (value or "").strip().lower()
    if "." not in value:
        return value
    return value.split(".")[0]


COMMON_SUFFIXES = {
    "prop",
    "propfirm",
    "funded",
    "trading",
    "capital",
    "markets",
    "group",
}


def _expand_slug(slug: str) -> List[str]:
    out: List[str] = []
    if not slug:
        return out
    out.append(slug)
    tokens = slug.split("-")
    if tokens and tokens[-1] in COMMON_SUFFIXES and len(tokens) > 1:
        out.append("-".join(tokens[:-1]))
    if "prop" in tokens and len(tokens) > 1:
        without_prop = [t for t in tokens if t != "prop"]
        if without_prop:
            out.append("-".join(without_prop))
    if "-" in slug:
        out.append(slug.replace("-", ""))
    for suffix in ("prop-firm", "propfirm", "prop-trading-firm"):
        out.append(f"{slug}-{suffix}")
    return list(dict.fromkeys(out))


def slug_variants(firm_name: str | None, firm_id: str | None, website_root: str | None) -> List[str]:
    candidates = []
    for raw in (firm_name or "", firm_id or "", _strip_tld(website_root or "")):
        slug = _slugify(raw)
        if slug:
            candidates.extend(_expand_slug(slug))
    return list(dict.fromkeys(candidates))


def generate_candidates(
    firm_name: str | None,
    firm_id: str | None,
    website_root: str | None,
) -> List[Tuple[str, int]]:
    slugs = slug_variants(firm_name, firm_id, website_root)
    if not slugs:
        return []
    candidates: List[Tuple[str, int]] = []
    for source in SOURCES:
        for slug in slugs:
            for pattern in source.patterns:
                url = pattern.format(slug=slug)
                score = source.trust
                if firm_id and slug == _slugify(firm_id):
                    score += 1
                candidates.append((url, score))
    return candidates


def rank_candidates(candidates: Iterable[Tuple[str, int]], limit: int = 10) -> List[str]:
    ordered = sorted(candidates, key=lambda item: item[1], reverse=True)
    out: List[str] = []
    for url, _score in ordered:
        if url not in out:
            out.append(url)
        if len(out) >= limit:
            break
    return out


def rank_candidates_diverse(
    firm_name: str | None,
    firm_id: str | None,
    website_root: str | None,
    *,
    limit: int = 10,
    per_slug: int = 2,
) -> List[str]:
    slugs = slug_variants(firm_name, firm_id, website_root)
    if not slugs:
        return []
    candidates: List[Tuple[str, int, str]] = []
    for source in SOURCES:
        for slug in slugs:
            for pattern in source.patterns:
                url = pattern.format(slug=slug)
                score = source.trust
                if firm_id and slug == _slugify(firm_id):
                    score += 1
                candidates.append((url, score, slug))
    ordered = sorted(candidates, key=lambda item: item[1], reverse=True)
    out: List[str] = []
    slug_counts: dict[str, int] = {}
    for url, _score, slug in ordered:
        if url in out:
            continue
        if slug_counts.get(slug, 0) >= per_slug:
            continue
        out.append(url)
        slug_counts[slug] = slug_counts.get(slug, 0) + 1
        if len(out) >= limit:
            break
    return out
