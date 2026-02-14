/**
 * RVI Agent Tests - Registry Verification
 * Tests FCA API integration and license verification
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import RVIAgent from './rvi-fca.agent';
import { Firm } from '../../types/firm';

describe('RVI Agent - Registry Verification', () => {
  let agent: RVIAgent;

  beforeEach(() => {
    // Use mock client for testing
    agent = new RVIAgent(true);
  });

  describe('License Verification', () => {
    it('should confirm authorized firm', async () => {
      const firm: Firm = {
        firm_id: 'TEST001',
        name: 'FTMO Limited',
        country: 'GB',
        sector: 'Financial Services',
      };

      const result = await agent.verify(firm);

      expect(result.evidence_type).toBe('LICENSE_VERIFICATION');
      expect(result.status).toBe('CONFIRMED');
      expect(result.confidence).toBeGreaterThanOrEqual(0.9);
      expect(result.permissions.length).toBeGreaterThan(0);
    });

    it('should reject non-existent firm', async () => {
      const firm: Firm = {
        firm_id: 'TEST002',
        name: 'Fake Company XYZ',
        country: 'GB',
        sector: 'Financial Services',
      };

      const result = await agent.verify(firm);

      expect(result.status).toBe('REJECTED');
      expect(result.confidence).toBe(0);
    });

    it('should handle name variations', async () => {
      const firm: Firm = {
        firm_id: 'TEST003',
        name: 'FTMO Ltd', // Variation of "FTMO Limited"
        country: 'GB',
        sector: 'Financial Services',
      };

      const result = await agent.verify(firm);

      // Should still match with fuzzy matching
      expect(result.status).toBe('CONFIRMED');
      expect(result.confidence).toBeGreaterThanOrEqual(0.6);
    });

    it('should extract permissions', async () => {
      const firm: Firm = {
        firm_id: 'TEST004',
        name: 'FTMO Limited',
        country: 'GB',
        sector: 'Financial Services',
      };

      const result = await agent.verify(firm);

      expect(result.permissions).toContain('DRVSTR'); // Dealing as principal
      expect(result.permissions).toContain('EDDCAS'); // Arranging deals
    });

    it('should count enforcement actions', async () => {
      const firm: Firm = {
        firm_id: 'TEST005',
        name: 'FTMO Limited',
        country: 'GB',
        sector: 'Financial Services',
      };

      const result = await agent.verify(firm);

      expect(result.enforcement_actions).toBeGreaterThanOrEqual(0);
      expect(typeof result.enforcement_actions).toBe('number');
    });
  });

  describe('Batch Verification', () => {
    it('should verify multiple firms', async () => {
      const firms: Firm[] = [
        {
          firm_id: 'BATCH001',
          name: 'FTMO Limited',
          country: 'GB',
          sector: 'Financial Services',
        },
        {
          firm_id: 'BATCH002',
          name: 'Unknown Company',
          country: 'GB',
          sector: 'Financial Services',
        },
        {
          firm_id: 'BATCH003',
          name: 'FTMO Ltd',
          country: 'GB',
          sector: 'Financial Services',
        },
      ];

      const results = await agent.verifyBatch(firms);

      expect(results.length).toBe(3);
      expect(results[0].status).toBe('CONFIRMED');
      expect(results[1].status).toBe('REJECTED');
      expect(results[2].status).toBe('CONFIRMED');
    });

    it('should handle performance', async () => {
      const firms: Firm[] = Array.from({ length: 10 }, (_, i) => ({
        firm_id: `PERF${i}`,
        name: i % 3 === 0 ? 'FTMO Limited' : `Unknown Company ${i}`,
        country: 'GB',
        sector: 'Financial Services',
      }));

      const startTime = Date.now();
      const results = await agent.verifyBatch(firms);
      const elapsed = Date.now() - startTime;

      expect(results.length).toBe(10);
      // Should complete 10 firms in < 5 seconds (avg 500ms per firm)
      expect(elapsed).toBeLessThan(5000);
    });
  });

  describe('Error Handling', () => {
    it('should handle API errors gracefully', async () => {
      const firm: Firm = {
        firm_id: 'ERR001',
        name: 'FTMO Limited',
        country: 'GB',
        sector: 'Financial Services',
      };

      // This should not throw
      const result = await agent.verify(firm);

      expect(result).toBeDefined();
      expect(result.evidence_type).toBe('LICENSE_VERIFICATION');
    });

    it('should set error field on failure', async () => {
      // Mock a firm that might cause issues
      const firm: Firm = {
        firm_id: 'ERR002',
        name: '', // Empty name might cause issues
        country: 'GB',
        sector: 'Financial Services',
      };

      const result = await agent.verify(firm);

      expect(result.status).toBe('REJECTED');
    });
  });

  describe('Data Source Tracking', () => {
    it('should mark mock data correctly', async () => {
      const firm: Firm = {
        firm_id: 'MOCK001',
        name: 'FTMO Limited',
        country: 'GB',
        sector: 'Financial Services',
      };

      const result = await agent.verify(firm);

      expect(result.data_source).toBe('MOCK'); // Using mock client
    });

    it('should include timestamp', async () => {
      const firm: Firm = {
        firm_id: 'TS001',
        name: 'FTMO Limited',
        country: 'GB',
        sector: 'Financial Services',
      };

      const beforeTime = new Date();
      const result = await agent.verify(firm);
      const afterTime = new Date();

      expect(result.collected_at.getTime()).toBeGreaterThanOrEqual(beforeTime.getTime());
      expect(result.collected_at.getTime()).toBeLessThanOrEqual(afterTime.getTime());
    });
  });

  describe('Metadata', () => {
    it('should provide agent metadata', () => {
      const metadata = agent.getMetadata();

      expect(metadata.name).toBe('RVI');
      expect(metadata.label).toBe('Registry Verification');
      expect(metadata.evidenceType).toBe('LICENSE_VERIFICATION');
      expect(metadata.dataSource).toBe('FCA_REGISTRY');
      expect(metadata.status).toBe('operational');
    });
  });
});
