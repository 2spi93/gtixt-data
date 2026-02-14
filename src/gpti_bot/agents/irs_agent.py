"""
IRS Agent - Independent Review System
Phase 2: Week 2

Purpose:
- Handle manual evidence submissions from users/partners
- Verify submitted evidence against known sources
- Assign high-impact submissions to human curators
- Document verification decisions
- Update evidence database with verified facts

Data Sources:
- Web form submissions (contact form)
- Partner API submissions
- Email submissions
- Manual curator research results
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
from dataclasses import dataclass
from enum import Enum

from gpti_bot.agents import Agent, AgentStatus, AgentResult, Evidence, EvidenceType

logger = logging.getLogger(__name__)


class SubmissionType(str, Enum):
    """Type of submission"""
    USER_REPORT = "user_report"
    PARTNER_API = "partner_api"
    EMAIL = "email"
    CURATOR_RESEARCH = "curator_research"


class VerificationStatus(str, Enum):
    """Verification decision"""
    AUTO_VERIFIED = "auto_verified"
    PENDING_REVIEW = "pending_review"
    CURATOR_VERIFIED = "curator_verified"
    CURATOR_REJECTED = "curator_rejected"
    DISPUTED = "disputed"


@dataclass
class Submission:
    """A user/partner submission"""
    submission_id: str
    firm_id: str
    firm_name: str
    submission_type: SubmissionType
    submitted_by: str  # Email or partner ID
    submitted_at: str
    claim: str  # The evidence being submitted
    claim_type: str  # license_issue, payout_problem, customer_complaint, etc.
    severity: str  # critical, high, medium, low
    source_description: str  # Where the claim comes from
    supporting_evidence: List[str]  # URLs or references
    
    # Verification fields
    auto_verified: bool = False
    requires_curator: bool = False
    curator_assigned: Optional[str] = None
    curator_decision: Optional[str] = None
    curator_notes: Optional[str] = None
    confidence_score: float = 0.0


class IRSAgent(Agent):
    """Independent Review System Agent"""
    
    def __init__(self):
        super().__init__("IRS", frequency="daily")
        
        # Test submissions - in production would come from database
        self.test_submissions = [
            Submission(
                submission_id="SUB-2026-001",
                firm_id="ftmocom",
                firm_name="FTMO",
                submission_type=SubmissionType.USER_REPORT,
                submitted_by="trader@example.com",
                submitted_at="2026-01-30T10:30:00Z",
                claim="Withdrawal request denied without proper explanation",
                claim_type="payout_problem",
                severity="high",
                source_description="Direct customer report",
                supporting_evidence=["email screenshot", "support ticket #12345"],
                auto_verified=False,
                requires_curator=True,
            ),
            Submission(
                submission_id="SUB-2026-002",
                firm_id="xmglobal",
                firm_name="XM Global",
                submission_type=SubmissionType.PARTNER_API,
                submitted_by="partner_zenith@xmglobal.com",
                submitted_at="2026-01-29T14:20:00Z",
                claim="Updated compliance certification issued",
                claim_type="regulatory_approval",
                severity="low",
                source_description="Partner notification",
                supporting_evidence=["cert_url_link"],
                auto_verified=True,
                requires_curator=False,
                confidence_score=0.92,
            ),
            Submission(
                submission_id="SUB-2026-003",
                firm_id="roboforex",
                firm_name="RoboForex",
                submission_type=SubmissionType.EMAIL,
                submitted_by="support@trader-forum.com",
                submitted_at="2026-01-28T08:15:00Z",
                claim="Multiple negative reviews mentioning fund segregation issues",
                claim_type="customer_complaint",
                severity="critical",
                source_description="Aggregated forum reports",
                supporting_evidence=["forum_link_1", "forum_link_2", "forum_link_3"],
                auto_verified=False,
                requires_curator=True,
            ),
        ]
    
    async def run(self, firms: List[Dict[str, Any]]) -> AgentResult:
        """
        Execute independent review system.
        
        Args:
            firms: List of firms (for reference)
            
        Returns:
            AgentResult with review results
        """
        start_time = datetime.now()
        evidence_items: List[Evidence] = []
        errors = []
        
        try:
            auto_verified_count = 0
            curator_assigned_count = 0
            
            # Get pending submissions (test data for Week 2)
            submissions = await self._get_pending_submissions()
            
            for submission in submissions:
                try:
                    # Determine verification path
                    if submission.auto_verified:
                        # Auto-verified submissions go directly to evidence
                        auto_verified_count += 1
                        evidence = await self._create_evidence(submission)
                        evidence_items.append(evidence)
                        logger.info(f"IRS: Auto-verified {submission.submission_id}")
                        
                    elif submission.requires_curator:
                        # High-impact submissions assigned to curator
                        curator_assigned_count += 1
                        await self._assign_to_curator(submission)
                        logger.info(f"IRS: Assigned {submission.submission_id} to curator")
                        
                except Exception as e:
                    error_msg = f"Error processing {submission.submission_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return AgentResult(
                agent_name="IRS",
                status=AgentStatus.SUCCESS,
                timestamp=datetime.now(),
                firms_processed=len(set(s.firm_id for s in submissions)),
                evidence_collected=len(evidence_items),
                errors=errors,
                warnings=[],
                duration_seconds=duration,
                data={
                    "evidence": [e.to_dict() for e in evidence_items],
                    "summary": {
                        "submissions_reviewed": len(submissions),
                        "auto_verified": auto_verified_count,
                        "curator_assigned": curator_assigned_count,
                        "submission_types": self._count_submission_types(submissions),
                        "severity_distribution": self._count_severity(submissions),
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"IRS Agent failed: {str(e)}", exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            return AgentResult(
                agent_name="IRS",
                status=AgentStatus.FAILED,
                timestamp=datetime.now(),
                firms_processed=0,
                evidence_collected=0,
                errors=[str(e)],
                warnings=[],
                duration_seconds=duration,
                data={}
            )
    
    async def _get_pending_submissions(self) -> List[Submission]:
        """
        Get pending submissions from submission queue.
        
        In production, would query:
        - PostgreSQL submissions table
        - Email inbox (POP3/IMAP)
        - Partner API webhooks
        - Contact form submissions
        
        For Phase 2 Week 2, using test data.
        
        Returns:
            List of pending submissions
        """
        # Simulate API call
        await asyncio.sleep(0.5)
        
        logger.info(f"Retrieved {len(self.test_submissions)} submissions for review")
        return self.test_submissions
    
    async def _create_evidence(self, submission: Submission) -> Evidence:
        """
        Create evidence item from verified submission.
        
        Args:
            submission: Verified submission
            
        Returns:
            Evidence object
        """
        evidence = Evidence(
            firm_id=submission.firm_id,
            evidence_type=EvidenceType.SUBMISSION_VERIFICATION,
            collected_by="IRS",
            collected_at=datetime.now(),
            source="User Submission",
            raw_data={
                "submission_id": submission.submission_id,
                "submission_type": submission.submission_type.value,
                "claim": submission.claim,
                "claim_type": submission.claim_type,
                "severity": submission.severity,
                "source_description": submission.source_description,
                "supporting_evidence": submission.supporting_evidence,
                "submitted_by": submission.submitted_by,
                "submitted_at": submission.submitted_at,
                "verification_status": "auto_verified",
            },
            validation_status="verified",
            confidence_score=submission.confidence_score,
            impact_score=self._calculate_impact(submission)
        )
        
        return evidence
    
    async def _assign_to_curator(self, submission: Submission) -> None:
        """
        Assign high-impact submission to human curator.
        
        In production, would:
        1. Find next available curator
        2. Create assignment in database
        3. Send notification email
        4. Update submission status
        5. Set deadline for review
        
        Args:
            submission: Submission to assign
        """
        # Mock curator assignment
        curators = ["curator1@gpti.org", "curator2@gpti.org", "curator3@gpti.org"]
        assigned_curator = curators[hash(submission.submission_id) % len(curators)]
        
        submission.curator_assigned = assigned_curator
        
        logger.info(
            f"Assigned {submission.submission_id} to {assigned_curator} "
            f"(severity: {submission.severity})"
        )
    
    async def validate(self, evidence: Evidence) -> bool:
        """
        Validate submission evidence.
        
        Checks:
        - Required fields present
        - Claim type is valid
        - Severity is valid
        - Supporting evidence not empty
        - Confidence score valid
        
        Args:
            evidence: Evidence to validate
            
        Returns:
            True if valid
        """
        try:
            data = evidence.raw_data
            
            # Check required fields
            required = ["submission_id", "claim", "claim_type", "severity"]
            if not all(data.get(f) for f in required):
                logger.warning(f"Missing required fields in submission")
                return False
            
            # Check claim type
            valid_types = [
                "license_issue", "payout_problem", "customer_complaint",
                "regulatory_approval", "fund_segregation", "other"
            ]
            if data.get("claim_type") not in valid_types:
                logger.warning(f"Invalid claim type: {data.get('claim_type')}")
                return False
            
            # Check severity
            valid_severities = ["critical", "high", "medium", "low"]
            if data.get("severity") not in valid_severities:
                logger.warning(f"Invalid severity: {data.get('severity')}")
                return False
            
            # Check supporting evidence
            if not data.get("supporting_evidence"):
                logger.warning("Missing supporting evidence")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            return False
    
    def _calculate_impact(self, submission: Submission) -> float:
        """
        Calculate impact score for submission.
        
        Negative impact: payout issues, segregation violations
        Medium impact: customer complaints
        Low impact: approvals, positive developments
        
        Args:
            submission: Submission
            
        Returns:
            Impact score (-1.0 to +1.0)
        """
        severity_impact = {
            "critical": -0.9,
            "high": -0.5,
            "medium": -0.2,
            "low": 0.1,
        }
        
        base_impact = severity_impact.get(submission.severity, 0.0)
        
        # Type modifiers
        type_multiplier = 1.0
        if submission.claim_type in ["payout_problem", "fund_segregation"]:
            type_multiplier = 1.2  # More serious
        elif submission.claim_type == "regulatory_approval":
            base_impact = 0.3  # Positive
        
        return base_impact * type_multiplier
    
    def _count_submission_types(
        self, 
        submissions: List[Submission]
    ) -> Dict[str, int]:
        """Count submissions by type"""
        counts = {}
        for sub in submissions:
            key = sub.submission_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts
    
    def _count_severity(self, submissions: List[Submission]) -> Dict[str, int]:
        """Count submissions by severity"""
        counts = {}
        for sub in submissions:
            counts[sub.severity] = counts.get(sub.severity, 0) + 1
        return counts


# Quick test
if __name__ == "__main__":
    import json
    
    async def test():
        agent = IRSAgent()
        
        result = await agent.run([])
        print(f"\n{agent.name} Result:")
        print(json.dumps(result.to_dict(), indent=2))
