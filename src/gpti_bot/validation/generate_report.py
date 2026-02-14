#!/usr/bin/env python3
"""
Transparency Report Generator
Created: 2026-02-01
Phase: 1 (Validation Framework) - Week 3

Purpose:
- Auto-generate monthly transparency reports
- Include all 6 validation test results
- IOSCO Article 16 compliance (Public Disclosure)
- PDF format for distribution

Requirements:
- All validation tests must be run
- Historical comparison (if available)
- Executive summary + detailed findings
- Charts and visualizations
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


class TransparencyReportGenerator:
    """Generate IOSCO-compliant transparency reports"""
    
    def __init__(self, snapshot_data: Dict[str, Any], output_dir: str = "reports"):
        """
        Initialize report generator
        
        Args:
            snapshot_data: Complete snapshot with records and metadata
            output_dir: Directory to save generated reports
        """
        self.snapshot = snapshot_data
        self.records = snapshot_data.get("records", [])
        self.metadata = snapshot_data.get("metadata", {})
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.validation_results = {}
        self.report_data = {}
    
    def run_all_validations(self) -> Dict[str, Any]:
        """
        Execute all 6 validation tests
        
        Returns:
            Combined validation results
        """
        logger.info("Running all validation tests...")
        
        # Import test modules
        try:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            
            from gpti_bot.validation.test_coverage import run_coverage_test
            from gpti_bot.validation.test_stability import run_stability_test
            from gpti_bot.validation.test_calibration import run_calibration_test
            
            # Run each test
            self.validation_results['coverage'] = run_coverage_test(self.snapshot)
            self.validation_results['stability'] = run_stability_test(
                self.snapshot,
                previous_snapshot=None  # Use fallback mode
            )
            self.validation_results['calibration'] = run_calibration_test(self.snapshot)
            
            # Tests 3, 4, 6 not yet implemented
            self.validation_results['ground_truth'] = self._placeholder_test("ground_truth")
            self.validation_results['soft_signals'] = self._placeholder_test("soft_signals")
            self.validation_results['agent_health'] = self._placeholder_test("agent_health")
            
            logger.info("All validation tests complete")
            
        except Exception as e:
            logger.error(f"Error running validations: {e}")
            raise
        
        return self.validation_results
    
    def _placeholder_test(self, test_name: str) -> Dict[str, Any]:
        """Placeholder for not-yet-implemented tests"""
        return {
            "test_name": test_name,
            "timestamp": datetime.utcnow().isoformat(),
            "passed": None,
            "status": "NOT_IMPLEMENTED",
            "metrics": {},
            "alerts": [f"Test {test_name} not yet implemented"],
            "details": {}
        }
    
    def generate_report(self) -> Dict[str, Any]:
        """
        Generate complete transparency report
        
        Returns:
            Report data structure
        """
        logger.info("Generating transparency report...")
        
        # Run validations if not already done
        if not self.validation_results:
            self.run_all_validations()
        
        # Build report structure
        self.report_data = {
            "report_metadata": {
                "title": "GPTI Validation Framework - Monthly Transparency Report",
                "generated_at": datetime.utcnow().isoformat(),
                "reporting_period": self._get_reporting_period(),
                "snapshot_id": self.metadata.get("version", "unknown"),
                "total_firms": len(self.records),
                "iosco_compliance": "Article 16 - Public Disclosure"
            },
            "executive_summary": self._generate_executive_summary(),
            "validation_results": self._format_validation_results(),
            "data_quality_metrics": self._calculate_data_quality_metrics(),
            "coverage_analysis": self._generate_coverage_analysis(),
            "stability_analysis": self._generate_stability_analysis(),
            "calibration_analysis": self._generate_calibration_analysis(),
            "recommendations": self._generate_recommendations(),
            "appendix": self._generate_appendix()
        }
        
        logger.info("Report generation complete")
        return self.report_data
    
    def _get_reporting_period(self) -> str:
        """Get current reporting period (month/year)"""
        now = datetime.utcnow()
        return now.strftime("%B %Y")
    
    def _generate_executive_summary(self) -> Dict[str, Any]:
        """Generate executive summary section"""
        total_tests = len(self.validation_results)
        passed_tests = sum(
            1 for r in self.validation_results.values() 
            if r.get('passed') is True
        )
        failed_tests = sum(
            1 for r in self.validation_results.values() 
            if r.get('passed') is False
        )
        
        # Count total alerts
        total_alerts = sum(
            len(r.get('alerts', [])) 
            for r in self.validation_results.values()
        )
        
        return {
            "overview": f"This report covers validation testing for {len(self.records)} "
                       f"firms in the GPTI universe for {self._get_reporting_period()}.",
            "test_summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "not_implemented": total_tests - passed_tests - failed_tests
            },
            "overall_health": "GOOD" if failed_tests <= 1 else "NEEDS_ATTENTION",
            "total_alerts": total_alerts,
            "key_findings": [
                f"{passed_tests}/{total_tests} validation tests passed",
                f"{total_alerts} alerts requiring attention",
                f"{len(self.records)} firms monitored"
            ]
        }
    
    def _format_validation_results(self) -> Dict[str, Any]:
        """Format validation results for report"""
        formatted = {}
        
        for test_name, result in self.validation_results.items():
            formatted[test_name] = {
                "status": "PASS" if result.get('passed') else "FAIL" if result.get('passed') is False else "NOT_RUN",
                "timestamp": result.get('timestamp'),
                "key_metrics": result.get('metrics', {}),
                "alert_count": len(result.get('alerts', [])),
                "top_alerts": result.get('alerts', [])[:3]  # Top 3 alerts
            }
        
        return formatted
    
    def _calculate_data_quality_metrics(self) -> Dict[str, Any]:
        """Calculate overall data quality metrics"""
        if not self.records:
            return {}
        
        total_na_rate = sum(r.get('na_rate', 0) for r in self.records) / len(self.records)
        avg_score = sum(r.get('score_0_100', 0) for r in self.records) / len(self.records)
        
        # Confidence distribution
        confidence_dist = {
            'high': len([r for r in self.records if r.get('confidence') == 'high']),
            'medium': len([r for r in self.records if r.get('confidence') == 'medium']),
            'low': len([r for r in self.records if r.get('confidence') == 'low'])
        }
        
        return {
            "avg_na_rate": round(total_na_rate, 2),
            "avg_score": round(avg_score, 2),
            "confidence_distribution": confidence_dist,
            "data_completeness": round(100 - total_na_rate, 2)
        }
    
    def _generate_coverage_analysis(self) -> Dict[str, Any]:
        """Generate coverage analysis section"""
        coverage_result = self.validation_results.get('coverage', {})
        
        return {
            "status": "PASS" if coverage_result.get('passed') else "FAIL",
            "metrics": coverage_result.get('metrics', {}),
            "details": coverage_result.get('details', {}),
            "recommendations": self._coverage_recommendations(coverage_result)
        }
    
    def _generate_stability_analysis(self) -> Dict[str, Any]:
        """Generate stability analysis section"""
        stability_result = self.validation_results.get('stability', {})
        
        return {
            "status": "PASS" if stability_result.get('passed') else "FAIL",
            "metrics": stability_result.get('metrics', {}),
            "details": stability_result.get('details', {}),
            "recommendations": self._stability_recommendations(stability_result)
        }
    
    def _generate_calibration_analysis(self) -> Dict[str, Any]:
        """Generate calibration analysis section"""
        calibration_result = self.validation_results.get('calibration', {})
        
        return {
            "status": "PASS" if calibration_result.get('passed') else "FAIL",
            "metrics": calibration_result.get('metrics', {}),
            "details": calibration_result.get('details', {}),
            "recommendations": self._calibration_recommendations(calibration_result)
        }
    
    def _coverage_recommendations(self, result: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on coverage test"""
        recs = []
        
        coverage = result.get('metrics', {}).get('coverage_pct', 0)
        if coverage < 85:
            recs.append(f"Increase data coverage from {coverage}% to target 85%")
        
        na_rate = result.get('metrics', {}).get('avg_na_rate', 0)
        if na_rate > 25:
            recs.append(f"Reduce NA rate from {na_rate}% to below 25%")
        
        if not recs:
            recs.append("Coverage metrics meet targets - maintain current data collection")
        
        return recs
    
    def _stability_recommendations(self, result: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on stability test"""
        recs = []
        
        major_changes = result.get('metrics', {}).get('major_changes', 0)
        if major_changes > 5:
            recs.append(f"Investigate {major_changes} firms with major score changes")
        
        top10_turnover = result.get('metrics', {}).get('top_10_turnover', 0)
        if top10_turnover > 2:
            recs.append(f"High top-10 turnover ({top10_turnover}) - review ranking stability")
        
        if not recs:
            recs.append("Scores stable - no action required")
        
        return recs
    
    def _calibration_recommendations(self, result: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on calibration test"""
        recs = []
        
        conf_accuracy = result.get('metrics', {}).get('confidence_accuracy', 0)
        if conf_accuracy < 80:
            recs.append(f"Improve confidence calibration (current: {conf_accuracy}%, target: >80%)")
        
        skewness = abs(result.get('metrics', {}).get('score_skewness', 0))
        if skewness > 2:
            recs.append(f"Address score distribution skewness ({skewness:.2f})")
        
        if not recs:
            recs.append("Calibration metrics acceptable")
        
        return recs
    
    def _generate_recommendations(self) -> List[Dict[str, str]]:
        """Generate overall recommendations"""
        recommendations = []
        
        # Priority 1: Failed tests
        for test_name, result in self.validation_results.items():
            if result.get('passed') is False:
                recommendations.append({
                    "priority": "HIGH",
                    "category": test_name,
                    "recommendation": f"Address failures in {test_name} validation test",
                    "impact": "Critical for IOSCO compliance"
                })
        
        # Priority 2: High alert count
        for test_name, result in self.validation_results.items():
            alert_count = len(result.get('alerts', []))
            if alert_count > 5:
                recommendations.append({
                    "priority": "MEDIUM",
                    "category": test_name,
                    "recommendation": f"Review and address {alert_count} alerts",
                    "impact": "May affect data quality"
                })
        
        # Priority 3: General improvements
        if not recommendations:
            recommendations.append({
                "priority": "LOW",
                "category": "general",
                "recommendation": "Continue current validation practices",
                "impact": "Maintain high quality standards"
            })
        
        return recommendations
    
    def _generate_appendix(self) -> Dict[str, Any]:
        """Generate appendix with technical details"""
        return {
            "methodology": {
                "validation_framework": "6-test comprehensive validation",
                "iosco_alignment": "Articles 13, 15, 16",
                "frequency": "Daily validation, monthly reporting"
            },
            "test_descriptions": {
                "coverage": "Data completeness and sufficiency",
                "stability": "Score consistency and turnover",
                "calibration": "Confidence accuracy and bias detection",
                "ground_truth": "Alignment with known events",
                "soft_signals": "Detection of unreported issues",
                "agent_health": "Data collection agent performance"
            },
            "thresholds": {
                "coverage_pct": ">85%",
                "na_rate": "<25%",
                "score_change": "<5 points",
                "top_10_turnover": "<2 firms",
                "confidence_accuracy": ">80%"
            }
        }
    
    def save_json(self, filename: Optional[str] = None) -> Path:
        """
        Save report as JSON file
        
        Args:
            filename: Optional custom filename
            
        Returns:
            Path to saved file
        """
        if not self.report_data:
            self.generate_report()
        
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m")
            filename = f"transparency_report_{timestamp}.json"
        
        output_path = self.output_dir / filename
        
        with open(output_path, 'w') as f:
            json.dump(self.report_data, f, indent=2)
        
        logger.info(f"Report saved to {output_path}")
        return output_path
    
    def save_markdown(self, filename: Optional[str] = None) -> Path:
        """
        Save report as Markdown file
        
        Args:
            filename: Optional custom filename
            
        Returns:
            Path to saved file
        """
        if not self.report_data:
            self.generate_report()
        
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m")
            filename = f"transparency_report_{timestamp}.md"
        
        output_path = self.output_dir / filename
        
        with open(output_path, 'w') as f:
            f.write(self._format_markdown())
        
        logger.info(f"Markdown report saved to {output_path}")
        return output_path
    
    def _format_markdown(self) -> str:
        """Format report as Markdown"""
        md = []
        meta = self.report_data['report_metadata']
        summary = self.report_data['executive_summary']
        
        # Header
        md.append(f"# {meta['title']}\n")
        md.append(f"**Reporting Period:** {meta['reporting_period']}  ")
        md.append(f"**Generated:** {meta['generated_at'][:10]}  ")
        md.append(f"**Snapshot:** {meta['snapshot_id']}  ")
        md.append(f"**IOSCO Compliance:** {meta['iosco_compliance']}\n")
        
        # Executive Summary
        md.append("## Executive Summary\n")
        md.append(f"{summary['overview']}\n")
        md.append(f"**Overall Health:** {summary['overall_health']}  ")
        md.append(f"**Total Alerts:** {summary['total_alerts']}\n")
        
        test_sum = summary['test_summary']
        md.append("### Test Results")
        md.append(f"- ✅ Passed: {test_sum['passed']}")
        md.append(f"- ❌ Failed: {test_sum['failed']}")
        md.append(f"- ⏳ Not Implemented: {test_sum['not_implemented']}\n")
        
        # Validation Results
        md.append("## Validation Results\n")
        for test_name, result in self.report_data['validation_results'].items():
            status_emoji = "✅" if result['status'] == "PASS" else "❌" if result['status'] == "FAIL" else "⏳"
            md.append(f"### {status_emoji} {test_name.title()}")
            md.append(f"**Status:** {result['status']}  ")
            md.append(f"**Alerts:** {result['alert_count']}\n")
            
            if result['key_metrics']:
                md.append("**Key Metrics:**")
                for metric, value in result['key_metrics'].items():
                    md.append(f"- {metric}: {value}")
                md.append("")
        
        # Recommendations
        md.append("## Recommendations\n")
        for rec in self.report_data['recommendations']:
            md.append(f"### {rec['priority']} Priority: {rec['category']}")
            md.append(f"{rec['recommendation']}")
            md.append(f"*Impact: {rec['impact']}*\n")
        
        # Data Quality
        md.append("## Data Quality Metrics\n")
        dq = self.report_data['data_quality_metrics']
        md.append(f"- **Data Completeness:** {dq.get('data_completeness', 'N/A')}%")
        md.append(f"- **Average NA Rate:** {dq.get('avg_na_rate', 'N/A')}%")
        md.append(f"- **Average Score:** {dq.get('avg_score', 'N/A')}\n")
        
        # Appendix
        md.append("## Appendix\n")
        appendix = self.report_data['appendix']
        md.append("### Validation Thresholds")
        for threshold, value in appendix['thresholds'].items():
            md.append(f"- {threshold}: {value}")
        
        return "\n".join(md)


def generate_transparency_report(
    snapshot_data: Dict[str, Any],
    output_dir: str = "reports",
    formats: List[str] = ["json", "markdown"]
) -> Dict[str, Path]:
    """
    Convenience function to generate transparency report
    
    Args:
        snapshot_data: Complete snapshot dictionary
        output_dir: Directory to save reports
        formats: List of output formats ("json", "markdown", "pdf")
        
    Returns:
        Dictionary mapping format to output path
    """
    generator = TransparencyReportGenerator(snapshot_data, output_dir)
    generator.generate_report()
    
    output_files = {}
    
    if "json" in formats:
        output_files["json"] = generator.save_json()
    
    if "markdown" in formats:
        output_files["markdown"] = generator.save_markdown()
    
    # PDF generation would require additional library (reportlab, weasyprint, etc.)
    if "pdf" in formats:
        logger.warning("PDF generation not yet implemented - use markdown + pandoc")
    
    return output_files


# Example usage
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Load test snapshot
    snapshot_path = Path("/opt/gpti/gpti-site/data/test-snapshot.json")
    
    if snapshot_path.exists():
        with open(snapshot_path) as f:
            snapshot = json.load(f)
        
        print("Generating transparency report...")
        output_files = generate_transparency_report(
            snapshot,
            output_dir="/opt/gpti/data/reports",
            formats=["json", "markdown"]
        )
        
        print("\n=== Report Generation Complete ===")
        for fmt, path in output_files.items():
            print(f"{fmt.upper()}: {path}")
    else:
        print(f"Test snapshot not found: {snapshot_path}")
        sys.exit(1)
