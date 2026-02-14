"""
Prefect Flow Orchestration for GPTI Bot Agents
Phase 2: Agent Orchestration

Schedules and orchestrates all 7 bot agents:
- Daily flows (RVI, REM, IRS, FRP)
- Weekly flows (SSS, IIP)
- Manual flows (MIS)

Includes error handling, retries, and notifications.
"""

from datetime import datetime, time
from typing import List, Dict, Any
import json
import asyncio
import logging

# Prefect 2.x imports
from prefect import flow, task, get_run_logger

logger = logging.getLogger(__name__)


# ============================================================================
# TASKS - Individual agent executions
# ============================================================================

@task(name="run-rvi-agent", description="Execute RVI (Registry Verification) agent", retries=2)
async def task_run_rvi(firms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run RVI agent for all firms"""
    from gpti_bot.agents.rvi_agent import RVIAgent
    
    logger.info(f"Starting RVI agent for {len(firms)} firms")
    agent = RVIAgent()
    result = await agent.execute(firms)
    return result.to_dict()


@task(
    name="run-sss-agent",
    description="Execute SSS (Sanctions Screening) agent",
    retries=2,
    retry_delay_seconds=60,
)
async def task_run_sss(firms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run SSS agent for all firms"""
    from gpti_bot.agents.sss_agent import SSSAgent
    
    logger.info(f"Starting SSS agent for {len(firms)} firms")
    agent = SSSAgent()
    result = await agent.execute(firms)
    return result.to_dict()


@task(
    name="run-rem-agent",
    description="Execute REM (Regulatory Event Monitor) agent",
    retries=2,
    retry_delay_seconds=60,
)
async def task_run_rem(firms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run REM agent for regulatory event monitoring"""
    from gpti_bot.agents.rem_agent import REMAgent
    
    logger.info(f"Starting REM agent for {len(firms)} firms")
    agent = REMAgent()
    result = await agent.execute(firms)
    return result.to_dict()


@task(
    name="run-irs-agent",
    description="Execute IRS (Independent Review System) agent",
    retries=2,
    retry_delay_seconds=60,
)
async def task_run_irs(firms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run IRS agent for submission review"""
    from gpti_bot.agents.irs_agent import IRSAgent
    
    logger.info(f"Starting IRS agent")
    agent = IRSAgent()
    result = await agent.execute(firms)
    return result.to_dict()


@task(
    name="run-frp-agent",
    description="Execute FRP (Firm Reputation & Payout) agent",
    retries=2,
    retry_delay_seconds=60,
)
async def task_run_frp(firms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run FRP agent for reputation and payout assessment"""
    from gpti_bot.agents.frp_agent import FRPAgent
    
    logger.info(f"Starting FRP agent for {len(firms)} firms")
    agent = FRPAgent()
    result = await agent.execute(firms)
    return result.to_dict()


@task(
    name="run-mis-agent",
    description="Execute MIS (Manual Investigation System) agent",
    retries=2,
    retry_delay_seconds=120,
)
async def task_run_mis(firms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run MIS agent for research automation and investigation"""
    from gpti_bot.agents.mis_agent import MISAgent
    
    logger.info(f"Starting MIS agent for {len(firms)} firms")
    agent = MISAgent()
    result = await agent.execute(firms)
    return result.to_dict()


@task(
    name="run-iip-agent",
    description="Execute IIP (IOSCO Reporting) agent",
    retries=2,
    retry_delay_seconds=60,
)
async def task_run_iip(firms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run IIP agent for IOSCO compliance reporting"""
    from gpti_bot.agents.iip_agent import IIPAgent
    
    logger.info(f"Starting IIP agent for {len(firms)} firms")
    agent = IIPAgent()
    result = await agent.execute(firms)
    return result.to_dict()


@task(name="load-firms", description="Load firms from database")
async def task_load_firms(limit: int = None) -> List[Dict[str, Any]]:
    """Load firms from database"""
    try:
        from gpti_bot.db import connect, fetch_firms
    except Exception:
        logger.warning("Unable to import DB helpers, returning empty list")
        return []

    try:
        with connect() as conn:
            firms = fetch_firms(conn, statuses=("candidate", "watchlist", "eligible"), limit=limit or 200)
            logger.info(f"Loaded {len(firms)} firms from database")
            return firms
    except Exception as exc:
        logger.warning(f"Failed to load firms from database: {exc}")
        return []


@task(name="validate-evidence")
async def task_validate_evidence(evidence_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate all collected evidence"""
    logger.info(f"Validating {len(evidence_list)} evidence items")
    
    validation_results = {
        "total": len(evidence_list),
        "valid": 0,
        "invalid": 0,
        "issues": []
    }
    
    for evidence in evidence_list:
        try:
            # Basic validation
            required_fields = ["firm_id", "evidence_type", "collected_by", "raw_data"]
            if all(field in evidence for field in required_fields):
                validation_results["valid"] += 1
            else:
                validation_results["invalid"] += 1
                validation_results["issues"].append(f"Missing fields in {evidence.get('firm_id')}")
        except Exception as e:
            validation_results["invalid"] += 1
            validation_results["issues"].append(str(e))
    
    return validation_results


@task(name="publish-evidence")
async def task_publish_evidence(evidence_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Publish evidence to database"""
    logger.info(f"Publishing {len(evidence_list)} evidence items to database")
    
    publish_results = {
        "attempted": len(evidence_list),
        "published": len(evidence_list),  # Mock - assume all publish successfully
        "failed": 0,
        "errors": []
    }
    
    # In production, this would execute:
    # INSERT INTO evidence (...) VALUES (...)
    
    return publish_results


@task(name="check-agent-health")
async def task_check_agent_health(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Check health of all agents"""
    logger.info(f"Checking health of {len(results)} agent results")
    
    health_report = {
        "timestamp": datetime.now().isoformat(),
        "agents": {result.get("agent_name"): {
            "status": result.get("status"),
            "firms_processed": result.get("firms_processed"),
            "evidence_collected": result.get("evidence_collected"),
            "error_count": len(result.get("errors", [])),
            "duration_seconds": result.get("duration_seconds"),
        } for result in results},
        "critical_issues": [
            f"{r.get('agent_name')}: {e}" 
            for r in results 
            for e in r.get("errors", [])
        ]
    }
    
    return health_report


@task(name="send-notification")
async def task_send_notification(
    message: str,
    severity: str = "info"
) -> bool:
    """Send Slack notification"""
    logger.info(f"[{severity.upper()}] {message}")
    
    # In production: 
    # from gpti_bot.utils.slack_notifier import NotificationHandler
    # handler = NotificationHandler()
    # handler.send_alert(message, severity)
    
    return True


# ============================================================================
# FLOWS - Orchestrated execution
# ============================================================================

@flow(
    name="daily-agent-flow",
    description="Daily execution of RVI, REM, IRS, FRP, MIS agents",
)
async def flow_daily_agents():
    """
    Daily Flow (09:00 UTC)
    - RVI: License verification (10 min)
    - REM: Regulatory event monitoring (15 min)  
    - IRS: Manual submission processing (5 min)
    - FRP: Sentiment/reputation check (10 min)
    - MIS: Research automation (20 min)
    """
    logger.info("Starting daily agent flow")
    
    try:
        # Load firms once
        firms = await task_load_firms(limit=50)
        
        if not firms:
            logger.error("No firms loaded, cannot proceed")
            return {"status": "failed", "reason": "No firms available"}
        
        # Execute agents in sequence
        rvi_result = await task_run_rvi(firms)
        logger.info(f"RVI completed: {rvi_result['firms_processed']} processed")
        
        sss_result = await task_run_sss(firms)
        logger.info(f"SSS completed: {sss_result['firms_processed']} processed")
        
        rem_result = await task_run_rem(firms)
        logger.info(f"REM completed: {rem_result['firms_processed']} processed, {rem_result['evidence_collected']} events found")
        
        irs_result = await task_run_irs(firms)
        logger.info(f"IRS completed: {irs_result['evidence_collected']} submissions verified")
        
        frp_result = await task_run_frp(firms)
        logger.info(f"FRP completed: {frp_result['firms_processed']} processed, {frp_result['evidence_collected']} reputation issues found")
        
        mis_result = await task_run_mis(firms)
        logger.info(f"MIS completed: {mis_result['firms_processed']} investigated, {mis_result['evidence_collected']} anomalies detected")
        
        # Collect all results
        all_results = [rvi_result, sss_result, rem_result, irs_result, frp_result, mis_result]
        
        # Validate and publish evidence
        all_evidence = []
        for result in all_results:
            if "evidence" in result.get("data", {}):
                all_evidence.extend(result["data"]["evidence"])
        
        if all_evidence:
            validation_result = await task_validate_evidence(all_evidence)
            logger.info(f"Validation: {validation_result['valid']} valid, {validation_result['invalid']} invalid")
            
            publish_result = await task_publish_evidence(all_evidence)
            logger.info(f"Published {publish_result['published']} evidence items")
        
        # Check health
        health = await task_check_agent_health(all_results)
        logger.info(f"Agent health: {json.dumps(health, indent=2)}")
        
        # Alert on critical issues
        if health["critical_issues"]:
            for issue in health["critical_issues"]:
                await task_send_notification(issue, severity="warning")
        
        return {
            "status": "success",
            "agents_run": len(all_results),
            "evidence_collected": len(all_evidence),
            "critical_issues": len(health["critical_issues"])
        }
        
    except Exception as e:
        logger.error(f"Daily flow failed: {str(e)}", exc_info=True)
        await task_send_notification(
            f"Daily agent flow failed: {str(e)}",
            severity="critical"
        )
        return {"status": "failed", "reason": str(e)}


@flow(
    name="weekly-agent-flow",
    description="Weekly execution of SSS and IIP agents",
)
async def flow_weekly_agents():
    """
    Weekly Flow (Sunday 00:00 UTC)
    - SSS: Watchlist screening (20 min)
    - IIP: IOSCO reporting (15 min)
    """
    logger.info("Starting weekly agent flow")
    
    try:
        # Load all firms for comprehensive screening
        firms = await task_load_firms()  # All firms
        
        if not firms:
            logger.error("No firms loaded")
            return {"status": "failed"}
        
        # Run comprehensive weekly agents
        sss_result = await task_run_sss(firms)
        logger.info(f"SSS weekly: {sss_result['firms_processed']} screened")
        
        # Generate IOSCO compliance reports
        iip_result = await task_run_iip(firms)
        logger.info(f"IIP completed: {iip_result['firms_processed']} firms reported, {iip_result['evidence_collected']} reports generated")
        
        all_results = [sss_result, iip_result]
        
        # Health check
        health = await task_check_agent_health(all_results)
        
        return {
            "status": "success",
            "agents_run": len(all_results),
            "critical_issues": len(health["critical_issues"])
        }
        
    except Exception as e:
        logger.error(f"Weekly flow failed: {str(e)}")
        return {"status": "failed", "reason": str(e)}


# ============================================================================
# MAIN FLOW - Combines daily and weekly
# ============================================================================

@flow(
    name="main-gpti-agent-flow",
    description="Main orchestration for all GPTI bot agents",
    version="2.0-week1",
)
async def main_flow():
    """
    Main flow that triggers:
    - Daily agents at 09:00 UTC
    - Weekly agents at Sunday 00:00 UTC
    - Manual agents on demand
    """
    logger.info("=== GPTI Agent Orchestration Started ===")
    
    # For initial Phase 2 testing, run daily flow
    daily_result = await flow_daily_agents()
    
    return {
        "status": "success",
        "daily_flow": daily_result,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# TEST & MONITORING
# ============================================================================

if __name__ == "__main__":
    # Run test
    print("Phase 2 Orchestration Flow Test\n")
    
    # Execute main flow
    import asyncio
    result = asyncio.run(main_flow())
    
    print(f"\n\nResult:")
    print(json.dumps(result, indent=2))
    
    print("\n✅ Flow orchestration test complete!")
    print("\nIn production, use: prefect deployment build flows.py -n gpti-agents")
