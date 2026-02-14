"""
IIP Agent - IOSCO Reporting & Information Platform

Aggregates all bot agent evidence into IOSCO-compliant compliance reports.
Automates regulatory reporting and certification workflows.
Generates standardized compliance evidence packages for regulators.

IOSCO (International Organization of Securities Commissions) Requirements:
- Evidence aggregation from all sources
- Risk scoring and classification
- Regulatory compliance reporting
- Audit trail documentation
- Certification signing and timestamps

Report Sections:
1. Executive Summary (Risk classification, overall score)
2. Evidence Inventory (All 6 agents' findings)
3. Risk Assessment (Categorized by risk level)
4. Remediation Status (Actions taken)
5. Regulatory Certification (Auditor sign-off)
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from abc import ABC
from enum import Enum

from gpti_bot.agents import Agent, Evidence, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class ComplianceStatus(str, Enum):
    """Regulatory compliance status"""
    COMPLIANT = "compliant"
    CONDITIONAL = "conditional"
    NON_COMPLIANT = "non_compliant"
    PENDING_REVIEW = "pending_review"


class RiskLevel(str, Enum):
    """Risk classification levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ComplianceReport:
    """IOSCO compliance report structure"""
    report_id: str
    firm_id: str
    firm_name: str
    report_date: datetime
    risk_level: RiskLevel
    compliance_status: ComplianceStatus
    overall_score: float  # 0-100
    evidence_count: int
    critical_issues: int
    remediation_required: bool
    auditor_name: str = "GPTI System"
    certification_date: Optional[datetime] = None
    notes: str = ""


class IIPAgent(Agent):
    """
    IOSCO Information Platform (IIP) Agent
    
    Final aggregation agent that consolidates all evidence into regulatory reports.
    Generates IOSCO-compliant compliance certifications.
    """
    
    def __init__(self):
        super().__init__("IIP", frequency="weekly")
        self.description = "IOSCO Reporting & Information Platform"
        
        # Firm reference data (would come from database in production)
        self.firm_registry = self._initialize_firm_registry()
    
    async def run(self, firms: List[Dict[str, Any]]) -> AgentResult:
        """
        Main execution method for IIP Agent
        
        Aggregates evidence from all other agents and generates compliance reports.
        
        Args:
            firms: List of firm dicts with firm_id
            
        Returns:
            AgentResult with compliance reports
        """
        try:
            logger.info(f"IIP Agent starting IOSCO reporting for {len(firms)} firms")
            
            evidence_items = []
            reports = []
            
            for firm in firms:
                firm_id = firm.get('firm_id', '')
                firm_name = firm.get('name', firm_id)
                
                # Generate IOSCO report
                report = await self._generate_compliance_report(firm_id, firm_name)
                reports.append(report)
                
                # Create evidence item for regulatory filing
                evidence = Evidence(
                    firm_id=firm_id,
                    evidence_type='compliance_report',
                    collected_by='IIP',
                    collected_at=datetime.utcnow(),
                    source='IIP Agent',
                    raw_data={
                        'report_id': report.report_id,
                        'report_date': report.report_date.isoformat(),
                        'risk_level': report.risk_level.value,
                        'compliance_status': report.compliance_status.value,
                        'overall_score': report.overall_score,
                        'evidence_count': report.evidence_count,
                        'critical_issues': report.critical_issues,
                        'remediation_required': report.remediation_required,
                        'notes': report.notes
                    },
                    validation_status='verified',
                    confidence_score=0.95,
                    impact_score=self._calculate_report_impact(report)
                )
                evidence_items.append(evidence)
            
            # Summary statistics
            critical_count = sum(1 for r in reports if r.risk_level == RiskLevel.CRITICAL)
            high_count = sum(1 for r in reports if r.risk_level == RiskLevel.HIGH)
            compliant_count = sum(1 for r in reports if r.compliance_status == ComplianceStatus.COMPLIANT)
            
            result = AgentResult(
                agent_name=self.name,
                status=AgentStatus.SUCCESS,
                timestamp=datetime.utcnow(),
                firms_processed=len(firms),
                evidence_collected=len(evidence_items),
                errors=[],
                warnings=[],
                duration_seconds=0.0,
                data={
                    'evidence_items': evidence_items,
                    'reports': [self._report_to_dict(r) for r in reports],
                    'summary': {
                        'total_firms': len(firms),
                        'critical_risk': critical_count,
                        'high_risk': high_count,
                        'compliant': compliant_count,
                        'reports_generated': len(reports)
                    }
                }
            )
            
            logger.info(
                f"IIP Agent completed: {len(reports)} reports generated, "
                f"{critical_count} critical, {compliant_count} compliant"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"IIP Agent error: {str(e)}", exc_info=True)
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
    
    async def validate(self, evidence: Evidence) -> bool:
        """
        Validate compliance report evidence
        
        Args:
            evidence: Evidence to validate
            
        Returns:
            True if evidence is valid
        """
        # Validate required fields
        if not evidence.firm_id or not evidence.data:
            return False
        
        # Validate report structure
        required_fields = ['report_id', 'risk_level', 'compliance_status', 'overall_score']
        if not all(field in evidence.data for field in required_fields):
            return False
        
        # Validate score range
        score = evidence.data.get('overall_score', -1)
        if not (0 <= score <= 100):
            return False
        
        return True
    
    async def _generate_compliance_report(
        self, 
        firm_id: str, 
        firm_name: str
    ) -> ComplianceReport:
        """
        Generate IOSCO compliance report for firm
        
        Args:
            firm_id: Firm identifier
            firm_name: Firm display name
            
        Returns:
            ComplianceReport object
        """
        await asyncio.sleep(0.2)  # Simulate aggregation time
        
        # Mock evidence from all agents (in production, would aggregate real evidence)
        firm_evidence = {
            'ftmocom': {
                'evidence_count': 3,
                'critical_issues': 0,
                'rvi_status': 'verified',
                'sss_status': 'no_matches',
                'rem_status': 'no_events',
                'irs_status': 'compliant',
                'frp_status': 'good',
                'mis_status': 'clean'
            },
            'xm': {
                'evidence_count': 5,
                'critical_issues': 1,
                'rvi_status': 'verified',
                'sss_status': 'no_matches',
                'rem_status': 'no_events',
                'irs_status': 'compliant',
                'frp_status': 'moderate',
                'mis_status': 'clean'
            },
            'roboforex': {
                'evidence_count': 12,
                'critical_issues': 6,
                'rvi_status': 'suspended',
                'sss_status': 'matches_found',
                'rem_status': 'events_found',
                'irs_status': 'complaints',
                'frp_status': 'severe',
                'mis_status': 'critical'
            }
        }
        
        evidence = firm_evidence.get(firm_id, {
            'evidence_count': 2,
            'critical_issues': 0,
            'rvi_status': 'unknown',
            'sss_status': 'unknown',
            'rem_status': 'unknown',
            'irs_status': 'unknown',
            'frp_status': 'unknown',
            'mis_status': 'unknown'
        })
        
        # Calculate risk level and compliance status
        risk_level, compliance_status, overall_score = self._assess_compliance(evidence)
        
        # Generate report
        report = ComplianceReport(
            report_id=f"IOSCO-{firm_id.upper()}-{datetime.utcnow().strftime('%Y%m%d')}",
            firm_id=firm_id,
            firm_name=firm_name,
            report_date=datetime.utcnow(),
            risk_level=risk_level,
            compliance_status=compliance_status,
            overall_score=overall_score,
            evidence_count=evidence['evidence_count'],
            critical_issues=evidence['critical_issues'],
            remediation_required=compliance_status != ComplianceStatus.COMPLIANT,
            auditor_name="GPTI System",
            certification_date=datetime.utcnow(),
            notes=self._generate_report_notes(evidence, risk_level)
        )
        
        return report
    
    def _assess_compliance(self, evidence: Dict[str, Any]) -> Tuple[RiskLevel, ComplianceStatus, float]:
        """
        Assess compliance status from aggregated evidence
        
        Args:
            evidence: Evidence dictionary
            
        Returns:
            Tuple of (RiskLevel, ComplianceStatus, score)
        """
        critical = evidence.get('critical_issues', 0)
        total_evidence = evidence.get('evidence_count', 0)
        
        # Risk classification logic
        if critical >= 5:
            risk = RiskLevel.CRITICAL
            score = 20
            status = ComplianceStatus.NON_COMPLIANT
        elif critical >= 3:
            risk = RiskLevel.HIGH
            score = 40
            status = ComplianceStatus.CONDITIONAL
        elif critical >= 1:
            risk = RiskLevel.MEDIUM
            score = 65
            status = ComplianceStatus.CONDITIONAL
        else:
            risk = RiskLevel.LOW
            score = 85
            status = ComplianceStatus.COMPLIANT
        
        return risk, status, score
    
    def _generate_report_notes(self, evidence: Dict[str, Any], risk_level: RiskLevel) -> str:
        """
        Generate human-readable report notes
        
        Args:
            evidence: Evidence data
            risk_level: Risk classification
            
        Returns:
            Report notes string
        """
        notes = []
        
        if evidence.get('rvi_status') == 'suspended':
            notes.append("License suspended or not verified with regulatory authorities")
        
        if evidence.get('sss_status') == 'matches_found':
            notes.append("Entity identified on international sanctions/watchlists")
        
        if evidence.get('rem_status') == 'events_found':
            notes.append("Regulatory enforcement actions or warnings identified")
        
        if evidence.get('irs_status') == 'complaints':
            notes.append("Customer complaints or submission issues documented")
        
        if evidence.get('frp_status') == 'severe':
            notes.append("Reputation risk and payout reliability concerns identified")
        
        if evidence.get('mis_status') == 'critical':
            notes.append("Investigation anomalies detected (domain, company, news, fraud patterns)")
        
        if not notes:
            notes.append("Firm meets compliance requirements. Regular monitoring recommended.")
        
        return " | ".join(notes)
    
    def _calculate_report_impact(self, report: ComplianceReport) -> float:
        """
        Calculate impact score for compliance report
        
        Args:
            report: ComplianceReport
            
        Returns:
            Impact score (-1.0 to 1.0)
        """
        if report.compliance_status == ComplianceStatus.COMPLIANT:
            return 0.0  # No negative impact
        elif report.compliance_status == ComplianceStatus.CONDITIONAL:
            return -0.4  # Moderate concern
        else:  # NON_COMPLIANT
            return -0.8  # Severe concern
    
    def _report_to_dict(self, report: ComplianceReport) -> Dict[str, Any]:
        """Convert report to dict for JSON serialization"""
        return {
            'report_id': report.report_id,
            'firm_id': report.firm_id,
            'firm_name': report.firm_name,
            'report_date': report.report_date.isoformat(),
            'risk_level': report.risk_level.value,
            'compliance_status': report.compliance_status.value,
            'overall_score': report.overall_score,
            'evidence_count': report.evidence_count,
            'critical_issues': report.critical_issues,
            'remediation_required': report.remediation_required,
            'auditor_name': report.auditor_name,
            'certification_date': report.certification_date.isoformat() if report.certification_date else None,
            'notes': report.notes
        }
    
    def _initialize_firm_registry(self) -> Dict[str, Dict[str, str]]:
        """Initialize mock firm registry"""
        return {
            'ftmocom': {'name': 'FTMO', 'jurisdiction': 'CZ', 'type': 'Proprietary Trading'},
            'xm': {'name': 'XM', 'jurisdiction': 'CY', 'type': 'Forex Broker'},
            'roboforex': {'name': 'RoboForex', 'jurisdiction': 'BZ', 'type': 'Forex Broker'}
        }


# Test/Demo Execution
if __name__ == '__main__':
    
    async def test_iip_agent():
        """Test IIP Agent"""
        print("\n" + "="*70)
        print("IIP AGENT TEST - IOSCO Reporting & Information Platform")
        print("="*70)
        
        agent = IIPAgent()
        
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
        print(f"Reports Generated: {result.evidence_collected}")
        print(f"Errors: {len(result.errors)}")
        
        # Display reports
        print(f"\n{'─'*70}")
        print("IOSCO COMPLIANCE REPORTS:")
        print(f"{'─'*70}")
        
        if result.data and 'reports' in result.data:
            for i, report in enumerate(result.data['reports'], 1):
                print(f"\n{i}. {report['firm_name']} ({report['firm_id']})")
                print(f"   Report ID: {report['report_id']}")
                print(f"   Risk Level: {report['risk_level'].upper()}")
                print(f"   Compliance: {report['compliance_status'].upper()}")
                print(f"   Overall Score: {report['overall_score']}/100")
                print(f"   Evidence Items: {report['evidence_count']}")
                print(f"   Critical Issues: {report['critical_issues']}")
                print(f"   Remediation Required: {report['remediation_required']}")
                print(f"   Notes: {report['notes']}")
        
        # Summary statistics
        if result.data and 'summary' in result.data:
            summary = result.data['summary']
            print(f"\n{'─'*70}")
            print("SUMMARY STATISTICS:")
            print(f"{'─'*70}")
            print(f"Total Firms Reported: {summary['total_firms']}")
            print(f"Critical Risk: {summary['critical_risk']}")
            print(f"High Risk: {summary['high_risk']}")
            print(f"Compliant: {summary['compliant']}")
            print(f"Reports Generated: {summary['reports_generated']}")
    
    asyncio.run(test_iip_agent())
