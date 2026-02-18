"""
Multi-engine web search service WITHOUT API keys or scraping.
Uses free JSON APIs from DuckDuckGo, Qwant, SearX (and StartPage if available).
Includes caching, deduplication, and relevance scoring.

Supported sources (free tier, no auth):
- DuckDuckGo Instant Answer API (default)
- Qwant API (privacy-focused, EU-based)
- SearX (federated meta-search, self-hosted or public instance)
- StartPage (if API available, fallback to partner search)
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)


class SearchResult:
    """Single search result with metadata."""
    
    def __init__(
        self,
        url: str,
        title: str,
        snippet: str,
        source: str,
        relevance: float = 0.0,
        published_date: Optional[str] = None,
        rank_position: Optional[int] = None,
    ):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.source = source  # duckduckgo, qwant, searx, startpage
        self.relevance = relevance
        self.published_date = published_date
        self.rank_position = rank_position
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source,
            "relevance": round(self.relevance, 3),
            "published_date": self.published_date,
            "rank_position": self.rank_position,
        }
    
    def __repr__(self) -> str:
        return f"SearchResult({self.title[:40]}... | {self.relevance:.2f})"


class WebSearchService:
    """Multi-engine web search using free APIs (no auth required)."""
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        cache_ttl_hours: int = 24,
        timeout_s: float = 10.0,
    ):
        self.cache_dir = Path(cache_dir or "/opt/gpti/tmp/web_search_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.timeout = timeout_s
        
        # SearX public instances (fallback to others if needed)
        self.searx_instances = [
            "https://searx.be/searx/",
            "https://search.mwclarkson.com/",
            "https://searx.info/",
        ]
    
    def _get_cache_key(self, query: str) -> str:
        """Generate cache key from query."""
        normalized = query.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def _load_cache(self, query: str) -> Optional[List[SearchResult]]:
        """Load results from cache if fresh."""
        cache_file = self.cache_dir / f"{self._get_cache_key(query)}.json"
        if not cache_file.exists():
            return None
        
        try:
            stat = cache_file.stat()
            age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            if age > self.cache_ttl:
                logger.debug(f"Cache expired for '{query}' (age: {age})")
                return None
            
            with open(cache_file) as f:
                data = json.load(f)
            
            results = [SearchResult(**r) for r in data.get("results", [])]
            logger.info(f"Cache hit for '{query}' ({len(results)} results, age: {age.total_seconds():.1f}s)")
            return results
        except Exception as e:
            logger.warning(f"Cache load error for '{query}': {e}")
            return None
    
    def _save_cache(self, query: str, results: List[SearchResult]) -> None:
        """Save results to cache."""
        try:
            cache_file = self.cache_dir / f"{self._get_cache_key(query)}.json"
            data = {
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "results": [r.to_dict() for r in results],
            }
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Cached {len(results)} results for '{query}'")
        except Exception as e:
            logger.warning(f"Cache save error for '{query}': {e}")
    
    async def _fetch_duckduckgo(self, query: str) -> List[SearchResult]:
        """Fetch from DuckDuckGo Instant Answer API (free, no auth)."""
        results = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                url = f"https://api.duckduckgo.com/?q={quote(query)}&format=json"
                resp = await client.get(url)
                resp.raise_for_status()
                
                data = resp.json()
                
                # Abstract/Answer section
                if data.get("AbstractURL"):
                    results.append(
                        SearchResult(
                            url=data["AbstractURL"],
                            title=data.get("Heading", query),
                            snippet=data.get("AbstractText", "")[:200],
                            source="duckduckgo",
                            rank_position=1,
                        )
                    )
                
                # Related Topics
                related = data.get("RelatedTopics", [])
                for topic in related[:8]:
                    if isinstance(topic, dict):
                        if "FirstURL" in topic:
                            results.append(
                                SearchResult(
                                    url=topic["FirstURL"],
                                    title=topic.get("Text", "")[:100],
                                    snippet=topic.get("Text", "")[:200],
                                    source="duckduckgo",
                                    rank_position=len(results) + 1,
                                )
                            )
                        elif "Topics" in topic:
                            for sub in topic["Topics"][:3]:
                                if "FirstURL" in sub:
                                    results.append(
                                        SearchResult(
                                            url=sub["FirstURL"],
                                            title=sub.get("Text", "")[:100],
                                            snippet=sub.get("Text", "")[:200],
                                            source="duckduckgo",
                                            rank_position=len(results) + 1,
                                        )
                                    )
                
                logger.info(f"DuckDuckGo: {len(results)} results for '{query}'")
        except Exception as e:
            logger.warning(f"DuckDuckGo fetch error for '{query}': {e}")
        
        return results
    
    async def _fetch_qwant(self, query: str) -> List[SearchResult]:
        """Fetch from Qwant API (privacy-focused, EU-based)."""
        results = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Qwant API endpoint (free, no auth)
                url = f"https://api.qwant.com/v3/search/web?q={quote(query)}&count=10"
                resp = await client.get(url)
                resp.raise_for_status()
                
                data = resp.json()
                
                # Extract results from response
                items = data.get("data", {}).get("result", {}).get("items", [])
                for i, item in enumerate(items[:10]):
                    title = item.get("title", "")
                    url_text = item.get("url", "")
                    snippet = item.get("desc", "")[:200]
                    
                    if title and url_text:
                        results.append(
                            SearchResult(
                                url=url_text,
                                title=title,
                                snippet=snippet,
                                source="qwant",
                                rank_position=i + 1,
                            )
                        )
                
                logger.info(f"Qwant: {len(results)} results for '{query}'")
        except Exception as e:
            logger.warning(f"Qwant fetch error for '{query}': {e}")
        
        return results
    
    async def _fetch_searx(self, query: str) -> List[SearchResult]:
        """Fetch from SearX federated meta-search (free, privacy-friendly)."""
        results = []
        
        for instance in self.searx_instances:
            if results:  # Stop after first success
                break
            
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    # SearX JSON API
                    url = f"{instance}search?q={quote(query)}&format=json"
                    resp = await client.get(url)
                    resp.raise_for_status()
                    
                    data = resp.json()
                    
                    # Extract results
                    items = data.get("results", [])
                    for i, item in enumerate(items[:10]):
                        title = item.get("title", "")
                        url_text = item.get("url", "")
                        snippet = item.get("content", "")[:200]
                        
                        if title and url_text and not url_text.startswith("javascript:"):
                            results.append(
                                SearchResult(
                                    url=url_text,
                                    title=title,
                                    snippet=snippet,
                                    source="searx",
                                    rank_position=i + 1,
                                )
                            )
                    
                    logger.info(f"SearX ({instance}): {len(results)} results for '{query}'")
                    break  # Success, don't try other instances
            except Exception as e:
                logger.debug(f"SearX fetch error from {instance}: {e}")
                continue
        
        return results
    
    def _calculate_relevance(self, result: SearchResult, query: str, rank: int) -> float:
        """Calculate relevance score (0.0-1.0)."""
        score = 0.0
        
        # Position score
        if rank == 1:
            score += 0.4
        elif rank <= 3:
            score += 0.3
        elif rank <= 5:
            score += 0.2
        else:
            score += 0.1
        
        # Query match in title
        query_words = set(query.lower().split())
        title_words = set(result.title.lower().split())
        overlap = len(query_words & title_words) / max(len(query_words), 1)
        score += overlap * 0.3
        
        # Query match in snippet
        snippet_words = set(result.snippet.lower().split())
        snippet_overlap = len(query_words & snippet_words) / max(len(query_words), 1)
        score += snippet_overlap * 0.2
        
        # Source priority (favor direct search results over indirect)
        source_priority = {"duckduckgo": 0.05, "qwant": 0.05, "searx": 0.05}
        score += source_priority.get(result.source, 0.0)
        
        return min(1.0, max(0.0, score))
    
    def _deduplicate_results(self, all_results: List[SearchResult]) -> List[SearchResult]:
        """Deduplicate results by URL domain, keeping highest relevance."""
        domain_map: Dict[str, SearchResult] = {}
        
        for result in all_results:
            domain = urlparse(result.url).netloc or "unknown"
            
            if domain not in domain_map:
                domain_map[domain] = result
            else:
                if result.relevance > domain_map[domain].relevance:
                    domain_map[domain] = result
        
        return list(domain_map.values())
    
    async def search(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
        sources: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """
        Search web using multiple free APIs.
        
        Args:
            query: Search query
            max_results: Max results to return
            use_cache: Whether to use cache
            sources: List of sources to use (default: duckduckgo)
                    Options: duckduckgo, qwant, searx
        
        Returns:
            List of SearchResult objects, sorted by relevance
        """
        # Default: use DuckDuckGo (most reliable)
        # Set GPTI_WEB_SEARCH_SOURCES=duckduckgo,qwant,searx to enable multiple
        if sources is None:
            sources = os.getenv("GPTI_WEB_SEARCH_SOURCES", "duckduckgo").split(",")
        
        # Check cache
        if use_cache:
            cached = self._load_cache(query)
            if cached:
                return cached[:max_results]
        
        logger.info(f"Searching '{query}' across {sources}")
        
        all_results = []
        
        # Fetch from selected sources concurrently
        tasks = []
        if "duckduckgo" in sources:
            tasks.append(self._fetch_duckduckgo(query))
        if "qwant" in sources:
            tasks.append(self._fetch_qwant(query))
        if "searx" in sources:
            tasks.append(self._fetch_searx(query))
        
        import asyncio
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)
        for results in results_lists:
            if isinstance(results, list):
                all_results.extend(results)
            elif isinstance(results, Exception):
                logger.debug(f"Task failed: {results}")
        
        logger.info(f"Fetched {len(all_results)} total results from {len(sources)} sources")
        
        # Deduplicate
        all_results = self._deduplicate_results(all_results)
        logger.info(f"After dedup: {len(all_results)} unique results")
        
        # Calculate relevance scores and sort
        ranked_results = []
        for rank, result in enumerate(all_results, 1):
            result.relevance = self._calculate_relevance(result, query, rank)
            ranked_results.append(result)
        
        ranked_results.sort(key=lambda r: r.relevance, reverse=True)
        
        # Return top N
        final_results = ranked_results[:max_results]
        
        # Save cache
        if use_cache:
            self._save_cache(query, final_results)
        
        logger.info(
            f"Returning {len(final_results)} results "
            f"(relevance: {[f'{r.relevance:.2f}' for r in final_results]})"
        )
        return final_results


# Singleton instance
_service_instance: Optional[WebSearchService] = None


def get_web_search_service(
    cache_dir: Optional[str] = None,
    cache_ttl_hours: int = 24,
    timeout_s: float = 10.0,
) -> WebSearchService:
    """Get or create singleton web search service."""
    global _service_instance
    
    if _service_instance is None:
        cache_dir = cache_dir or os.getenv("GPTI_WEB_SEARCH_CACHE", "/opt/gpti/tmp/web_search_cache")
        cache_ttl = int(os.getenv("GPTI_WEB_SEARCH_CACHE_TTL_H", cache_ttl_hours))
        timeout_s = float(os.getenv("GPTI_WEB_SEARCH_TIMEOUT_S", timeout_s))
        
        _service_instance = WebSearchService(
            cache_dir=cache_dir,
            cache_ttl_hours=cache_ttl,
            timeout_s=timeout_s,
        )
        logger.info(f"Initialized WebSearchService (cache={cache_dir}, ttl={cache_ttl}h)")
    
    return _service_instance


def web_search(
    query: str,
    max_results: int = 10,
    sources: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for web search (for use in agents/LLM contexts).
    
    Args:
        query: Search query
        max_results: Max results to return
        sources: List of sources to use (default: all)
    
    Returns:
        List of result dicts with url, title, snippet, source, relevance
    """
    import asyncio
    
    service = get_web_search_service()
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    results = loop.run_until_complete(
        service.search(query, max_results=max_results, sources=sources)
    )
    
    return [r.to_dict() for r in results]
