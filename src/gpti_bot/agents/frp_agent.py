"""
FRP Agent - Firm Reputation & Payout Assessment

Monitors firm reputation, customer reviews, and payout reliability.
Aggregates sentiment from multiple sources (TrustPilot, Reddit, review sites).
Identifies payout issues, complaints, and reputation risks.

Sources:
- TrustPilot API (review aggregation)
- Reddit r/Forex, r/WallStreetBets monitoring
- FTC Complaint Database
- Customer review sites (Trustmary, eToro, etc.)
- News sentiment analysis

Evidence Types:
- Negative review surge (>20% in 7 days)
- Payout complaint cluster (>5 in 30 days)
- Sentiment score drop (>0.3 points weekly)
- Regulatory review signals
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
class ReviewData:
    """Review aggregation data"""
    source: str  # trustpilot, reddit, ftc, etc
    firm_id: str
    sentiment_score: float  # -1.0 to 1.0
    review_count: int
    avg_rating: float  # 1-5
    complaint_keywords: List[str]  # payout, withdrawal, support, etc
    timestamp: datetime


class FRPAgent(Agent):
    """
    Firm Reputation & Payout (FRP) Agent
    
    Monitors reputation metrics and payout reliability indicators.
    Generates evidence when concerning patterns detected.
    """
    
    def __init__(self):
        super().__init__("FRP", frequency="daily")
        self.description = "Firm Reputation & Payout Assessment"
        
        # Mock review data store (would be API in production)
        self.reviews_db = self._initialize_review_data()
    
    async def validate(self, evidence: Evidence) -> bool:
        """
        Validate reputation and payout evidence
        
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
        Main execution method for FRP Agent
        
        Args:
            firms: List of firm dicts with firm_id
            
        Returns:
            AgentResult with evidence items
        """
        try:
            logger.info(f"FRP Agent starting assessment for {len(firms)} firms")
            
            evidence_items = []
            
            for firm in firms:
                firm_id = firm.get('firm_id', '')
                
                # Fetch reputation metrics
                reputation_metrics = await self._fetch_reputation_metrics(firm_id)
                
                # Analyze payout complaints
                payout_issues = await self._analyze_payout_complaints(firm_id)
                
                # Calculate sentiment trend
                sentiment_trend = await self._calculate_sentiment_trend(firm_id)
                
                # Generate evidence if issues found
                if reputation_metrics['has_issues']:
                    evidence = Evidence(
                        firm_id=firm_id,
                        evidence_type='reputation_risk',
                        collected_by='FRP',
                        collected_at=datetime.utcnow(),
                        source='FRP Agent',
                        raw_data=reputation_metrics['data'],
                        validation_status='verified',
                        confidence_score=reputation_metrics['confidence'],
                        impact_score=reputation_metrics['impact']
                    )
                    evidence_items.append(evidence)
                
                if payout_issues['has_issues']:
                    evidence = Evidence(
                        firm_id=firm_id,
                        evidence_type='payout_risk',
                        collected_by='FRP',
                        collected_at=datetime.utcnow(),
                        source='FRP Agent',
                        raw_data=payout_issues['data'],
                        validation_status='verified',
                        confidence_score=payout_issues['confidence'],
                        impact_score=payout_issues['impact']
                    )
                    evidence_items.append(evidence)
                
                if sentiment_trend['is_concerning']:
                    evidence = Evidence(
                        firm_id=firm_id,
                        evidence_type='sentiment_risk',
                        collected_by='FRP',
                        collected_at=datetime.utcnow(),
                        source='FRP Agent',
                        raw_data=sentiment_trend['data'],
                        validation_status='verified',
                        confidence_score=sentiment_trend['confidence'],
                        impact_score=sentiment_trend['impact']
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
                f"FRP Agent completed: {len(evidence_items)} evidence items, "
                f"{critical_issues} critical issues"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"FRP Agent error: {str(e)}", exc_info=True)
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
    
    async def _fetch_reputation_metrics(self, firm_id: str) -> Dict[str, Any]:
        """
        Fetch reputation metrics from multiple sources
        
        Args:
            firm_id: Firm identifier
            
        Returns:
            Dict with reputation data and analysis
        """
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock data based on firm
        firm_metrics = {
            'ftmocom': {
                'trustpilot_rating': 4.2,
                'review_count': 3245,
                'negative_recent': 0.08,  # 8% negative in last 7 days
                'sentiment_score': 0.65,
                'complaint_keywords': ['withdrawal delays', 'support slow']
            },
            'xm': {
                'trustpilot_rating': 3.8,
                'review_count': 5120,
                'negative_recent': 0.15,  # 15% negative in last 7 days
                'sentiment_score': 0.45,
                'complaint_keywords': ['withdrawal delays', 'high spreads', 'support issues']
            },
            'roboforex': {
                'trustpilot_rating': 2.9,
                'review_count': 2110,
                'negative_recent': 0.35,  # 35% negative in last 7 days
                'sentiment_score': 0.05,
                'complaint_keywords': ['payout issues', 'account frozen', 'no support']
            }
        }
        
        metrics = firm_metrics.get(firm_id, {
            'trustpilot_rating': 3.5,
            'review_count': 1000,
            'negative_recent': 0.12,
            'sentiment_score': 0.4,
            'complaint_keywords': ['general concerns']
        })
        
        # Analyze reputation
        has_issues = False
        confidence = 0.8
        impact = 0.0
        description = f"Reputation assessment for {firm_id}"
        
        if metrics['negative_recent'] > 0.25:  # >25% negative
            has_issues = True
            impact = -0.6
            confidence = 0.9
            description = (
                f"High negative review surge: {metrics['negative_recent']*100:.1f}% "
                f"negative reviews in last 7 days"
            )
        elif metrics['negative_recent'] > 0.15:  # 15-25% negative
            has_issues = True
            impact = -0.35
            confidence = 0.85
            description = (
                f"Elevated negative reviews: {metrics['negative_recent']*100:.1f}% "
                f"negative in past week"
            )
        
        return {
            'has_issues': has_issues,
            'description': description,
            'confidence': confidence,
            'impact': impact,
            'data': {
                'trustpilot_rating': metrics['trustpilot_rating'],
                'total_reviews': metrics['review_count'],
                'negative_recent_pct': metrics['negative_recent'] * 100,
                'sentiment_score': metrics['sentiment_score'],
                'top_complaints': metrics['complaint_keywords'][:3]
            }
        }
    
    async def _analyze_payout_complaints(self, firm_id: str) -> Dict[str, Any]:
        """
        Analyze payout-related complaints and issues
        
        Args:
            firm_id: Firm identifier
            
        Returns:
            Dict with payout analysis
        """
        await asyncio.sleep(0.15)  # Simulate API call
        
        # Mock complaint data by firm
        complaint_data = {
            'ftmocom': {
                'complaints_30d': 3,
                'avg_resolution_days': 2,
                'complaint_trend': 'stable',
                'payout_success_rate': 0.99
            },
            'xm': {
                'complaints_30d': 8,
                'avg_resolution_days': 5,
                'complaint_trend': 'increasing',
                'payout_success_rate': 0.96
            },
            'roboforex': {
                'complaints_30d': 24,
                'avg_resolution_days': 15,
                'complaint_trend': 'critical',
                'payout_success_rate': 0.78
            }
        }
        
        data = complaint_data.get(firm_id, {
            'complaints_30d': 5,
            'avg_resolution_days': 7,
            'complaint_trend': 'stable',
            'payout_success_rate': 0.95
        })
        
        # Analyze payout issues
        has_issues = False
        confidence = 0.85
        impact = 0.0
        description = f"Payout analysis for {firm_id}"
        
        if data['complaints_30d'] > 15:  # Critical
            has_issues = True
            impact = -0.75
            confidence = 0.95
            description = (
                f"Critical payout complaints: {data['complaints_30d']} in 30 days, "
                f"{data['avg_resolution_days']:.0f}d avg resolution"
            )
        elif data['complaints_30d'] > 8:  # Elevated
            has_issues = True
            impact = -0.45
            confidence = 0.90
            description = (
                f"Elevated payout complaints: {data['complaints_30d']} in 30 days"
            )
        
        if data['payout_success_rate'] < 0.90:  # <90% success
            has_issues = True
            impact = min(impact - 0.3, -0.5)
            confidence = 0.92
            description += f" | Success rate: {data['payout_success_rate']*100:.1f}%"
        
        return {
            'has_issues': has_issues,
            'description': description,
            'confidence': confidence,
            'impact': impact,
            'data': {
                'complaints_30d': data['complaints_30d'],
                'avg_resolution_days': data['avg_resolution_days'],
                'trend': data['complaint_trend'],
                'payout_success_rate': data['payout_success_rate']
            }
        }
    
    async def _calculate_sentiment_trend(self, firm_id: str) -> Dict[str, Any]:
        """
        Calculate sentiment trend over time
        
        Args:
            firm_id: Firm identifier
            
        Returns:
            Dict with sentiment analysis
        """
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock sentiment data (current vs 4 weeks ago)
        sentiment_history = {
            'ftmocom': {
                'current': 0.65,
                'week_1': 0.68,
                'week_2': 0.67,
                'week_3': 0.66,
                'week_4': 0.65
            },
            'xm': {
                'current': 0.45,
                'week_1': 0.52,
                'week_2': 0.50,
                'week_3': 0.48,
                'week_4': 0.45
            },
            'roboforex': {
                'current': 0.05,
                'week_1': 0.25,
                'week_2': 0.18,
                'week_3': 0.12,
                'week_4': 0.05
            }
        }
        
        history = sentiment_history.get(firm_id, {
            'current': 0.40,
            'week_1': 0.42,
            'week_2': 0.41,
            'week_3': 0.40,
            'week_4': 0.40
        })
        
        # Calculate trend
        initial = history['week_4']
        current = history['current']
        trend = current - initial
        weekly_decline = (initial - current) / 4 if current < initial else 0
        
        is_concerning = False
        confidence = 0.80
        impact = 0.0
        description = f"Sentiment analysis for {firm_id}"
        
        if trend < -0.30:  # Significant decline
            is_concerning = True
            impact = -0.55
            confidence = 0.88
            description = (
                f"Severe sentiment decline: {initial:.2f} → {current:.2f} "
                f"({trend:.3f} over 4 weeks)"
            )
        elif trend < -0.15:  # Moderate decline
            is_concerning = True
            impact = -0.30
            confidence = 0.85
            description = (
                f"Notable sentiment decline: {initial:.2f} → {current:.2f}"
            )
        
        if weekly_decline > 0.08:  # Fast decline rate
            is_concerning = True
            impact = min(impact - 0.2, -0.4)
            confidence = 0.90
            description += f" | Rapid decline rate: {weekly_decline:.3f}/week"
        
        return {
            'is_concerning': is_concerning,
            'description': description,
            'confidence': confidence,
            'impact': impact,
            'data': {
                'current_score': current,
                'initial_score': initial,
                'trend': trend,
                'weekly_decline_rate': weekly_decline,
                'history': history
            }
        }
    
    def _initialize_review_data(self) -> Dict[str, ReviewData]:
        """Initialize mock review database"""
        now = datetime.utcnow()
        
        return {
            'ftmocom': ReviewData(
                source='trustpilot',
                firm_id='ftmocom',
                sentiment_score=0.65,
                review_count=3245,
                avg_rating=4.2,
                complaint_keywords=['withdrawal', 'support'],
                timestamp=now
            ),
            'xm': ReviewData(
                source='trustpilot',
                firm_id='xm',
                sentiment_score=0.45,
                review_count=5120,
                avg_rating=3.8,
                complaint_keywords=['withdrawal', 'spreads', 'support'],
                timestamp=now
            ),
            'roboforex': ReviewData(
                source='trustpilot',
                firm_id='roboforex',
                sentiment_score=0.05,
                review_count=2110,
                avg_rating=2.9,
                complaint_keywords=['payout', 'account', 'no_support'],
                timestamp=now
            )
        }


# Test/Demo Execution
if __name__ == '__main__':
    
    async def test_frp_agent():
        """Test FRP Agent"""
        print("\n" + "="*60)
        print("FRP AGENT TEST")
        print("="*60)
        
        agent = FRPAgent()
        
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
    
    asyncio.run(test_frp_agent())
