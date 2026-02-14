/**
 * Enhanced RVI Agent - With Sanctions Screening Integration
 * Combined verification flow: FCA Registry + OFAC/UN Sanctions
 */

import { Agent, AgentContext } from '../../types/agent';
import { Firm } from '../../types/firm';
import { FCAClient, FCAClientMock } from '../../integrations/fca-client';
import { SSSAgent, getSSSAgent, ScreeningResult } from '../sss/sss-sanctions.agent';
import { stringSimilarity } from '../../utils/string-similarity';

export interface CombinedVerificationResult {
  status: 'CLEAR' | 'SANCTIONED' | 'SUSPENDED' | 'REVIEW_REQUIRED' | 'NOT_FOUND';
  riskScore: 'LOW' | 'MEDIUM' | 'HIGH';
  fca: {
    status: 'AUTHORIZED' | 'SUSPENDED' | 'REVOKED' | 'NOT_FOUND';
    firm?: Firm;
    confidence: number;
  };
  sanctions: {
    status: 'CLEAR' | 'SANCTIONED' | 'POTENTIAL_MATCH' | 'REVIEW_REQUIRED';
    matches: number;
    entities: string[];
  };
  riskFactors: string[];
  duration: number;
  timestamp: Date;
}

export class EnhancedRVIAgent implements Agent {
  name = 'RVI_ENHANCED';
  label = 'Enhanced Registry Verification';
  description = 'Verifies firm licenses (FCA) + screens against sanctions (OFAC/UN)';

  private fcaClient: FCAClient | FCAClientMock;
  private sssAgent: SSSAgent;
  private useMock: boolean;

  constructor(useMock: boolean = false, sssAgent?: SSSAgent) {
    this.useMock = useMock;

    // Initialize FCA client
    if (useMock) {
      this.fcaClient = new FCAClientMock();
    } else {
      const apiKey = process.env.FCA_API_KEY || '';
      if (!apiKey) {
        console.warn('FCA_API_KEY not set, using mock client');
        this.fcaClient = new FCAClientMock();
        this.useMock = true;
      } else {
        this.fcaClient = new FCAClient(apiKey);
      }
    }

    // Initialize SSS Agent
    this.sssAgent = sssAgent || getSSSAgent();
  }

  /**
   * Combined verification: FCA + Sanctions
   */
  async verify(firmName: string): Promise<CombinedVerificationResult> {
    const startTime = Date.now();

    try {
      // 1. FCA Verification
      const fcaResult = await this.verifyFCA(firmName);

      // 2. Sanctions Screening (always run, even if FCA fails)
      const sanctionsResult = await this.screenForSanctions(
        fcaResult.firm?.name || firmName,
        { threshold: 0.85, includeAliases: true }
      );

      // 3. Combine results
      const combined = this.combineResults(fcaResult, sanctionsResult);

      // 4. Calculate risk score
      combined.riskScore = this.calculateRiskScore(fcaResult, sanctionsResult);

      // 5. Identify risk factors
      combined.riskFactors = this.identifyRiskFactors(fcaResult, sanctionsResult);

      combined.duration = Date.now() - startTime;
      combined.timestamp = new Date();

      return combined;
    } catch (error: any) {
      console.error('Verification error:', error.message);
      throw error;
    }
  }

  /**
   * Verify against FCA registry
   */
  private async verifyFCA(firmName: string): Promise<{
    status: 'AUTHORIZED' | 'SUSPENDED' | 'REVOKED' | 'NOT_FOUND';
    firm?: any;
    confidence: number;
  }> {
    try {
      const results = await this.fcaClient.search({ name: firmName });

      if (results.length === 0) {
        return { status: 'NOT_FOUND', confidence: 0 };
      }

      const firm = results[0];
      const fcaStatus = firm.authorization_status === 'authorized' ? 'AUTHORIZED' : 
                        firm.authorization_status === 'suspended' ? 'SUSPENDED' : 'REVOKED';
      
      return {
        status: fcaStatus,
        firm,
        confidence: stringSimilarity(firmName.toLowerCase(), firm.name.toLowerCase()),
      };
    } catch (error) {
      console.warn('FCA verification failed:', error);
      return { status: 'NOT_FOUND', confidence: 0 };
    }
  }

  /**
   * Screen against OFAC/UN sanctions lists
   */
  private async screenForSanctions(
    firmName: string,
    options?: { threshold?: number; includeAliases?: boolean }
  ): Promise<ScreeningResult> {
    return await this.sssAgent.screen({
      name: firmName,
      threshold: options?.threshold || 0.85,
      includeAliases: options?.includeAliases !== false,
      matchTypes: ['exact', 'fuzzy', 'phonetic'],
    });
  }

  /**
   * Combine FCA and Sanctions results
   */
  private combineResults(fcaResult: any, sanctionsResult: ScreeningResult): CombinedVerificationResult {
    // Determine overall status
    let status: 'CLEAR' | 'SANCTIONED' | 'SUSPENDED' | 'REVIEW_REQUIRED' | 'NOT_FOUND';

    if (sanctionsResult.status === 'SANCTIONED') {
      status = 'SANCTIONED';
    } else if (fcaResult.status === 'SUSPENDED') {
      status = 'SUSPENDED';
    } else if (sanctionsResult.status === 'REVIEW_REQUIRED') {
      status = 'REVIEW_REQUIRED';
    } else if (fcaResult.status === 'NOT_FOUND') {
      status = 'NOT_FOUND';
    } else {
      status = 'CLEAR';
    }

    // Extract sanctions match details
    const sanctionsMatches = sanctionsResult.matches || [];
    const sanctionsEntities = sanctionsMatches.map((m) => m.entity.primary_name);

    return {
      status,
      riskScore: 'LOW', // Will be calculated separately
      fca: {
        status: fcaResult.status,
        firm: fcaResult.firm,
        confidence: fcaResult.confidence,
      },
      sanctions: {
        status: sanctionsResult.status,
        matches: sanctionsMatches.length,
        entities: sanctionsEntities,
      },
      riskFactors: [], // Will be populated by identifyRiskFactors
      duration: 0, // Will be set by caller
      timestamp: new Date(),
    };
  }

  /**
   * Calculate combined risk score
   */
  private calculateRiskScore(fcaResult: any, sanctionsResult: ScreeningResult): 'LOW' | 'MEDIUM' | 'HIGH' {
    // HIGHEST priority: Sanctioned
    if (sanctionsResult.status === 'SANCTIONED') {
      return 'HIGH';
    }

    // HIGH: Suspended or Under Review for Sanctions
    if (fcaResult.status === 'SUSPENDED' || sanctionsResult.status === 'REVIEW_REQUIRED') {
      return 'HIGH';
    }

    // MEDIUM: Potential sanctions match or low FCA confidence
    if (sanctionsResult.status === 'POTENTIAL_MATCH' || fcaResult.confidence < 0.7) {
      return 'MEDIUM';
    }

    // LOW: All clear
    return 'LOW';
  }

  /**
   * Identify specific risk factors
   */
  private identifyRiskFactors(fcaResult: any, sanctionsResult: ScreeningResult): string[] {
    const factors: string[] = [];

    // FCA risk factors
    if (fcaResult.status === 'SUSPENDED') {
      factors.push('FCA authorization suspended');
    }
    if (fcaResult.status === 'REVOKED') {
      factors.push('FCA authorization revoked');
    }
    if (fcaResult.status === 'NOT_FOUND') {
      factors.push('Not found in FCA registry');
    }
    if (fcaResult.confidence < 0.7 && fcaResult.confidence > 0) {
      factors.push(`Low FCA match confidence (${(fcaResult.confidence * 100).toFixed(0)}%)`);
    }

    // Sanctions risk factors
    if (sanctionsResult.status === 'SANCTIONED') {
      factors.push('Entity or related entity on OFAC/UN sanctions list');
      factors.push(`${sanctionsResult.matches.length} sanctions match(es)`);
    }
    if (sanctionsResult.status === 'REVIEW_REQUIRED') {
      factors.push('Potential match with OFAC/UN sanctions list - requires manual review');
    }
    if (sanctionsResult.status === 'POTENTIAL_MATCH') {
      factors.push('Possible phonetic match with sanctioned entity');
    }

    return factors;
  }

  /**
   * Batch verification
   */
  async verifyBatch(firmNames: string[]): Promise<CombinedVerificationResult[]> {
    const results: CombinedVerificationResult[] = [];

    for (const firmName of firmNames) {
      try {
        const result = await this.verify(firmName);
        results.push(result);
      } catch (error: any) {
        console.error(`Failed to verify ${firmName}:`, error.message);
        results.push({
          status: 'NOT_FOUND',
          riskScore: 'HIGH',
          fca: {
            status: 'NOT_FOUND',
            confidence: 0,
          },
          sanctions: {
            status: 'CLEAR',
            matches: 0,
            entities: [],
          },
          riskFactors: [`Verification failed: ${error.message}`],
          duration: 0,
          timestamp: new Date(),
        });
      }
    }

    return results;
  }

  /**
   * Agent interface implementation
   */
  async execute(context: AgentContext): Promise<any> {
    const firmName = (context as any).firmName || (context as any).name;
    if (!firmName) {
      throw new Error('firmName or name required in context');
    }

    return this.verify(firmName);
  }

  /**
   * Get agent metadata
   */
  getMetadata(): any {
    return {
      name: this.name,
      label: this.label,
      description: this.description,
      version: '2.0.0',
      features: [
        'FCA Registry Verification',
        'OFAC Sanctions Screening',
        'UN Consolidated Sanctions Screening',
        'Combined Risk Scoring',
        'Batch Processing',
      ],
      dataSource: this.useMock ? 'MOCK' : 'FCA_API + OFAC/UN',
    };
  }
}

// Singleton instance
let enhancedRVIInstance: EnhancedRVIAgent | null = null;

export function getEnhancedRVIAgent(useMock: boolean = false): EnhancedRVIAgent {
  if (!enhancedRVIInstance) {
    enhancedRVIInstance = new EnhancedRVIAgent(useMock);
  }
  return enhancedRVIInstance;
}

export default EnhancedRVIAgent;
