/**
 * SSS Agent Tests
 * Test suite for Sanctions Screening Service
 */

import { describe, test, expect, beforeAll } from '@jest/globals';
import { SSSAgent, ScreeningRequest, ScreeningResult } from './sss-sanctions.agent';
import { DatabaseClient, SanctionsEntity } from '../../db/postgres-client';

// Mock database client
class MockDatabaseClient {
  private mockEntities: SanctionsEntity[] = [];

  constructor() {
    // Setup mock data
    this.mockEntities = [
      {
        id: 1,
        list_id: 1,
        entity_id: 'OFAC-001',
        entity_type: 'individual',
        primary_name: 'John Smith',
        name_variants: ['Jon Smith', 'J. Smith'],
        name_normalized: 'john smith',
        program: 'UKRAINE-EO13662',
        sanctions_list: 'SDN',
        nationality: ['US'],
        added_date: new Date('2022-01-01'),
        raw_data: {},
      },
      {
        id: 2,
        list_id: 1,
        entity_id: 'OFAC-002',
        entity_type: 'entity',
        primary_name: 'Acme Trading Corp',
        name_variants: ['ACME Trading Corporation', 'Acme Corp'],
        name_normalized: 'acme trading corp',
        program: 'IRAN',
        sanctions_list: 'SDN',
        nationality: ['IR'],
        added_date: new Date('2021-06-15'),
        raw_data: {},
      },
      {
        id: 3,
        list_id: 2,
        entity_id: 'UN-001',
        entity_type: 'individual',
        primary_name: 'Mohammed Hassan',
        name_variants: ['Muhammad Hassan', 'M. Hassan'],
        name_normalized: 'mohammed hassan',
        program: 'AL-QAIDA',
        sanctions_list: 'UN_CONSOLIDATED',
        nationality: ['YE'],
        added_date: new Date('2020-03-10'),
        raw_data: {},
      },
    ];
  }

  async searchExact(name: string): Promise<SanctionsEntity[]> {
    const normalized = name.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim();
    return this.mockEntities.filter((e) => e.name_normalized === normalized);
  }

  async searchFuzzy(name: string, threshold: number): Promise<SanctionsEntity[]> {
    // Simple mock implementation
    const normalized = name.toLowerCase();
    return this.mockEntities.filter((e) => 
      e.name_normalized.includes(normalized.split(' ')[0])
    );
  }

  async query<T>(sql: string, params?: any[]): Promise<{ rows: T[] }> {
    // Mock query for alias search
    if (sql.includes('name_variants')) {
      const searchName = params?.[0] || '';
      const entities = this.mockEntities.filter((e) =>
        e.name_variants.some((v) => v.toLowerCase() === searchName.toLowerCase())
      );
      return { rows: entities as T[] };
    }

    // Mock query for phonetic
    if (sql.includes('ILIKE')) {
      return { rows: this.mockEntities as T[] };
    }

    return { rows: [] };
  }

  async recordMatch(match: any): Promise<number> {
    return 1;
  }

  async getStatistics(): Promise<any> {
    return [{ list_name: 'OFAC_SDN', total_entities: 3 }];
  }
}

describe('SSS Agent - Sanctions Screening Service', () => {
  let agent: SSSAgent;
  let mockDb: MockDatabaseClient;

  beforeAll(() => {
    mockDb = new MockDatabaseClient();
    agent = new SSSAgent(mockDb as unknown as DatabaseClient);
  });

  describe('Exact Matching', () => {
    test('should find exact match by primary name', async () => {
      const request: ScreeningRequest = {
        name: 'John Smith',
        matchTypes: ['exact'],
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('SANCTIONED');
      expect(result.matches.length).toBeGreaterThan(0);
      expect(result.matches[0].matchType).toBe('exact');
      expect(result.matches[0].entity.primary_name).toBe('John Smith');
      expect(result.matches[0].similarityScore).toBe(1.0);
      expect(result.matches[0].confidence).toBe('high');
    });

    test('should find exact match case-insensitive', async () => {
      const request: ScreeningRequest = {
        name: 'JOHN SMITH',
        matchTypes: ['exact'],
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('SANCTIONED');
      expect(result.matches.length).toBeGreaterThan(0);
    });

    test('should return CLEAR for no match', async () => {
      const request: ScreeningRequest = {
        name: 'Jane Doe',
        matchTypes: ['exact'],
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('CLEAR');
      expect(result.matches.length).toBe(0);
    });
  });

  describe('Alias Matching', () => {
    test('should find match by alias', async () => {
      const request: ScreeningRequest = {
        name: 'Jon Smith',
        includeAliases: true,
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('SANCTIONED');
      expect(result.matches.length).toBeGreaterThan(0);
      expect(['alias', 'exact']).toContain(result.matches[0].matchType);
    });

    test('should find entity by alternative name', async () => {
      const request: ScreeningRequest = {
        name: 'ACME Trading Corporation',
        includeAliases: true,
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('SANCTIONED');
      expect(result.matches.some((m) => m.entity.primary_name === 'Acme Trading Corp')).toBe(true);
    });
  });

  describe('Fuzzy Matching', () => {
    test('should find fuzzy match with typo', async () => {
      const request: ScreeningRequest = {
        name: 'John Smyth', // Typo in surname
        threshold: 0.80,
        matchTypes: ['fuzzy'],
      };

      const result = await agent.screen(request);

      // Should find John Smith with medium/low confidence
      expect(['POTENTIAL_MATCH', 'REVIEW_REQUIRED']).toContain(result.status);
    });

    test('should respect threshold setting', async () => {
      const request: ScreeningRequest = {
        name: 'John Doe', // Different surname
        threshold: 0.95, // Very high threshold
        matchTypes: ['fuzzy'],
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('CLEAR');
    });

    test('should find partial company name match', async () => {
      const request: ScreeningRequest = {
        name: 'Acme Trading',
        threshold: 0.75,
        matchTypes: ['fuzzy'],
      };

      const result = await agent.screen(request);

      expect(result.matches.length).toBeGreaterThan(0);
    });
  });

  describe('Phonetic Matching', () => {
    test('should find phonetically similar names', async () => {
      const request: ScreeningRequest = {
        name: 'Muhammad Hassan', // Phonetically similar to Mohammed
        matchTypes: ['phonetic'],
      };

      const result = await agent.screen(request);

      // Should find Mohammed Hassan
      expect(result.matches.length).toBeGreaterThan(0);
    });
  });

  describe('Batch Screening', () => {
    test('should screen multiple names', async () => {
      const requests: ScreeningRequest[] = [
        { name: 'John Smith' },
        { name: 'Jane Doe' },
        { name: 'Acme Trading Corp' },
      ];

      const batchResult = await agent.screenBatch(requests);

      expect(batchResult.results.length).toBe(3);
      expect(batchResult.results[0].status).toBe('SANCTIONED'); // John Smith
      expect(batchResult.results[1].status).toBe('CLEAR'); // Jane Doe
      expect(batchResult.results[2].status).toBe('SANCTIONED'); // Acme
    });

    test('should calculate batch statistics', async () => {
      const requests: ScreeningRequest[] = [
        { name: 'Test 1' },
        { name: 'Test 2' },
      ];

      const batchResult = await agent.screenBatch(requests);

      expect(batchResult.totalDuration).toBeGreaterThan(0);
      expect(batchResult.averageDuration).toBe(batchResult.totalDuration / 2);
    });
  });

  describe('Confidence Levels', () => {
    test('should assign high confidence for exact match', async () => {
      const request: ScreeningRequest = {
        name: 'John Smith',
      };

      const result = await agent.screen(request);

      expect(result.matches[0]?.confidence).toBe('high');
    });

    test('should assign medium confidence for good fuzzy match', async () => {
      const request: ScreeningRequest = {
        name: 'John Smyth',
        threshold: 0.85,
      };

      const result = await agent.screen(request);

      if (result.matches.length > 0) {
        expect(['medium', 'low']).toContain(result.matches[0].confidence);
      }
    });
  });

  describe('Status Determination', () => {
    test('should return SANCTIONED for high confidence match', async () => {
      const request: ScreeningRequest = {
        name: 'John Smith',
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('SANCTIONED');
    });

    test('should return CLEAR when no matches', async () => {
      const request: ScreeningRequest = {
        name: 'Random Name XYZ',
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('CLEAR');
    });
  });

  describe('Performance', () => {
    test('should screen within 100ms for exact match', async () => {
      const request: ScreeningRequest = {
        name: 'John Smith',
        matchTypes: ['exact'],
      };

      const result = await agent.screen(request);

      expect(result.duration).toBeLessThan(100);
    });

    test('should screen batch of 10 in reasonable time', async () => {
      const requests: ScreeningRequest[] = Array.from({ length: 10 }, (_, i) => ({
        name: `Test Name ${i}`,
      }));

      const startTime = Date.now();
      const batchResult = await agent.screenBatch(requests);
      const duration = Date.now() - startTime;

      expect(duration).toBeLessThan(1000); // < 1 second for 10 names
      expect(batchResult.averageDuration).toBeLessThan(100);
    });
  });

  describe('Metadata', () => {
    test('should include screening metadata', async () => {
      const request: ScreeningRequest = {
        name: 'John Smith',
      };

      const result = await agent.screen(request);

      expect(result.metadata).toBeDefined();
      expect(result.metadata.total_entities_checked).toBeGreaterThan(0);
    });

    test('should count match types correctly', async () => {
      const request: ScreeningRequest = {
        name: 'John Smith',
        matchTypes: ['exact', 'fuzzy'],
      };

      const result = await agent.screen(request);

      const totalMatches =
        result.metadata.exact_matches +
        result.metadata.fuzzy_matches +
        result.metadata.phonetic_matches +
        result.metadata.alias_matches;

      expect(totalMatches).toBe(result.matches.length);
    });
  });

  describe('Edge Cases', () => {
    test('should handle empty name', async () => {
      const request: ScreeningRequest = {
        name: '',
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('CLEAR');
    });

    test('should handle special characters', async () => {
      const request: ScreeningRequest = {
        name: 'John@Smith#123',
      };

      const result = await agent.screen(request);

      // Should normalize and still match
      expect(result.status).not.toBe('CLEAR');
    });

    test('should handle very long names', async () => {
      const request: ScreeningRequest = {
        name: 'A'.repeat(500),
      };

      const result = await agent.screen(request);

      expect(result.status).toBe('CLEAR');
    });

    test('should handle Unicode characters', async () => {
      const request: ScreeningRequest = {
        name: 'محمد حسن', // Arabic name
      };

      const result = await agent.screen(request);

      // Should not crash
      expect(result).toBeDefined();
    });
  });

  describe('Statistics', () => {
    test('should get screening statistics', async () => {
      const stats = await agent.getStatistics();

      expect(stats).toBeDefined();
      expect(stats.sanctions_lists).toBeDefined();
    });

    test('should get recent screenings', async () => {
      // Perform a screening first
      await agent.screen({ name: 'John Smith' });

      const recent = await agent.getRecentScreenings(10);

      expect(Array.isArray(recent)).toBe(true);
    });
  });

  describe('Entity Types', () => {
    test('should filter by entity type (individual)', async () => {
      const request: ScreeningRequest = {
        name: 'John Smith',
        entityType: 'individual',
      };

      const result = await agent.screen(request);

      if (result.matches.length > 0) {
        expect(result.matches[0].entity.entity_type).toBe('individual');
      }
    });

    test('should filter by entity type (entity)', async () => {
      const request: ScreeningRequest = {
        name: 'Acme Trading Corp',
        entityType: 'entity',
      };

      const result = await agent.screen(request);

      if (result.matches.length > 0) {
        expect(result.matches[0].entity.entity_type).toBe('entity');
      }
    });
  });

  describe('Match Sorting', () => {
    test('should sort matches by confidence', async () => {
      const request: ScreeningRequest = {
        name: 'John',
        threshold: 0.5, // Low threshold to get multiple matches
      };

      const result = await agent.screen(request);

      if (result.matches.length > 1) {
        // Check that matches are sorted (high > medium > low)
        const confidenceOrder = { high: 3, medium: 2, low: 1 };
        for (let i = 0; i < result.matches.length - 1; i++) {
          const current = confidenceOrder[result.matches[i].confidence];
          const next = confidenceOrder[result.matches[i + 1].confidence];
          expect(current).toBeGreaterThanOrEqual(next);
        }
      }
    });
  });
});

describe('SSS Agent Integration', () => {
  test('should work with multiple match types', async () => {
    const mockDb = new MockDatabaseClient();
    const agent = new SSSAgent(mockDb as unknown as DatabaseClient);

    const request: ScreeningRequest = {
      name: 'John Smith',
      matchTypes: ['exact', 'fuzzy', 'phonetic'],
    };

    const result = await agent.screen(request);

    expect(result.matches.length).toBeGreaterThan(0);
    expect(result.metadata.total_entities_checked).toBeGreaterThan(0);
  });

  test('should provide detailed match reasons', async () => {
    const mockDb = new MockDatabaseClient();
    const agent = new SSSAgent(mockDb as unknown as DatabaseClient);

    const request: ScreeningRequest = {
      name: 'John Smith',
    };

    const result = await agent.screen(request);

    if (result.matches.length > 0) {
      expect(result.matches[0].reason).toBeDefined();
      expect(typeof result.matches[0].reason).toBe('string');
      expect(result.matches[0].reason.length).toBeGreaterThan(0);
    }
  });
});
