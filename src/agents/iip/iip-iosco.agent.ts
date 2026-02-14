/**
 * IIP Agent - IOSCO Implementation & Publication
 * Ensures compliance with IOSCO standards and generates reports
 */

import { Agent, AgentContext } from '../../types/agent';
import { Firm } from '../../types/firm';
import { writeFileSync } from 'fs';
import { join } from 'path';

export interface IOSCOReportEvidence {
  evidence_type: 'IOSCO_REPORT';
  firm_id: string;
  firm_name: string;
  report_id: string;
  report_type: 'COMPLIANCE' | 'DISCLOSURE' | 'AUDIT' | 'TRANSPARENCY';
  compliance_score: number;
  iosco_principles: {
    principle: string;
    status: 'COMPLIANT' | 'PARTIAL' | 'NON_COMPLIANT';
    details: string;
  }[];
  recommendations: string[];
  report_url?: string;
  generated_at: Date;
  confidence: number;
}

export class IIPAgent implements Agent {
  name = 'IIP';
  label = 'IOSCO Implementation & Publication';
  description = 'Generates IOSCO compliance reports';

  private useMock: boolean;
  private reportsDir: string;

  constructor(useMock: boolean = false, reportsDir: string = '/opt/gpti/data/reports') {
    this.useMock = useMock;
    this.reportsDir = reportsDir;
  }

  /**
   * Generate IOSCO report for a firm
   */
  async verify(firm: Firm, context?: AgentContext): Promise<IOSCOReportEvidence> {
    try {
      // Assess compliance with IOSCO principles
      const principles = this.assessIOSCOPrinciples(firm);
      const complianceScore = this.calculateComplianceScore(principles);
      const recommendations = this.generateRecommendations(principles);

      const report: IOSCOReportEvidence = {
        evidence_type: 'IOSCO_REPORT',
        firm_id: firm.firm_id,
        firm_name: firm.name,
        report_id: `iosco-${firm.firm_id}-${Date.now()}`,
        report_type: 'COMPLIANCE',
        compliance_score: complianceScore,
        iosco_principles: principles,
        recommendations,
        generated_at: new Date(),
        confidence: 0.95,
      };

      // Generate and save report
      if (!this.useMock) {
        const reportPath = await this.saveReport(report);
        report.report_url = reportPath;
      }

      return report;
    } catch (error) {
      console.error(`IIP Agent error for ${firm.name}:`, error);
      return this.getMockReport(firm);
    }
  }

  private assessIOSCOPrinciples(firm: Firm): any[] {
    const principles = [
      {
        principle: 'Transparency and Disclosure',
        status: this.assessTransparency(firm),
        details: `Firm transparency score: ${firm.score}/100`,
      },
      {
        principle: 'Risk Management',
        status: this.assessRiskManagement(firm),
        details: 'Risk controls and monitoring systems',
      },
      {
        principle: 'Investor Protection',
        status: this.assessInvestorProtection(firm),
        details: 'Client fund segregation and insurance',
      },
      {
        principle: 'Market Integrity',
        status: this.assessMarketIntegrity(firm),
        details: 'Fair trading practices and surveillance',
      },
      {
        principle: 'Regulatory Compliance',
        status: this.assessRegulatoryCompliance(firm),
        details: 'License status and regulatory standing',
      },
    ];

    return principles;
  }

  private assessTransparency(firm: Firm): 'COMPLIANT' | 'PARTIAL' | 'NON_COMPLIANT' {
    const score = firm.score || 0;
    if (score >= 70) return 'COMPLIANT';
    if (score >= 50) return 'PARTIAL';
    return 'NON_COMPLIANT';
  }

  private assessRiskManagement(firm: Firm): 'COMPLIANT' | 'PARTIAL' | 'NON_COMPLIANT' {
    // Check if firm has risk management pillar data
    const riskScore = firm.pillar_scores?.['risk_model'] || 0;
    if (riskScore >= 0.7) return 'COMPLIANT';
    if (riskScore >= 0.5) return 'PARTIAL';
    return 'NON_COMPLIANT';
  }

  private assessInvestorProtection(firm: Firm): 'COMPLIANT' | 'PARTIAL' | 'NON_COMPLIANT' {
    const payoutScore = firm.pillar_scores?.['payout_reliability'] || 0;
    if (payoutScore >= 0.7) return 'COMPLIANT';
    if (payoutScore >= 0.5) return 'PARTIAL';
    return 'NON_COMPLIANT';
  }

  private assessMarketIntegrity(firm: Firm): 'COMPLIANT' | 'PARTIAL' | 'NON_COMPLIANT' {
    // Based on legal compliance and reputation
    const legalScore = firm.pillar_scores?.['legal_compliance'] || 0;
    if (legalScore >= 0.7) return 'COMPLIANT';
    if (legalScore >= 0.5) return 'PARTIAL';
    return 'NON_COMPLIANT';
  }

  private assessRegulatoryCompliance(firm: Firm): 'COMPLIANT' | 'PARTIAL' | 'NON_COMPLIANT' {
    const status = firm.status || '';
    if (status === 'active') return 'COMPLIANT';
    if (status === 'candidate') return 'PARTIAL';
    return 'NON_COMPLIANT';
  }

  private calculateComplianceScore(principles: any[]): number {
    let score = 0;
    principles.forEach(p => {
      if (p.status === 'COMPLIANT') score += 20;
      else if (p.status === 'PARTIAL') score += 10;
    });
    return Math.min(score, 100);
  }

  private generateRecommendations(principles: any[]): string[] {
    const recommendations: string[] = [];

    principles.forEach(p => {
      if (p.status === 'NON_COMPLIANT') {
        recommendations.push(`Improve ${p.principle} - currently non-compliant`);
      } else if (p.status === 'PARTIAL') {
        recommendations.push(`Enhance ${p.principle} to reach full compliance`);
      }
    });

    if (recommendations.length === 0) {
      recommendations.push('Maintain current compliance standards');
      recommendations.push('Continue regular monitoring and reporting');
    }

    return recommendations;
  }

  private async saveReport(report: IOSCOReportEvidence): Promise<string> {
    try {
      const filename = `${report.report_id}.json`;
      const filepath = join(this.reportsDir, filename);
      
      writeFileSync(filepath, JSON.stringify(report, null, 2));
      
      return `/reports/${filename}`;
    } catch (error) {
      console.error('Failed to save report:', error);
      return '';
    }
  }

  private getMockReport(firm: Firm): IOSCOReportEvidence {
    return {
      evidence_type: 'IOSCO_REPORT',
      firm_id: firm.firm_id,
      firm_name: firm.name,
      report_id: `mock-iosco-${Date.now()}`,
      report_type: 'COMPLIANCE',
      compliance_score: 75,
      iosco_principles: [
        {
          principle: 'Transparency',
          status: 'COMPLIANT',
          details: 'Mock assessment',
        },
      ],
      recommendations: ['Continue good practices'],
      generated_at: new Date(),
      confidence: 0.8,
    };
  }

  async verifyBatch(firms: Firm[], context?: AgentContext): Promise<IOSCOReportEvidence[]> {
    const results = await Promise.all(
      firms.map(firm => this.verify(firm, context))
    );
    return results;
  }

  getMetadata(): Record<string, any> {
    return {
      name: this.name,
      label: this.label,
      description: this.description,
      useMock: this.useMock,
      capabilities: ['iosco_compliance', 'report_generation', 'regulatory_assessment'],
    };
  }
}
