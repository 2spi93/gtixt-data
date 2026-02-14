/**
 * Verification & Screening REST API
 * Express endpoints for firm verification and sanctions screening
 */

import express, { Request, Response, Router } from 'express';
import { EnhancedRVIAgent } from '../agents/rvi/rvi-enhanced.agent';
import { getSSSAgent, SSSAgent } from '../agents/sss/sss-sanctions.agent';
import { DatabaseClient, SanctionsEntity } from '../db/postgres-client';
import { MOCK_OFAC_ENTITIES, MOCK_UN_ENTITIES } from '../data/mock-sanctions';

class MockSanctionsDatabase {
  private entities: SanctionsEntity[];

  constructor() {
    let id = 1;
    this.entities = [...MOCK_OFAC_ENTITIES, ...MOCK_UN_ENTITIES].map((entity) => ({
      ...entity,
      id: id++,
    }));
  }

  private normalize(name: string): string {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  async searchExact(name: string): Promise<SanctionsEntity[]> {
    const normalized = this.normalize(name);
    return this.entities.filter((e) => e.name_normalized === normalized);
  }

  async searchFuzzy(name: string, _threshold: number): Promise<SanctionsEntity[]> {
    const normalized = this.normalize(name);
    const firstWord = normalized.split(' ')[0];
    return this.entities.filter((e) => e.name_normalized.includes(firstWord));
  }

  async query<T>(sql: string, params?: any[]): Promise<{ rows: T[] }> {
    if (sql.includes('ANY(name_variants)')) {
      const rawName = (params?.[0] || '').toString();
      const normalized = (params?.[1] || '').toString();
      const rows = this.entities.filter((e) => {
        const aliasMatch = e.name_variants.some((v) => v.toLowerCase() === rawName.toLowerCase());
        return aliasMatch || e.name_normalized === normalized;
      });
      return { rows: rows as T[] };
    }

    if (sql.includes('ILIKE')) {
      const pattern = (params?.[0] || '').toString().replace(/%/g, '').toLowerCase();
      const rows = this.entities.filter((e) => e.name_normalized.includes(pattern));
      return { rows: rows as T[] };
    }

    return { rows: [] as T[] };
  }

  async recordMatch(): Promise<number> {
    return 1;
  }

  async getStatistics(): Promise<any[]> {
    return [
      {
        list_name: 'MOCK',
        total_entities: this.entities.length,
      },
    ];
  }
}

/**
 * API Request/Response Types
 */

interface VerifyRequest {
  firmName: string;
  country?: string;
}

interface VerifyResponse {
  status: 'success' | 'error';
  data?: {
    firmName: string;
    overallStatus: string;
    riskScore: string;
    fca: {
      status: string;
      firmName?: string;
      confidence: number;
    };
    sanctions: {
      status: string;
      matchCount: number;
      entities: string[];
    };
    riskFactors: string[];
    duration: number;
  };
  error?: string;
}

interface ScreenRequest {
  name: string;
  threshold?: number;
  includeAliases?: boolean;
  matchTypes?: string[];
}

interface ScreenResponse {
  status: 'success' | 'error';
  data?: {
    name: string;
    screeningStatus: string;
    matches: number;
    confidence: number;
    entities: Array<{
      name: string;
      type: string;
      program: string;
      matchType: string;
      score: number;
    }>;
    duration: number;
  };
  error?: string;
}

interface BatchScreenRequest {
  names: string[];
  threshold?: number;
}

interface BatchScreenResponse {
  status: 'success' | 'error';
  data?: {
    totalRequests: number;
    results: Array<{
      name: string;
      screeningStatus: string;
      matches: number;
      confidence: number;
    }>;
    totalDuration: number;
    averageDuration: number;
  };
  error?: string;
}

interface StatisticsResponse {
  status: 'success' | 'error';
  data?: {
    fcaIntegration: {
      status: string;
      mockMode: boolean;
    };
    sanctionsDatabase: {
      totalEntities: number;
      ofacEntities: number;
      unEntities: number;
      individuals: number;
      entities: number;
    };
    screening: {
      totalScreenings: number;
      matches: number;
      average_duration_ms: number;
      cache_hit_rate?: number;
    };
    performance: {
      avgVerificationTime: number;
      avgScreeningTime: number;
      p95ResponseTime: number;
    };
  };
  error?: string;
}

/**
 * API Routes
 */
export class VerificationAPI {
  private router: Router;
  private rviAgent: EnhancedRVIAgent;
  private sssAgent: SSSAgent;
  private mockMode: boolean;
  private stats = {
    totalVerifications: 0,
    totalScreenings: 0,
    sanctionsMatches: 0,
    totalDuration: 0,
    verificationDurations: [] as number[],
    screeningDurations: [] as number[],
  };

  constructor(options?: { mockMode?: boolean; rviAgent?: EnhancedRVIAgent; sssAgent?: SSSAgent }) {
    this.router = express.Router();
    this.mockMode = options?.mockMode ?? process.env.MOCK_MODE !== 'false';

    const db = this.mockMode ? (new MockSanctionsDatabase() as unknown as DatabaseClient) : undefined;

    this.sssAgent = options?.sssAgent || getSSSAgent(db);
    this.rviAgent = options?.rviAgent || new EnhancedRVIAgent(this.mockMode, this.sssAgent);
    this.setupRoutes();
  }

  /**
   * Setup routes
   */
  private setupRoutes(): void {
    // POST /api/verify - Firm verification with sanctions screening
    this.router.post('/verify', this.handleVerify.bind(this));

    // POST /api/screen - Single sanctions screening
    this.router.post('/screen', this.handleScreen.bind(this));

    // POST /api/screen/batch - Batch sanctions screening
    this.router.post('/screen/batch', this.handleBatchScreen.bind(this));

    // GET /api/statistics - Get statistics
    this.router.get('/statistics', this.handleStatistics.bind(this));

    // GET /api/health - Health check
    this.router.get('/health', this.handleHealth.bind(this));
  }

  /**
   * POST /api/verify
   * Verify firm against FCA registry + sanctions lists
   */
  private async handleVerify(req: Request, res: Response): Promise<void> {
    try {
      const { firmName, country } = req.body as VerifyRequest;

      if (!firmName) {
        res.status(400).json({
          status: 'error',
          error: 'firmName is required',
        } as VerifyResponse);
        return;
      }

      const startTime = Date.now();

      // Execute verification
      const result = await this.rviAgent.verify(firmName);

      const duration = Date.now() - startTime;
      this.recordVerification(duration);

      const response: VerifyResponse = {
        status: 'success',
        data: {
          firmName,
          overallStatus: result.status,
          riskScore: result.riskScore,
          fca: {
            status: result.fca.status,
            firmName: result.fca.firm?.name,
            confidence: result.fca.confidence,
          },
          sanctions: {
            status: result.sanctions.status,
            matchCount: result.sanctions.matches,
            entities: result.sanctions.entities,
          },
          riskFactors: result.riskFactors,
          duration,
        },
      };

      res.json(response);
    } catch (error: any) {
      console.error('Verification error:', error.message);
      res.status(500).json({
        status: 'error',
        error: error.message || 'Verification failed',
      } as VerifyResponse);
    }
  }

  /**
   * POST /api/screen
   * Screen entity against OFAC/UN sanctions lists
   */
  private async handleScreen(req: Request, res: Response): Promise<void> {
    try {
      const { name, threshold, includeAliases, matchTypes } = req.body as ScreenRequest;

      if (!name) {
        res.status(400).json({
          status: 'error',
          error: 'name is required',
        } as ScreenResponse);
        return;
      }

      const startTime = Date.now();

      // Execute screening
      const result = await this.sssAgent.screen({
        name,
        threshold: threshold || 0.85,
        includeAliases: includeAliases !== false,
        matchTypes: (matchTypes as any) || ['exact', 'fuzzy', 'phonetic'],
      });

      const duration = Date.now() - startTime;
      this.recordScreening(duration, result.matches.length);

      // Format matches
      const formattedMatches = result.matches.map((m) => ({
        name: m.entity.primary_name,
        type: m.entity.entity_type,
        program: m.entity.program,
        matchType: m.matchType,
        score: m.similarityScore,
      }));

      const response: ScreenResponse = {
        status: 'success',
        data: {
          name,
          screeningStatus: result.status,
          matches: result.matches.length,
          confidence:
            result.matches.length > 0
              ? result.matches.reduce((sum, m) => sum + m.similarityScore, 0) / result.matches.length
              : 0,
          entities: formattedMatches,
          duration,
        },
      };

      res.json(response);
    } catch (error: any) {
      console.error('Screening error:', error.message);
      res.status(500).json({
        status: 'error',
        error: error.message || 'Screening failed',
      } as ScreenResponse);
    }
  }

  /**
   * POST /api/screen/batch
   * Batch screen multiple entities
   */
  private async handleBatchScreen(req: Request, res: Response): Promise<void> {
    try {
      const { names, threshold } = req.body as BatchScreenRequest;

      if (!names || !Array.isArray(names) || names.length === 0) {
        res.status(400).json({
          status: 'error',
          error: 'names array is required',
        } as BatchScreenResponse);
        return;
      }

      if (names.length > 100) {
        res.status(400).json({
          status: 'error',
          error: 'Maximum 100 names per batch',
        } as BatchScreenResponse);
        return;
      }

      const startTime = Date.now();

      // Execute batch screening
      const batchResult = await this.sssAgent.screenBatch(
        names.map((name) => ({
          name,
          threshold: threshold || 0.85,
          includeAliases: true,
        }))
      );

      const totalDuration = Date.now() - startTime;
      this.recordScreening(totalDuration, batchResult.results.reduce((sum, r) => sum + r.matches.length, 0));

      const results = batchResult.results.map((r) => ({
        name: r.request.name,
        screeningStatus: r.status,
        matches: r.matches.length,
        confidence:
          r.matches.length > 0
            ? r.matches.reduce((sum, m) => sum + m.similarityScore, 0) / r.matches.length
            : 0,
      }));

      const response: BatchScreenResponse = {
        status: 'success',
        data: {
          totalRequests: names.length,
          results,
          totalDuration,
          averageDuration: totalDuration / names.length,
        },
      };

      res.json(response);
    } catch (error: any) {
      console.error('Batch screening error:', error.message);
      res.status(500).json({
        status: 'error',
        error: error.message || 'Batch screening failed',
      } as BatchScreenResponse);
    }
  }

  /**
   * GET /api/statistics
   * Get API statistics and performance metrics
   */
  private async handleStatistics(req: Request, res: Response): Promise<void> {
    try {
      // Calculate average durations
      const avgVerificationTime =
        this.stats.verificationDurations.length > 0
          ? this.stats.verificationDurations.reduce((a, b) => a + b, 0) / this.stats.verificationDurations.length
          : 0;

      const avgScreeningTime =
        this.stats.screeningDurations.length > 0
          ? this.stats.screeningDurations.reduce((a, b) => a + b, 0) / this.stats.screeningDurations.length
          : 0;

      // Calculate P95 response time
      const allDurations = [...this.stats.verificationDurations, ...this.stats.screeningDurations].sort((a, b) => a - b);
      const p95Index = Math.floor(allDurations.length * 0.95);
      const p95ResponseTime = allDurations[p95Index] || 0;

      const response: StatisticsResponse = {
        status: 'success',
        data: {
          fcaIntegration: {
            status: 'operational',
            mockMode: this.mockMode,
          },
          sanctionsDatabase: {
            totalEntities: 10, // Mock data
            ofacEntities: 5,
            unEntities: 5,
            individuals: 6,
            entities: 4,
          },
          screening: {
            totalScreenings: this.stats.totalScreenings,
            matches: this.stats.sanctionsMatches,
            average_duration_ms: avgScreeningTime,
          },
          performance: {
            avgVerificationTime,
            avgScreeningTime,
            p95ResponseTime,
          },
        },
      };

      res.json(response);
    } catch (error: any) {
      console.error('Statistics error:', error.message);
      res.status(500).json({
        status: 'error',
        error: error.message || 'Failed to get statistics',
      } as StatisticsResponse);
    }
  }

  /**
   * GET /api/health
   * Health check endpoint
   */
  private handleHealth(req: Request, res: Response): void {
    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      endpoints: {
        verify: 'POST /api/verify',
        screen: 'POST /api/screen',
        batchScreen: 'POST /api/screen/batch',
        statistics: 'GET /api/statistics',
        health: 'GET /api/health',
      },
    });
  }

  /**
   * Record verification for statistics
   */
  private recordVerification(duration: number): void {
    this.stats.totalVerifications++;
    this.stats.totalDuration += duration;
    this.stats.verificationDurations.push(duration);

    // Keep last 1000 durations for P95 calculation
    if (this.stats.verificationDurations.length > 1000) {
      this.stats.verificationDurations.shift();
    }
  }

  /**
   * Record screening for statistics
   */
  private recordScreening(duration: number, matches: number): void {
    this.stats.totalScreenings++;
    this.stats.sanctionsMatches += matches;
    this.stats.screeningDurations.push(duration);

    // Keep last 1000 durations for P95 calculation
    if (this.stats.screeningDurations.length > 1000) {
      this.stats.screeningDurations.shift();
    }
  }

  /**
   * Get router
   */
  getRouter(): Router {
    return this.router;
  }

  /**
   * Get statistics
   */
  getStats() {
    return this.stats;
  }
}

/**
 * Create and setup Express app with API
 */
export function setupVerificationAPI(app: express.Express): void {
  const api = new VerificationAPI();
  app.use('/api', api.getRouter());
}

/**
 * Export for external use
 */
export default VerificationAPI;
