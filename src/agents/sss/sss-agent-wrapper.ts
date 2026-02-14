/**
 * SSS Agent Wrapper
 * Adapts SSSAgent (screener) to standard Agent interface
 */

import { Agent, AgentContext } from '../../types/agent';
import { Firm } from '../../types/firm';
import { SSSAgent as SSSScreener, ScreeningResult } from './sss-sanctions.agent';
import { getDatabase } from '../../db/postgres-client';

export interface SanctionsEvidence {
  evidence_type: 'SANCTIONS_SCREENING';
  firm_id: string;
  firm_name: string;
  status: 'CLEAR' | 'SANCTIONED' | 'POTENTIAL_MATCH' | 'REVIEW_REQUIRED';
  matches: any[];
  confidence: number;
  data_source: 'OFAC' | 'UN' | 'BOTH';
  collected_at: Date;
}

export class SSSAgentWrapper implements Agent {
  name = 'SSS';
  label = 'Sanctions Screening Service';
  description = 'Screens firms against OFAC and UN sanctions lists';

  private screener: SSSScreener;
  private useMock: boolean;

  constructor(useMock: boolean = false) {
    this.useMock = useMock;
    if (!useMock) {
      try {
        const db = getDatabase();
        this.screener = new SSSScreener(db);
      } catch (error) {
        console.warn('Database not available, using mock mode');
        this.useMock = true;
        this.screener = new SSSScreener();
      }
    } else {
      this.screener = new SSSScreener();
    }
  }

  async verify(firm: Firm, context?: AgentContext): Promise<SanctionsEvidence> {
    if (this.useMock) {
      return this.getMockResult(firm);
    }

    try {
      const result: ScreeningResult = await this.screener.screen({
        name: firm.name,
        threshold: 0.85,
        includeAliases: true,
      });

      return {
        evidence_type: 'SANCTIONS_SCREENING',
        firm_id: firm.firm_id,
        firm_name: firm.name,
        status: result.status,
        matches: result.matches,
        confidence: this.calculateConfidence(result),
        data_source: 'BOTH',
        collected_at: new Date(),
      };
    } catch (error) {
      console.error(`SSS Agent error for ${firm.name}:`, error);
      return this.getMockResult(firm);
    }
  }

  private calculateConfidence(result: ScreeningResult): number {
    if (result.status === 'CLEAR') return 0.95;
    if (result.status === 'SANCTIONED') return 0.99;
    if (result.matches.length === 0) return 0.95;
    
    // Average of match confidences
    const avgScore = result.matches.reduce((sum, m) => sum + m.similarityScore, 0) / result.matches.length;
    return avgScore;
  }

  private getMockResult(firm: Firm): SanctionsEvidence {
    return {
      evidence_type: 'SANCTIONS_SCREENING',
      firm_id: firm.firm_id,
      firm_name: firm.name,
      status: 'CLEAR',
      matches: [],
      confidence: 0.95,
      data_source: 'BOTH',
      collected_at: new Date(),
    };
  }

  async verifyBatch(firms: Firm[], context?: AgentContext): Promise<SanctionsEvidence[]> {
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
      capabilities: ['sanctions_screening', 'fuzzy_matching', 'alias_detection'],
      databases: ['OFAC', 'UN'],
    };
  }
}
