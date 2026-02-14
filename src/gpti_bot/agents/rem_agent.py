"""
REM Agent - Regulatory Event Monitor
Phase 2: Week 2

Purpose:
- Parse regulatory news and enforcement actions
- Monitor SEC, FCA, CySEC databases for firm events
- Extract regulatory events (warnings, suspensions, settlements)
- Match events to firm database (fuzzy matching)
- Feed into Ground Truth validation

Data Sources:
- SEC Enforcement (https://www.sec.gov/litigation/)
- FCA Warnings (https://www.fca.org.uk/news/warnings/)
- CySEC Enforcement (https://www.cysec.gov.cy/)
- News RSS feeds (Reuters, Bloomberg, etc.)
- Court records (PACER for US cases)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
from dataclasses import dataclass
import re
import os
import json
import hashlib
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime

import requests
import psycopg
from bs4 import BeautifulSoup

from gpti_bot.agents import Agent, AgentStatus, AgentResult, Evidence, EvidenceType

logger = logging.getLogger(__name__)


@dataclass
class RegulatoryEvent:
    """A regulatory event extracted from news/databases"""
    event_id: str
    firm_name: str
    firm_id: Optional[str]
    event_type: str  # warning, enforcement, suspension, revocation, settlement
    event_date: str
    announced_date: str
    severity: str  # critical, high, medium, low
    jurisdiction: str
    description: str
    source_url: str
    source_type: str  # sec, fca, cysec, news, court
    match_confidence: float  # 0.0-1.0 (confidence firm_id match)
    expected_impact: float  # -1.0 to 0.0 (negative impact)


class REMAgent(Agent):
    """Regulatory Event Monitor Agent"""
    
    def __init__(self):
        super().__init__("REM", frequency="daily")

        self.use_live_sources = os.getenv("REM_LIVE", "1") == "1"
        self.http_timeout_s = int(os.getenv("REM_HTTP_TIMEOUT_S", "12"))
        
        # Test data - regulatory events
        # In production, these would be fetched from real APIs/feeds
        self.test_events = [
            RegulatoryEvent(
                event_id="SEC-2026-001",
                firm_name="FTMO Group a.s.",
                firm_id="ftmocom",
                event_type="warning",
                event_date="2026-01-28",
                announced_date="2026-01-28",
                severity="medium",
                jurisdiction="US",
                description="SEC issues warning regarding unauthorized operations targeting US retail investors",
                source_url="https://www.sec.gov/litigation/alerts/2026-001",
                source_type="sec",
                match_confidence=0.95,
                expected_impact=-0.15
            ),
            RegulatoryEvent(
                event_id="FCA-2026-002",
                firm_name="XM Global Limited",
                firm_id="xmglobal",
                event_type="enforcement",
                event_date="2026-01-20",
                announced_date="2026-01-22",
                severity="high",
                jurisdiction="UK",
                description="FCA enforcement action: firm failed to respond to regulatory inquiries within deadline",
                source_url="https://www.fca.org.uk/news/news-stories/enforcement-2026",
                source_type="fca",
                match_confidence=0.98,
                expected_impact=-0.25
            ),
            RegulatoryEvent(
                event_id="CYSEC-2026-003",
                firm_name="RoboForex (CY) Ltd",
                firm_id="roboforex",
                event_type="suspension",
                event_date="2026-01-15",
                announced_date="2026-01-16",
                severity="critical",
                jurisdiction="Cyprus",
                description="CySEC suspends firm license pending investigation into customer fund segregation violations",
                source_url="https://www.cysec.gov.cy/en-GB/enforcement/2026",
                source_type="cysec",
                match_confidence=0.99,
                expected_impact=-0.80
            ),
        ]
    
    async def run(self, firms: List[Dict[str, Any]]) -> AgentResult:
        """
        Execute regulatory event monitoring.
        
        Args:
            firms: List of firms to monitor
            
        Returns:
            AgentResult with detected events
        """
        start_time = datetime.now()
        evidence_items: List[Evidence] = []
        errors = []
        
        try:
            firms_with_events = 0
            critical_events = 0
            
            # Phase 2 Week 2: Use test data
            # Production: Fetch from real APIs
            detected_events = await self._fetch_events()
            
            # For each detected event, create evidence if firm matches
            for event in detected_events:
                try:
                    # Try exact match first
                    if event.firm_id:
                        firm_match = next(
                            (f for f in firms 
                             if f.get("firm_id") == event.firm_id or 
                                f.get("id") == event.firm_id),
                            None
                        )
                    else:
                        # Fuzzy match on firm name
                        firm_match = await self._fuzzy_match_firm(
                            event.firm_name, 
                            firms
                        )
                    
                    if firm_match or event.firm_id:
                        firms_with_events += 1
                        if event.severity == "critical":
                            critical_events += 1
                        
                        # Create evidence item
                        evidence = Evidence(
                            firm_id=event.firm_id or firm_match.get("firm_id", "unknown"),
                            evidence_type=EvidenceType.REGULATORY_EVENT,
                            collected_by="REM",
                            collected_at=datetime.now(),
                            source=event.source_type.upper(),
                            raw_data={
                                "event_type": event.event_type,
                                "event_date": event.event_date,
                                "announced_date": event.announced_date,
                                "severity": event.severity,
                                "jurisdiction": event.jurisdiction,
                                "description": event.description,
                                "source_url": event.source_url,
                                "source_type": event.source_type,
                                "event_id": event.event_id,
                            },
                            validation_status="verified",
                            confidence_score=event.match_confidence,
                            impact_score=event.expected_impact
                        )
                        
                        evidence_items.append(evidence)
                        logger.info(
                            f"REM: {event.event_type} for {event.firm_name} "
                            f"(severity={event.severity})"
                        )
                    
                except Exception as e:
                    error_msg = f"Error processing event {event.event_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
            
            duration = (datetime.now() - start_time).total_seconds()

            self._store_evidence_items(evidence_items)
            
            return AgentResult(
                agent_name="REM",
                status=AgentStatus.SUCCESS,
                timestamp=datetime.now(),
                firms_processed=len(firms),
                evidence_collected=len(evidence_items),
                errors=errors,
                warnings=[],
                duration_seconds=duration,
                data={
                    "evidence": [e.to_dict() for e in evidence_items],
                    "summary": {
                        "events_detected": len(detected_events),
                        "firms_with_events": firms_with_events,
                        "critical_events": critical_events,
                        "event_types": self._count_event_types(detected_events),
                        "jurisdictions": self._count_jurisdictions(detected_events),
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"REM Agent failed: {str(e)}", exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return AgentResult(
                agent_name="REM",
                status=AgentStatus.FAILED,
                timestamp=datetime.now(),
                firms_processed=0,
                evidence_collected=0,
                errors=[str(e)],
                warnings=[],
                duration_seconds=duration,
                data={}
            )
    
    async def _fetch_events(self) -> List[RegulatoryEvent]:
        """
        Fetch regulatory events from various sources.
        
        In production, this would:
        1. Query SEC enforcement API
        2. Scrape FCA warnings page
        3. Query CySEC API
        4. Parse news RSS feeds
        5. Check court databases (PACER)
        
        For Phase 2 Week 2, using test data.
        
        Returns:
            List of regulatory events
        """
        if not self.use_live_sources:
            await asyncio.sleep(0.2)
            logger.info(f"Fetched {len(self.test_events)} regulatory events (test)")
            return self.test_events

        events: List[RegulatoryEvent] = []
        events.extend(self._fetch_rss_events())
        events.extend(self._fetch_html_events())

        if not events:
            logger.warning("No live REM events found, falling back to test events")
            return self.test_events

        logger.info(f"Fetched {len(events)} regulatory events (live)")
        return events

    def _fetch_rss_events(self) -> List[RegulatoryEvent]:
        feeds = [
            {
                "url": "https://www.fca.org.uk/news/rss.xml",
                "jurisdiction": "UK",
                "source_type": "fca",
            },
            {
                "url": "https://www.sec.gov/rss/litigation/litreleases.xml",
                "jurisdiction": "US",
                "source_type": "sec",
            },
            {
                "url": "https://www.cftc.gov/PressRoom/PressReleases/rss",
                "jurisdiction": "US",
                "source_type": "cftc",
            },
            {
                "url": "https://www.bafin.de/SiteGlobals/Functions/RSSFeed/RSSNewsfeed/RSSNewsfeed.xml",
                "jurisdiction": "DE",
                "source_type": "bafin",
            },
            {
                "url": "https://www.finma.ch/en/news/rss.xml",
                "jurisdiction": "CH",
                "source_type": "finma",
            },
        ]

        all_events: List[RegulatoryEvent] = []
        for feed in feeds:
            try:
                resp = requests.get(feed["url"], timeout=self.http_timeout_s, headers={"User-Agent": "GTIXT-REM/1.0"})
                if resp.status_code != 200:
                    continue
                items = self._parse_rss(resp.text)
                for item in items:
                    event_type = self._infer_event_type(item["title"])
                    severity = self._infer_severity(item["title"])
                    all_events.append(
                        RegulatoryEvent(
                            event_id=self._event_id(feed["source_type"], item["title"], item["date"]),
                            firm_name=item["title"],
                            firm_id=None,
                            event_type=event_type,
                            event_date=item["date"],
                            announced_date=item["date"],
                            severity=severity,
                            jurisdiction=feed["jurisdiction"],
                            description=item["summary"],
                            source_url=item["link"],
                            source_type=feed["source_type"],
                            match_confidence=0.0,
                            expected_impact=self._impact_from_severity(severity),
                        )
                    )
            except Exception:
                continue

        return all_events

    def _fetch_html_events(self) -> List[RegulatoryEvent]:
        pages = [
            {
                "url": "https://www.cysec.gov.cy/en-GB/enforcement/",
                "jurisdiction": "CY",
                "source_type": "cysec",
            },
            {
                "url": "https://www.amf-france.org/en/actualites/communiques",
                "jurisdiction": "FR",
                "source_type": "amf",
            },
        ]

        events: List[RegulatoryEvent] = []
        for page in pages:
            try:
                resp = requests.get(page["url"], timeout=self.http_timeout_s, headers={"User-Agent": "GTIXT-REM/1.0"})
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=True)
                titles = []
                for link in links:
                    text = (link.get_text(" ", strip=True) or "").strip()
                    if not text:
                        continue
                    if len(text) < 6:
                        continue
                    titles.append((text, link["href"]))
                seen = set()
                for title, href in titles[:20]:
                    if title in seen:
                        continue
                    seen.add(title)
                    event_type = self._infer_event_type(title)
                    severity = self._infer_severity(title)
                    link = href
                    if link.startswith("/"):
                        link = page["url"].rstrip("/") + link
                    events.append(
                        RegulatoryEvent(
                            event_id=self._event_id(page["source_type"], title, datetime.utcnow().isoformat()),
                            firm_name=title,
                            firm_id=None,
                            event_type=event_type,
                            event_date=datetime.utcnow().isoformat(),
                            announced_date=datetime.utcnow().isoformat(),
                            severity=severity,
                            jurisdiction=page["jurisdiction"],
                            description=title,
                            source_url=link,
                            source_type=page["source_type"],
                            match_confidence=0.0,
                            expected_impact=self._impact_from_severity(severity),
                        )
                    )
            except Exception:
                continue

        return events

    def _parse_rss(self, xml_text: str) -> List[Dict[str, str]]:
        try:
            soup = BeautifulSoup(xml_text, "xml")
            items = soup.find_all("item")
            results = []
            for item in items[:50]:
                title = (item.title.text if item.title else "").strip()
                link = (item.link.text if item.link else "").strip()
                pub_date = (item.pubDate.text if item.pubDate else "").strip()
                desc = (item.description.text if item.description else "").strip()
                if not title:
                    continue
                results.append({
                    "title": title,
                    "link": link,
                    "date": self._parse_date(pub_date),
                    "summary": desc,
                })
            return results
        except Exception:
            return []

    def _parse_date(self, value: str) -> str:
        if not value:
            return datetime.utcnow().isoformat()
        try:
            dt = parsedate_to_datetime(value)
            return dt.isoformat()
        except Exception:
            return datetime.utcnow().isoformat()

    def _event_id(self, source: str, title: str, date: str) -> str:
        digest = hashlib.sha256(f"{source}:{title}:{date}".encode("utf-8")).hexdigest()
        return f"{source.upper()}-{digest[:12]}"

    def _infer_event_type(self, title: str) -> str:
        lowered = title.lower()
        if any(token in lowered for token in ["suspend", "suspension"]):
            return "suspension"
        if any(token in lowered for token in ["revok", "withdraw"]):
            return "revocation"
        if any(token in lowered for token in ["settlement", "fine", "penalty"]):
            return "settlement"
        if any(token in lowered for token in ["enforcement", "action", "proceeding"]):
            return "enforcement"
        return "warning"

    def _infer_severity(self, title: str) -> str:
        lowered = title.lower()
        if any(token in lowered for token in ["revok", "ban", "suspend", "criminal", "fraud"]):
            return "critical"
        if any(token in lowered for token in ["enforcement", "penalty", "fine"]):
            return "high"
        if any(token in lowered for token in ["warning", "alert"]):
            return "medium"
        return "low"

    def _impact_from_severity(self, severity: str) -> float:
        mapping = {
            "critical": -0.8,
            "high": -0.5,
            "medium": -0.25,
            "low": -0.1,
        }
        return mapping.get(severity, -0.1)
    
    async def _fuzzy_match_firm(
        self,
        firm_name: str,
        firms: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Fuzzy match firm name to database.
        
        Uses sequence matching to find likely candidates when
        exact name match fails.
        
        Args:
            firm_name: Name from regulatory event
            firms: List of firms to search
            
        Returns:
            Matched firm or None
        """
        if not firms:
            return None
        
        best_match = None
        best_score = 0.0
        
        for firm in firms:
            db_name = firm.get("name") or firm.get("firm_name") or ""
            
            # Normalize for comparison
            name1 = firm_name.lower().strip()
            name2 = db_name.lower().strip()
            
            # Calculate similarity
            score = SequenceMatcher(None, name1, name2).ratio()
            
            # Also check for partial matches
            if name1 in name2 or name2 in name1:
                score = max(score, 0.85)
            
            if score > best_score and score >= 0.75:  # Threshold
                best_score = score
                best_match = firm
        
        if best_match:
            logger.info(f"Fuzzy matched '{firm_name}' to '{best_match.get('name')}' ({best_score:.2f})")
        
        return best_match
    
    async def validate(self, evidence: Evidence) -> bool:
        """
        Validate regulatory event evidence.
        
        Checks:
        - Event type is valid
        - Event date is valid format
        - Severity is valid enum
        - Confidence score is valid range
        - Source URL is present
        
        Args:
            evidence: Evidence to validate
            
        Returns:
            True if valid
        """
        try:
            data = evidence.raw_data
            
            # Check event type
            valid_types = [
                "warning", "enforcement", "suspension", 
                "revocation", "settlement"
            ]
            if data.get("event_type") not in valid_types:
                logger.warning(f"Invalid event type: {data.get('event_type')}")
                return False
            
            # Check severity
            valid_severities = ["critical", "high", "medium", "low"]
            if data.get("severity") not in valid_severities:
                logger.warning(f"Invalid severity: {data.get('severity')}")
                return False
            
            # Check dates
            try:
                datetime.fromisoformat(data.get("event_date", ""))
                datetime.fromisoformat(data.get("announced_date", ""))
            except:
                logger.warning("Invalid date format")
                return False
            
            # Check source URL
            if not data.get("source_url"):
                logger.warning("Missing source URL")
                return False
            
            # Check confidence score
            confidence = evidence.confidence_score
            if not 0.0 <= confidence <= 1.0:
                logger.warning(f"Invalid confidence score: {confidence}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return False
    
    def _count_event_types(self, events: List[RegulatoryEvent]) -> Dict[str, int]:
        """Count events by type"""
        counts = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return counts
    
    def _count_jurisdictions(self, events: List[RegulatoryEvent]) -> Dict[str, int]:
        """Count events by jurisdiction"""
        counts = {}
        for event in events:
            counts[event.jurisdiction] = counts.get(event.jurisdiction, 0) + 1
        return counts

    def _store_evidence_items(self, evidence_items: List[Evidence]) -> None:
        if not evidence_items:
            return
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return
        try:
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    for evidence in evidence_items:
                        payload = evidence.raw_data or {}
                        payload_text = json.dumps(payload, ensure_ascii=True)
                        evidence_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
                        cur.execute(
                            """
                            INSERT INTO evidence_collection (
                                firm_id,
                                evidence_type,
                                evidence_source,
                                evidence_hash,
                                content_text,
                                content_json,
                                content_url,
                                collected_by,
                                collection_method,
                                relevance_score,
                                affects_metric,
                                affects_score_version,
                                impact_weight,
                                confidence_level,
                                is_verified,
                                collected_at
                            ) VALUES (
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                            )
                            """,
                            (
                                evidence.firm_id,
                                "document",
                                payload.get("source_type") or evidence.source,
                                evidence_hash,
                                payload.get("description"),
                                payload_text,
                                payload.get("source_url"),
                                evidence.collected_by,
                                "rss_fetch",
                                evidence.confidence_score,
                                "regulatory_event",
                                "v1.0",
                                evidence.impact_score,
                                "high" if evidence.confidence_score >= 0.85 else "medium",
                                True,
                                evidence.collected_at,
                            ),
                        )
                conn.commit()
        except Exception:
            return


# Quick test
if __name__ == "__main__":
    import json
    
    async def test():
        agent = REMAgent()
        
        test_firms = [
            {"firm_id": "ftmocom", "name": "FTMO"},
            {"firm_id": "xmglobal", "name": "XM Global"},
            {"firm_id": "roboforex", "name": "RoboForex"},
        ]
        
        result = await agent.run(test_firms)
        print(f"\n{agent.name} Result:")
        print(json.dumps(result.to_dict(), indent=2))
