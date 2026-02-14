"""
Agent Base Class - Foundation for all 7 data collection agents
Phase 2: Real Data Collection
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent execution status"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"


class EvidenceType(str, Enum):
    """Types of evidence that agents collect"""
    LICENSE_VERIFICATION = "license_verification"
    WATCHLIST_MATCH = "watchlist_match"
    REGULATORY_EVENT = "regulatory_event"
    SUBMISSION_VERIFICATION = "submission_verification"
    REPUTATION_SENTIMENT = "reputation_sentiment"
    INVESTIGATION_REPORT = "investigation_report"
    COMPLIANCE_REPORT = "compliance_report"


@dataclass
class AgentResult:
    """Standard result format for all agents"""
    agent_name: str
    status: AgentStatus
    timestamp: datetime
    firms_processed: int
    evidence_collected: int
    errors: List[str]
    warnings: List[str]
    duration_seconds: float
    data: Dict[str, Any]  # Agent-specific results
    
    def to_dict(self):
        """Convert result to dict for JSON serialization"""
        result = asdict(self)
        result['status'] = self.status.value
        result['timestamp'] = self.timestamp.isoformat()
        return result


@dataclass
class Evidence:
    """Evidence data collected by agents"""
    firm_id: str
    evidence_type: EvidenceType
    collected_by: str  # Agent name (RVI, SSS, REM, etc.)
    collected_at: datetime
    source: str  # "FCA", "TrustPilot", "SEC", etc.
    raw_data: Dict[str, Any]
    validation_status: str = "pending"  # pending, verified, disputed
    confidence_score: float = 1.0  # 0.0 - 1.0
    impact_score: float = 0.0  # -1.0 to 1.0 (negative = bad for firm)
    
    def to_dict(self):
        result = asdict(self)
        result['evidence_type'] = self.evidence_type.value
        result['collected_at'] = self.collected_at.isoformat()
        return result


class Agent(ABC):
    """
    Base class for all data collection agents.
    Subclasses: RVI, SSS, REM, IRS, FRP, MIS, IIP
    """
    
    def __init__(self, name: str, frequency: str = "daily"):
        """
        Initialize agent.
        
        Args:
            name: Agent identifier (RVI, SSS, REM, IRS, FRP, MIS, IIP)
            frequency: Execution frequency (daily, weekly, monthly, manual)
        """
        self.name = name
        self.frequency = frequency
        self.status = AgentStatus.IDLE
        self.last_run: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.error_count = 0
        self.success_count = 0
        self.run_count = 0
        
        # Logging
        self.logger = logging.getLogger(f"gpti_agent.{self.name.lower()}")
    
    @abstractmethod
    async def run(self, firms: List[Dict[str, Any]]) -> AgentResult:
        """
        Execute agent logic.
        
        Args:
            firms: List of firm dicts to process
            
        Returns:
            AgentResult with collected evidence and status
        """
        pass
    
    @abstractmethod
    async def validate(self, evidence: Evidence) -> bool:
        """
        Validate collected evidence before publishing.
        
        Args:
            evidence: Evidence to validate
            
        Returns:
            True if valid, False otherwise
        """
        pass
    
    async def execute(self, firms: List[Dict[str, Any]]) -> AgentResult:
        """
        High-level execution wrapper with error handling.
        
        Args:
            firms: Firms to process
            
        Returns:
            AgentResult
        """
        start_time = datetime.now()
        self.status = AgentStatus.RUNNING
        self.run_count += 1
        
        try:
            result = await self.run(firms)
            
            self.status = AgentStatus.SUCCESS
            self.success_count += 1
            self.last_run = datetime.now()
            
            self.logger.info(
                f"{self.name} executed successfully: "
                f"{result.firms_processed} firms, "
                f"{result.evidence_collected} evidence items"
            )
            
            return result
            
        except Exception as e:
            self.status = AgentStatus.FAILED
            self.error_count += 1
            self.last_error = str(e)
            
            self.logger.error(f"{self.name} failed: {str(e)}", exc_info=True)
            
            duration = (datetime.now() - start_time).total_seconds()
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                timestamp=datetime.now(),
                firms_processed=0,
                evidence_collected=0,
                errors=[str(e)],
                warnings=[],
                duration_seconds=duration,
                data={}
            )
    
    async def publish_evidence(
        self, 
        evidence: Evidence, 
        db_connection
    ) -> bool:
        """
        Publish evidence to database after validation.
        
        Args:
            evidence: Evidence to publish
            db_connection: Database connection
            
        Returns:
            True if published successfully
        """
        try:
            # Validate first
            if not await self.validate(evidence):
                evidence.validation_status = "disputed"
                self.logger.warning(f"Evidence validation failed: {evidence.firm_id}")
                return False
            
            # Insert into database
            query = """
            INSERT INTO evidence (
                firm_id, evidence_type, collected_by, collected_at, 
                source, raw_data, validation_status, 
                confidence_score, impact_score
            ) VALUES (
                :firm_id, :evidence_type, :collected_by, :collected_at,
                :source, :raw_data, :validation_status,
                :confidence_score, :impact_score
            )
            """
            
            evidence.validation_status = "verified"
            params = evidence.to_dict()
            params['evidence_type'] = evidence.evidence_type.value
            params['raw_data'] = json.dumps(evidence.raw_data)
            
            await db_connection.execute(query, params)
            self.logger.info(f"Published evidence for {evidence.firm_id}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to publish evidence: {str(e)}")
            return False
    
    def get_health(self) -> Dict[str, Any]:
        """
        Get agent health metrics for monitoring.
        
        Returns:
            Health status dict
        """
        return {
            "agent_name": self.name,
            "frequency": self.frequency,
            "status": self.status.value,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_error": self.last_error,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": (
                self.success_count / self.run_count 
                if self.run_count > 0 else 0
            ) * 100
        }
    
    def __repr__(self) -> str:
        return (
            f"{self.name} Agent (status={self.status.value}, "
            f"runs={self.run_count}, errors={self.error_count})"
        )
