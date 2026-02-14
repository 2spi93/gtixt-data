"""
MIS Agent - Manual Investigation System (Research Automation)

Automates manual research and investigation playbooks.
Gathers business intelligence from multiple sources.
Identifies registration anomalies, domain issues, and research gaps.

Sources:
- WHOIS database (domain registration)
- Company registries (Companies House, EU registries)
- Business news archives
- LinkedIn company profiles
- Domain reputation databases (DMARC, SSL cert validity)

Evidence Types:
- Domain anomalies (registration flags, age, transfers)
- Company registration issues
- Negative news clustering
- Suspicious business patterns
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from abc import ABC

from gpti_bot.agents import Agent, Evidence, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


@dataclass
class DomainInfo:
    """WHOIS domain information"""
    domain: str
    registrar: str
    registration_date: datetime
    expiry_date: datetime
    registrant_country: str
    name_servers: List[str]
    privacy_enabled: bool


class MISAgent(Agent):
    """
    Manual Investigation System (MIS) Agent
    
    Automates research and investigation playbooks.
    Identifies anomalies in domain, company, and business information.
    """
    
    def __init__(self):
        super().__init__("MIS", frequency="daily")
        self.description = "Manual Investigation System (Research Automation)"
        
        # Mock domain database (would be API in production)
        self.domains_db = self._initialize_domain_data()
    
    async def validate(self, evidence: Evidence) -> bool:
        """
        Validate investigation and research evidence
        
        Args:
            evidence: Evidence to validate
            
        Returns:
            True if evidence is valid
        """
        # Validate required fields
        if not evidence.firm_id or not evidence.data:
            return False
        
        # Validate confidence and impact scores
        if not (0 <= evidence.confidence_score <= 1.0):
            return False
        
        if not (-1.0 <= evidence.impact_score <= 1.0):
            return False
        
        return True
    
    async def run(self, firms: List[Dict[str, Any]]) -> AgentResult:
        """
        Main execution method for MIS Agent
        
        Args:
            firms: List of firm dicts with firm_id
            
        Returns:
            AgentResult with evidence items
        """
        try:
            logger.info(f"MIS Agent starting investigation for {len(firms)} firms")
            
            evidence_items = []
            
            for firm in firms:
                firm_id = firm.get('firm_id', '')
                
                # Get domain info
                domain_info = await self._fetch_domain_info(firm_id)
                
                # Check company registration
                company_info = await self._check_company_registration(firm_id)
                
                # Analyze news sentiment
                news_analysis = await self._analyze_news_mentions(firm_id)
                
                # Check for suspicious patterns
                suspicious = await self._detect_suspicious_patterns(firm_id)
                
                # Generate evidence if issues found
                if domain_info['has_issues']:
                    evidence = Evidence(
                        firm_id=firm_id,
                        evidence_type='domain_anomaly',
                        collected_by='MIS',
                        collected_at=datetime.utcnow(),
                        source='MIS Agent',
                        raw_data=domain_info['data'],
                        validation_status='verified',
                        confidence_score=domain_info['confidence'],
                        impact_score=domain_info['impact']
                    )
                    evidence_items.append(evidence)
                
                if company_info['has_issues']:
                    evidence = Evidence(
                        firm_id=firm_id,
                        evidence_type='company_issue',
                        collected_by='MIS',
                        collected_at=datetime.utcnow(),
                        source='MIS Agent',
                        raw_data=company_info['data'],
                        validation_status='verified',
                        confidence_score=company_info['confidence'],
                        impact_score=company_info['impact']
                    )
                    evidence_items.append(evidence)
                
                if news_analysis['has_issues']:
                    evidence = Evidence(
                        firm_id=firm_id,
                        evidence_type='news_risk',
                        collected_by='MIS',
                        collected_at=datetime.utcnow(),
                        source='MIS Agent',
                        raw_data=news_analysis['data'],
                        validation_status='verified',
                        confidence_score=news_analysis['confidence'],
                        impact_score=news_analysis['impact']
                    )
                    evidence_items.append(evidence)
                
                if suspicious['has_issues']:
                    evidence = Evidence(
                        firm_id=firm_id,
                        evidence_type='suspicious_pattern',
                        collected_by='MIS',
                        collected_at=datetime.utcnow(),
                        source='MIS Agent',
                        raw_data=suspicious['data'],
                        validation_status='verified',
                        confidence_score=suspicious['confidence'],
                        impact_score=suspicious['impact']
                    )
                    evidence_items.append(evidence)
            
            # Log results
            critical_issues = sum(1 for e in evidence_items 
                                if e.impact_score < -0.5)
            
            result = AgentResult(
                agent_name=self.name,
                status=AgentStatus.SUCCESS,
                timestamp=datetime.utcnow(),
                firms_processed=len(firms),
                evidence_collected=len(evidence_items),
                errors=[],
                warnings=[],
                duration_seconds=0.0,
                data={'evidence_items': evidence_items}
            )
            
            logger.info(
                f"MIS Agent completed: {len(evidence_items)} evidence items, "
                f"{critical_issues} critical issues"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"MIS Agent error: {str(e)}", exc_info=True)
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                timestamp=datetime.utcnow(),
                firms_processed=0,
                evidence_collected=0,
                errors=[str(e)],
                warnings=[],
                duration_seconds=0.0,
                data={}
            )
    
    async def _fetch_domain_info(self, firm_id: str) -> Dict[str, Any]:
        """
        Fetch WHOIS domain information
        
        Args:
            firm_id: Firm identifier
            
        Returns:
            Dict with domain analysis
        """
        await asyncio.sleep(0.12)  # Simulate API call
        
        # Mock domain data
        domain_data = {
            'ftmocom': {
                'domain': 'ftmo.com',
                'registrar': 'Namecheap Inc',
                'registration_date': datetime(2015, 3, 12),
                'expiry_date': datetime(2025, 3, 12),
                'registrant_country': 'CZ',
                'name_servers': ['ns1.ftmo.com', 'ns2.ftmo.com'],
                'privacy_enabled': False,
                'ssl_valid': True,
                'dns_integrity': True
            },
            'xm': {
                'domain': 'xm.com',
                'registrar': 'NameDrive Inc',
                'registration_date': datetime(2009, 6, 15),
                'expiry_date': datetime(2025, 6, 15),
                'registrant_country': 'CY',
                'name_servers': ['ns1.xm.com', 'ns2.xm.com'],
                'privacy_enabled': True,
                'ssl_valid': True,
                'dns_integrity': True
            },
            'roboforex': {
                'domain': 'roboforex.com',
                'registrar': 'Registrar123',
                'registration_date': datetime(2009, 12, 1),
                'expiry_date': datetime(2024, 12, 1),  # Expired!
                'registrant_country': 'RU',
                'name_servers': ['ns1.roboforex.biz', 'ns2.roboforex.biz'],
                'privacy_enabled': True,
                'ssl_valid': False,  # Invalid cert
                'dns_integrity': False  # DNS issues
            }
        }
        
        data = domain_data.get(firm_id, {
            'domain': f'{firm_id}.com',
            'registrar': 'Unknown',
            'registration_date': datetime(2010, 1, 1),
            'expiry_date': datetime(2025, 1, 1),
            'registrant_country': 'Unknown',
            'name_servers': [],
            'privacy_enabled': False,
            'ssl_valid': True,
            'dns_integrity': True
        })
        
        # Analyze domain
        has_issues = False
        confidence = 0.85
        impact = 0.0
        description = f"Domain analysis for {firm_id}"
        
        now = datetime.utcnow()
        days_to_expiry = (data['expiry_date'] - now).days
        
        if days_to_expiry < 0:  # Expired
            has_issues = True
            impact = -0.80
            confidence = 0.99
            description = f"Domain {data['domain']} EXPIRED ({days_to_expiry} days ago)"
        elif days_to_expiry < 30:  # Expiring soon
            has_issues = True
            impact = -0.50
            confidence = 0.95
            description = f"Domain {data['domain']} expiring in {days_to_expiry} days"
        
        if not data['ssl_valid']:  # Invalid SSL
            has_issues = True
            impact = min(impact - 0.3, -0.6)
            confidence = 0.98
            description += " | SSL certificate INVALID"
        
        if not data['dns_integrity']:  # DNS issues
            has_issues = True
            impact = min(impact - 0.25, -0.5)
            confidence = 0.90
            description += " | DNS integrity issues detected"
        
        return {
            'has_issues': has_issues,
            'description': description,
            'confidence': confidence,
            'impact': impact,
            'data': {
                'domain': data['domain'],
                'registrar': data['registrar'],
                'registration_date': data['registration_date'].isoformat(),
                'expiry_date': data['expiry_date'].isoformat(),
                'days_to_expiry': days_to_expiry,
                'registrant_country': data['registrant_country'],
                'ssl_valid': data['ssl_valid'],
                'dns_integrity': data['dns_integrity']
            }
        }
    
    async def _check_company_registration(self, firm_id: str) -> Dict[str, Any]:
        """
        Check company registration status
        
        Args:
            firm_id: Firm identifier
            
        Returns:
            Dict with company registration analysis
        """
        await asyncio.sleep(0.15)  # Simulate API call
        
        # Mock company registration data
        company_data = {
            'ftmocom': {
                'legal_name': 'FTMO s.r.o.',
                'registered': True,
                'country': 'CZ',
                'registration_number': '12345678',
                'status': 'active',
                'founded_year': 2015,
                'company_type': 'Limited Liability Company',
                'regulatory_filings': 'complete'
            },
            'xm': {
                'legal_name': 'XM Global Limited',
                'registered': True,
                'country': 'CY',
                'registration_number': 'HE334408',
                'status': 'active',
                'founded_year': 2009,
                'company_type': 'Private Company',
                'regulatory_filings': 'complete'
            },
            'roboforex': {
                'legal_name': 'RoboForex Ltd',
                'registered': True,
                'country': 'BZ',
                'registration_number': 'unknown',
                'status': 'flagged',  # Suspicious status
                'founded_year': 2009,
                'company_type': 'International Business Company',
                'regulatory_filings': 'incomplete'
            }
        }
        
        data = company_data.get(firm_id, {
            'legal_name': firm_id,
            'registered': True,
            'country': 'Unknown',
            'registration_number': 'unknown',
            'status': 'unknown',
            'founded_year': 2010,
            'company_type': 'Unknown',
            'regulatory_filings': 'unknown'
        })
        
        # Analyze registration
        has_issues = False
        confidence = 0.80
        impact = 0.0
        description = f"Company registration for {firm_id}"
        
        if not data['registered']:
            has_issues = True
            impact = -0.85
            confidence = 0.99
            description = f"{firm_id} NOT FOUND in company registry"
        elif data['status'] == 'flagged':
            has_issues = True
            impact = -0.60
            confidence = 0.90
            description = f"{data['legal_name']} status flagged in registry"
        
        if data['regulatory_filings'] == 'incomplete':
            has_issues = True
            impact = min(impact - 0.25, -0.4)
            confidence = 0.85
            description += " | Regulatory filings incomplete"
        
        if data['country'] in ['BZ', 'VG', 'KY']:  # High-risk jurisdictions
            has_issues = True
            impact = min(impact - 0.20, -0.35)
            confidence = 0.80
            description += f" | Registered in high-risk jurisdiction: {data['country']}"
        
        return {
            'has_issues': has_issues,
            'description': description,
            'confidence': confidence,
            'impact': impact,
            'data': {
                'legal_name': data['legal_name'],
                'country': data['country'],
                'registration_number': data['registration_number'],
                'status': data['status'],
                'founded_year': data['founded_year'],
                'company_type': data['company_type'],
                'filings_status': data['regulatory_filings']
            }
        }
    
    async def _analyze_news_mentions(self, firm_id: str) -> Dict[str, Any]:
        """
        Analyze news mentions and sentiment
        
        Args:
            firm_id: Firm identifier
            
        Returns:
            Dict with news analysis
        """
        await asyncio.sleep(0.18)  # Simulate API call
        
        # Mock news data
        news_data = {
            'ftmocom': {
                'positive_mentions': 45,
                'negative_mentions': 5,
                'neutral_mentions': 30,
                'recent_negative': 1,  # In last 7 days
                'topics': ['funding', 'expansion', 'awards']
            },
            'xm': {
                'positive_mentions': 60,
                'negative_mentions': 12,
                'neutral_mentions': 45,
                'recent_negative': 2,
                'topics': ['partnerships', 'compliance', 'product_launch']
            },
            'roboforex': {
                'positive_mentions': 8,
                'negative_mentions': 35,
                'neutral_mentions': 10,
                'recent_negative': 8,  # Many recent
                'topics': ['fraud', 'payout_issues', 'account_freeze']
            }
        }
        
        data = news_data.get(firm_id, {
            'positive_mentions': 20,
            'negative_mentions': 8,
            'neutral_mentions': 25,
            'recent_negative': 1,
            'topics': []
        })
        
        # Calculate sentiment
        total = data['positive_mentions'] + data['negative_mentions'] + data['neutral_mentions']
        negative_pct = data['negative_mentions'] / total if total > 0 else 0
        
        has_issues = False
        confidence = 0.80
        impact = 0.0
        description = f"News analysis for {firm_id}"
        
        if negative_pct > 0.30:  # >30% negative
            has_issues = True
            impact = -0.55
            confidence = 0.85
            description = f"Significant negative news coverage: {negative_pct*100:.1f}% of mentions"
        elif negative_pct > 0.15:  # 15-30% negative
            has_issues = True
            impact = -0.30
            confidence = 0.80
            description = f"Notable negative mentions: {negative_pct*100:.1f}% of {total} articles"
        
        if data['recent_negative'] > 5:  # Cluster of recent negative
            has_issues = True
            impact = min(impact - 0.25, -0.5)
            confidence = 0.90
            description += f" | {data['recent_negative']} negative articles in last 7 days"
        
        return {
            'has_issues': has_issues,
            'description': description,
            'confidence': confidence,
            'impact': impact,
            'data': {
                'positive_mentions': data['positive_mentions'],
                'negative_mentions': data['negative_mentions'],
                'neutral_mentions': data['neutral_mentions'],
                'negative_percentage': negative_pct * 100,
                'recent_negative_7d': data['recent_negative'],
                'top_topics': data['topics'][:3]
            }
        }
    
    async def _detect_suspicious_patterns(self, firm_id: str) -> Dict[str, Any]:
        """
        Detect suspicious business patterns
        
        Args:
            firm_id: Firm identifier
            
        Returns:
            Dict with pattern analysis
        """
        await asyncio.sleep(0.10)  # Simulate API call
        
        # Mock pattern detection
        pattern_data = {
            'ftmocom': {
                'rapid_jurisdiction_changes': False,
                'multiple_corporate_restructures': False,
                'high_employee_turnover': False,
                'regulatory_license_issues': False,
                'similarity_to_scams': 0.05
            },
            'xm': {
                'rapid_jurisdiction_changes': False,
                'multiple_corporate_restructures': False,
                'high_employee_turnover': False,
                'regulatory_license_issues': False,
                'similarity_to_scams': 0.08
            },
            'roboforex': {
                'rapid_jurisdiction_changes': True,  # Multiple moves
                'multiple_corporate_restructures': True,  # Multiple rebrands
                'high_employee_turnover': True,  # High turnover
                'regulatory_license_issues': True,  # License problems
                'similarity_to_scams': 0.72  # High similarity
            }
        }
        
        patterns = pattern_data.get(firm_id, {
            'rapid_jurisdiction_changes': False,
            'multiple_corporate_restructures': False,
            'high_employee_turnover': False,
            'regulatory_license_issues': False,
            'similarity_to_scams': 0.10
        })
        
        # Count red flags
        red_flags = sum(1 for v in patterns.values() if v is True)
        
        has_issues = False
        confidence = 0.85
        impact = 0.0
        description = f"Pattern analysis for {firm_id}"
        
        if patterns['similarity_to_scams'] > 0.60:  # High fraud similarity
            has_issues = True
            impact = -0.85
            confidence = 0.92
            description = f"CRITICAL: High fraud similarity score ({patterns['similarity_to_scams']:.2f})"
        elif patterns['similarity_to_scams'] > 0.40:  # Moderate fraud similarity
            has_issues = True
            impact = -0.55
            confidence = 0.88
            description = f"Suspicious patterns detected: Fraud similarity {patterns['similarity_to_scams']:.2f}"
        
        if red_flags >= 3:  # 3+ red flags
            has_issues = True
            impact = min(impact - 0.30, -0.6)
            confidence = 0.90
            description += f" | {red_flags} suspicious patterns detected"
        elif red_flags >= 2:  # 2 red flags
            has_issues = True
            impact = min(impact - 0.20, -0.4)
            confidence = 0.85
            description += f" | {red_flags} suspicious patterns detected"
        
        return {
            'has_issues': has_issues,
            'description': description,
            'confidence': confidence,
            'impact': impact,
            'data': {
                'rapid_jurisdiction_changes': patterns['rapid_jurisdiction_changes'],
                'corporate_restructures': patterns['multiple_corporate_restructures'],
                'employee_turnover': patterns['high_employee_turnover'],
                'license_issues': patterns['regulatory_license_issues'],
                'fraud_similarity': patterns['similarity_to_scams'],
                'red_flags': red_flags
            }
        }
    
    def _initialize_domain_data(self) -> Dict[str, DomainInfo]:
        """Initialize mock domain database"""
        return {
            'ftmocom': DomainInfo(
                domain='ftmo.com',
                registrar='Namecheap Inc',
                registration_date=datetime(2015, 3, 12),
                expiry_date=datetime(2025, 3, 12),
                registrant_country='CZ',
                name_servers=['ns1.ftmo.com', 'ns2.ftmo.com'],
                privacy_enabled=False
            ),
            'xm': DomainInfo(
                domain='xm.com',
                registrar='NameDrive Inc',
                registration_date=datetime(2009, 6, 15),
                expiry_date=datetime(2025, 6, 15),
                registrant_country='CY',
                name_servers=['ns1.xm.com', 'ns2.xm.com'],
                privacy_enabled=True
            ),
            'roboforex': DomainInfo(
                domain='roboforex.com',
                registrar='Registrar123',
                registration_date=datetime(2009, 12, 1),
                expiry_date=datetime(2024, 12, 1),
                registrant_country='RU',
                name_servers=['ns1.roboforex.biz', 'ns2.roboforex.biz'],
                privacy_enabled=True
            )
        }


# Test/Demo Execution
if __name__ == '__main__':
    
    async def test_mis_agent():
        """Test MIS Agent"""
        print("\n" + "="*60)
        print("MIS AGENT TEST")
        print("="*60)
        
        agent = MISAgent()
        
        # Test with sample firms
        test_firms = [
            {'firm_id': 'ftmocom', 'name': 'FTMO'},
            {'firm_id': 'xm', 'name': 'XM'},
            {'firm_id': 'roboforex', 'name': 'RoboForex'}
        ]
        
        result = await agent.run(test_firms)
        
        print(f"\nAgent: {result.agent_name}")
        print(f"Status: {result.status}")
        print(f"Firms Processed: {result.firms_processed}")
        print(f"Evidence Items: {result.evidence_collected}")
        print(f"Errors: {len(result.errors)}")
        print(f"\nEvidence Collected:")
        
        if result.data and 'evidence_items' in result.data:
            for i, evidence in enumerate(result.data['evidence_items'], 1):
                print(f"\n  {i}. {evidence.firm_id} - {evidence.evidence_type}")
                print(f"     Source: {evidence.source}")
                print(f"     Confidence: {evidence.confidence_score:.2f}")
                print(f"     Impact: {evidence.impact_score:.2f}")
    
    asyncio.run(test_mis_agent())
