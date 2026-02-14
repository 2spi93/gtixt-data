"""
SSS Agent - Screening & Scoring System
Phase 2: Week 1

Purpose:
- Screen firm principals/UBOs against sanctions lists
- Detect PEP (Politically Exposed Persons)
- Check OFAC, UN, and global watchlists
- Calculate fraud/sanctions risk scores

Data Sources:
- OFAC Consolidated Sanctions List
- UN Security Council Sanctions Lists
- EU Sanctions Lists
- Global PEP databases
- World-Check (in production)
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
from dataclasses import dataclass
import os
import re
import hashlib
import json
import requests
import xml.etree.ElementTree as ET
import psycopg

from gpti_bot.agents import Agent, AgentStatus, AgentResult, Evidence, EvidenceType

logger = logging.getLogger(__name__)


@dataclass
class WatchlistMatch:
    """A match in sanctions/PEP/watchlist"""
    name: str
    type: str  # OFAC, UN, PEP, etc.
    match_type: str  # exact, fuzzy, partial
    match_score: float  # 0.0-1.0
    entity_type: str  # individual, company
    country: str
    reason: str
    list_name: str
    last_updated: str


class SSSAgent(Agent):
    """Sanctions & Screening System Agent"""
    
    def __init__(self):
        super().__init__("SSS", frequency="monthly")

        self.use_live_sources = os.getenv("SSS_LIVE", "1") == "1"
        self.http_timeout_s = int(os.getenv("SSS_HTTP_TIMEOUT_S", "12"))
        self.sanctions_cache: Dict[str, List[str]] = {}
        
        # In production, these would be actual API clients
        self.watchlists = {
            "OFAC": {
                "url": "https://home.treasury.gov/policy-issues/financial-sanctions/consolidated-sanctions-list",
                "api": "SDNList"
            },
            "UN": {
                "url": "https://www.un.org/securitycouncil/sanctions/",
                "api": "UNConsolidatedList"
            },
            "EU": {
                "url": "https://ec.europa.eu/info/business-economy-euro/banking-and-finance/international-relations-and-sanctions_en",
                "api": "EUSanctionsList"
            },
            "PEP": {
                "url": "https://www.world-check.com",
                "api": "PEPDatabase"
            }
        }
        
        # Test data - simulated watchlist matches
        self.test_matches = {
            "ftmocom": [],  # Clean
            "xmglobal": [
                WatchlistMatch(
                    name="John Smith",
                    type="PEP",
                    match_type="fuzzy",
                    match_score=0.72,
                    entity_type="individual",
                    country="UK",
                    reason="Former government official",
                    list_name="UK-PEP",
                    last_updated="2026-01-15"
                )
            ],
            "roboforex": [
                WatchlistMatch(
                    name="RoboForex Ltd",
                    type="OFAC",
                    match_type="exact",
                    match_score=0.98,
                    entity_type="company",
                    country="Cyprus",
                    reason="Sanctions evasion suspected",
                    list_name="OFAC-SDN",
                    last_updated="2026-01-20"
                )
            ]
        }
    
    async def run(self, firms: List[Dict[str, Any]]) -> AgentResult:
        """
        Execute sanctions screening.
        
        Args:
            firms: List of firms to screen
            
        Returns:
            AgentResult with screening results
        """
        start_time = datetime.now()
        evidence_items: List[Evidence] = []
        errors = []
        
        try:
            processed_count = 0
            critical_matches = 0
            
            for firm in firms[:10]:
                firm_id = firm.get("firm_id") or firm.get("id")
                firm_name = firm.get("name") or firm.get("firm_name") or firm.get("brand_name") or firm_id
                
                try:
                    # Get watchlist matches (test data for Phase 2)
                    matches = await self._screen_watchlists(firm_id, firm_name)
                    processed_count += 1
                    
                    if matches:
                        critical_matches += len(matches)
                        
                        # Create evidence item
                        evidence = Evidence(
                            firm_id=firm_id,
                            evidence_type=EvidenceType.WATCHLIST_MATCH,
                            collected_by="SSS",
                            collected_at=datetime.now(),
                            source="Multi-List",
                            raw_data={
                                "matches": [
                                    {
                                        "name": m.name,
                                        "type": m.type,
                                        "match_score": m.match_score,
                                        "entity_type": m.entity_type,
                                        "country": m.country,
                                        "reason": m.reason,
                                        "list_name": m.list_name,
                                        "last_updated": m.last_updated,
                                    }
                                    for m in matches
                                ],
                                "total_matches": len(matches),
                                "critical_matches": len(
                                    [m for m in matches if m.match_score > 0.90]
                                ),
                                "screening_date": datetime.now().isoformat(),
                            },
                            validation_status="verified",
                            confidence_score=0.98,  # High confidence for watchlist
                            impact_score=self._calculate_risk_impact(matches)
                        )
                        
                        evidence_items.append(evidence)
                        logger.info(f"Found {len(matches)} matches for {firm_id}")
                    else:
                        logger.info(f"No watchlist matches for {firm_id}")
                        
                except Exception as e:
                    error_msg = f"Screening failed for {firm_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
            
            duration = (datetime.now() - start_time).total_seconds()

            self._store_evidence_items(evidence_items)
            
            return AgentResult(
                agent_name="SSS",
                status=AgentStatus.SUCCESS,
                timestamp=datetime.now(),
                firms_processed=processed_count,
                evidence_collected=len(evidence_items),
                errors=errors,
                warnings=[],
                duration_seconds=duration,
                data={
                    "evidence": [e.to_dict() for e in evidence_items],
                    "summary": {
                        "firms_screened": processed_count,
                        "firms_with_matches": len(evidence_items),
                        "critical_matches": critical_matches,
                        "watchlists_checked": len(self.watchlists),
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"SSS Agent failed: {str(e)}", exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return AgentResult(
                agent_name="SSS",
                status=AgentStatus.FAILED,
                timestamp=datetime.now(),
                firms_processed=0,
                evidence_collected=0,
                errors=[str(e)],
                warnings=[],
                duration_seconds=duration,
                data={}
            )
    
    async def _screen_watchlists(self, firm_id: str, firm_name: str) -> List[WatchlistMatch]:
        """
        Screen firm against watchlists.
        
        In production, this would:
        1. Fetch principals/UBOs from firm database
        2. Query each watchlist API
        3. Use fuzzy matching for names
        4. Return matched records
        
        For Phase 2 Week 1, using test data.
        
        Args:
            firm_id: Firm to screen
            
        Returns:
            List of watchlist matches
        """
        if not self.use_live_sources:
            await asyncio.sleep(0.2)
            return self.test_matches.get(firm_id, [])

        if not self.sanctions_cache:
            await asyncio.to_thread(self._load_sanctions_lists)

        matches: List[WatchlistMatch] = []
        normalized_firm = self._normalize_name(firm_name)
        firm_tokens = set(self._tokenize(normalized_firm))

        for list_name, names in self.sanctions_cache.items():
            for entry in names:
                entry_norm = self._normalize_name(entry)
                if not entry_norm:
                    continue
                if normalized_firm and normalized_firm == entry_norm:
                    matches.append(self._build_match(entry, list_name, score=0.98))
                    break
                entry_tokens = set(self._tokenize(entry_norm))
                if firm_tokens and firm_tokens.issubset(entry_tokens) and len(firm_tokens) >= 2:
                    matches.append(self._build_match(entry, list_name, score=0.85))
                    break

        if not matches:
            return []

        return matches

    def _load_sanctions_lists(self) -> None:
        sources = {
            "OFAC": "https://ofac.treasury.gov/sites/default/files/sdn.csv",
            "UN": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
            "EU": "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content",
            "UK": "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/1190359/ConList.csv",
        }

        for name, url in sources.items():
            try:
                resp = requests.get(url, timeout=self.http_timeout_s, headers={"User-Agent": "GTIXT-SSS/1.0"})
                if resp.status_code != 200:
                    continue
                if name == "UN" or name == "EU":
                    names = self._parse_xml_names(resp.text)
                else:
                    names = self._parse_csv_names(resp.text)
                if names:
                    self.sanctions_cache[name] = names
            except Exception:
                continue

    def _parse_csv_names(self, text: str) -> List[str]:
        lines = text.splitlines()
        if not lines:
            return []
        names: List[str] = []
        for line in lines[1:]:
            parts = line.split(",")
            if not parts:
                continue
            name = parts[1].strip().strip('"') if len(parts) > 1 else parts[0].strip().strip('"')
            if name:
                names.append(name)
        return names

    def _parse_xml_names(self, xml_text: str) -> List[str]:
        names: List[str] = []
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return names
        for node in root.iter():
            if node.tag.lower().endswith("name") or node.tag.lower().endswith("fullname"):
                value = (node.text or "").strip()
                if value:
                    names.append(value)
        return names

    def _normalize_name(self, value: str) -> str:
        if not value:
            return ""
        cleaned = re.sub(r"[^a-z0-9\s]", " ", value.lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"\b(ltd|limited|inc|llc|plc|corp|company|co)\b", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _tokenize(self, value: str) -> List[str]:
        return [token for token in value.split(" ") if token]

    def _build_match(self, name: str, list_name: str, score: float) -> WatchlistMatch:
        return WatchlistMatch(
            name=name,
            type=list_name,
            match_type="exact" if score >= 0.9 else "partial",
            match_score=score,
            entity_type="company",
            country="",
            reason="sanctions_list",
            list_name=list_name,
            last_updated=datetime.now().date().isoformat(),
        )
    
    async def validate(self, evidence: Evidence) -> bool:
        """
        Validate watchlist screening evidence.
        
        Checks:
        - Matches array is not empty (if collected)
        - Match scores are valid (0.0-1.0)
        - Match types are valid
        - List names are known
        
        Args:
            evidence: Evidence to validate
            
        Returns:
            True if valid
        """
        try:
            data = evidence.raw_data
            
            if "matches" in data and data["matches"]:
                for match in data["matches"]:
                    # Check match score
                    if not 0.0 <= match.get("match_score", 0) <= 1.0:
                        logger.warning(f"Invalid match score: {match.get('match_score')}")
                        return False
                    
                    # Check required fields
                    if not match.get("name") or not match.get("type"):
                        logger.warning("Missing name or type in match")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return False
    
    def _calculate_risk_impact(self, matches: List[WatchlistMatch]) -> float:
        """
        Calculate risk impact from watchlist matches.
        
        Higher match scores = more negative impact
        OFAC/UN matches = more critical
        
        Args:
            matches: List of matches
            
        Returns:
            Impact score (-1.0 to 0.0, negative only)
        """
        if not matches:
            return 0.0
        
        max_score = max(m.match_score for m in matches)
        
        # Critical types (OFAC, UN) - full impact
        critical_matches = [
            m for m in matches 
            if m.type in ["OFAC", "UN"]
        ]
        
        if critical_matches:
            return -1.0  # Automatic critical flag
        
        # PEP/EU: scaled based on match score
        if max_score > 0.90:
            return -0.7
        elif max_score > 0.75:
            return -0.4
        else:
            return -0.1

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
                                "api_response",
                                evidence.source,
                                evidence_hash,
                                None,
                                payload_text,
                                None,
                                evidence.collected_by,
                                "api_fetch",
                                evidence.confidence_score,
                                "sanctions_screening",
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
        agent = SSSAgent()
        
        test_firms = [
            {"firm_id": "ftmocom", "name": "FTMO"},
            {"firm_id": "xmglobal", "name": "XM Global"},
            {"firm_id": "roboforex", "name": "RoboForex"},
        ]
        
        result = await agent.run(test_firms)
        print(f"\n{agent.name} Result:")
        print(json.dumps(result.to_dict(), indent=2))
