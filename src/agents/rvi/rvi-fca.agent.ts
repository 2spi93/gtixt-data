/**
 * RVI Agent - Registry Verification Integration with FCA API
 * Handles license verification for UK regulated firms
 */

import { Agent, AgentContext } from '../../types/agent';
import { Firm } from '../../types/firm';
import { FCAClient, FCAClientMock, FCAPIError } from '../../integrations/fca-client';
import { stringSimilarity } from '../../utils/string-similarity';

export interface LicenseVerificationEvidence {
  evidence_type: 'LICENSE_VERIFICATION';
  status: 'CONFIRMED' | 'REJECTED' | 'SUSPENDED';
  firm_id: string;
  firm_name: string;
  fca_firm_id?: string;
  authorization_date?: Date;
  permissions: string[];
  enforcement_actions: number;
  confidence: number;
  data_source: 'FCA_REGISTRY' | 'MOCK';
  error?: string;
  collected_at: Date;
}

export class RVIAgent implements Agent {
  name = 'RVI';
  label = 'Registry Verification';
  description = 'Verifies firm licenses against FCA registry';

  private fcaClient: FCAClient | FCAClientMock;
  private useMock: boolean;

  constructor(useMock: boolean = false) {
    this.useMock = useMock;
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
  }

  /**
   * Verify license for a firm
   */
  async verify(firm: Firm, context?: AgentContext): Promise<LicenseVerificationEvidence> {
    const startTime = Date.now();

    try {
      // 1. Search FCA registry by firm name
      const searchResults = await this.fcaClient.search({
        name: firm.name,
        country: firm.country,
        limit: 5,
      });

      if (searchResults.length === 0) {
        return {
          evidence_type: 'LICENSE_VERIFICATION',
          status: 'REJECTED',
          firm_id: firm.firm_id,
          firm_name: firm.name,
          permissions: [],
          enforcement_actions: 0,
          confidence: 0,
          data_source: this.useMock ? 'MOCK' : 'FCA_REGISTRY',
          error: 'No FCA registry matches found',
          collected_at: new Date(),
        };
      }

      //  2. Find best match by name similarity
      const matches = searchResults.map((result: any) => {
        const sim = stringSimilarity(firm.name, result.name);
        return {
          firm: result,
          similarity: sim,
        };
      });

      const bestMatch = matches.sort((a: any, b: any) => b.similarity - a.similarity)[0];

      if (!bestMatch || bestMatch.similarity < 0.6) {
        return {
          evidence_type: 'LICENSE_VERIFICATION',
          status: 'REJECTED',
          firm_id: firm.firm_id,
          firm_name: firm.name,
          permissions: [],
          enforcement_actions: 0,
          confidence: bestMatch?.similarity || 0,
          data_source: this.useMock ? 'MOCK' : 'FCA_REGISTRY',
          error: `Low confidence match (${(bestMatch?.similarity || 0).toFixed(2)})`,
          collected_at: new Date(),
        };
      }

      // 3. Get detailed firm info
      const firmDetails = await this.fcaClient.getFirmDetails(bestMatch.firm.firm_id);

      // 4. Check authorization status
      const status =
        firmDetails.authorization_status === 'authorized'
          ? 'CONFIRMED'
          : firmDetails.authorization_status === 'suspended'
          ? 'SUSPENDED'
          : 'REJECTED';

      // 5. Count active enforcement actions
      const activeEnforcement = firmDetails.enforcement_actions.filter(
        (a: any) => a.status === 'active'
      ).length;

      // 6. Extract permissions
      const permissions = firmDetails.permissions
        .filter((p: any) => p.authorized)
        .map((p: any) => p.activity);

      // 7. Return evidence
      const evidence: LicenseVerificationEvidence = {
        evidence_type: 'LICENSE_VERIFICATION',
        status,
        firm_id: firm.firm_id,
        firm_name: firm.name,
        fca_firm_id: firmDetails.firm_id,
        authorization_date: firmDetails.authorization_date,
        permissions,
        enforcement_actions: activeEnforcement,
        confidence: bestMatch.similarity,
        data_source: this.useMock ? 'MOCK' : 'FCA_REGISTRY',
        collected_at: new Date(),
      };

      const elapsed = Date.now() - startTime;
      console.log(`[RVI] Verified ${firm.name} in ${elapsed}ms - Status: ${status}`);

      return evidence;
    } catch (error) {
      console.error(`[RVI] Error verifying ${firm.name}:`, error);

      const errorMessage =
        error instanceof FCAPIError ? (error as FCAPIError).message : String(error);

      return {
        evidence_type: 'LICENSE_VERIFICATION',
        status: 'REJECTED',
        firm_id: firm.firm_id,
        firm_name: firm.name,
        permissions: [],
        enforcement_actions: 0,
        confidence: 0,
        data_source: this.useMock ? 'MOCK' : 'FCA_REGISTRY',
        error: errorMessage,
        collected_at: new Date(),
      };
    }
  }

  /**
   * Batch verify multiple firms
   */
  async verifyBatch(
    firms: Firm[],
    context?: AgentContext
  ): Promise<LicenseVerificationEvidence[]> {
    console.log(`[RVI] Starting batch verification for ${firms.length} firms`);

    const startTime = Date.now();
    const results = await Promise.all(firms.map((firm) => this.verify(firm, context)));
    const elapsed = Date.now() - startTime;

    const confirmed = results.filter((r) => r.status === 'CONFIRMED').length;
    const rejected = results.filter((r) => r.status === 'REJECTED').length;
    const suspended = results.filter((r) => r.status === 'SUSPENDED').length;

    console.log(`[RVI] Batch complete in ${elapsed}ms:`);
    console.log(`  ✅ Confirmed: ${confirmed}`);
    console.log(`  ❌ Rejected: ${rejected}`);
    console.log(`  ⚠️  Suspended: ${suspended}`);

    return results;
  }

  /**
   * Get agent metadata
   */
  getMetadata() {
    return {
      name: this.name,
      label: this.label,
      description: this.description,
      evidenceType: 'LICENSE_VERIFICATION',
      dataSource: 'FCA_REGISTRY',
      status: 'operational',
      enabled: true,
    };
  }
}

export default RVIAgent;
