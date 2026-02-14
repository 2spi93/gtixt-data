/**
 * FCA Registry API Client
 * Real-world UK Financial Conduct Authority registry integration
 * 
 * Features:
 * - Redis caching (24-hour TTL for firm details, 1-hour for searches)
 * - Rate limiting (60 requests/minute)
 * - Automatic retry with exponential backoff
 */

import axios, { AxiosInstance } from 'axios';
import { RedisCache, getCache } from '../cache/redis-client';
import { RateLimiter, createFCARateLimiter } from '../utils/rate-limiter';

// Types
export interface FCAFirmSearchResult {
  firm_id: string;
  name: string;
  authorization_status: 'authorized' | 'suspended' | 'revoked';
  authorization_date: Date;
  type: string;
  country: string;
  regulated_activities: string[];
  website?: string;
}

export interface FCAFirmDetails extends FCAFirmSearchResult {
  permissions: Array<{
    activity: string;
    label: string;
    authorized: boolean;
    since: Date;
  }>;
  enforcement_actions: Array<{
    date: Date;
    type: 'fine' | 'warning' | 'suspension';
    amount?: number;
    description: string;
    status: 'active' | 'resolved';
  }>;
  address: {
    street: string;
    city: string;
    postcode: string;
    country: string;
  };
  last_update: Date;
}

export interface FCASearchParams {
  name: string;
  country?: string;
  limit?: number;
  offset?: number;
}

export interface FCAStatusCheckRequest {
  firms: Array<{
    name: string;
    country?: string;
  }>;
}

export interface FCAStatusCheckResult {
  input: { name: string; country?: string };
  found: boolean;
  firm_id?: string;
  status?: string;
  confidence: number;
}

// Client Class
export class FCAClient {
  private client: AxiosInstance;
  private baseUrl = 'https://register.fca.org.uk/api';
  private apiKey: string;
  private cache: RedisCache | null = null;
  private rateLimiter: RateLimiter | null = null;
  private useCache: boolean;
  private retryConfig = {
    maxRetries: 3,
    delays: [5000, 10000, 20000], // 5s, 10s, 20s
  };

  constructor(apiKey: string, useCache: boolean = true) {
    this.apiKey = apiKey;
    this.useCache = useCache;

    // Initialize cache and rate limiter if enabled
    if (this.useCache) {
      try {
        this.cache = getCache();
        this.rateLimiter = createFCARateLimiter();
        console.log('FCA Client: Cache and rate limiter enabled');
      } catch (error) {
        console.warn('FCA Client: Failed to initialize cache/rate limiter, running without them');
        this.cache = null;
        this.rateLimiter = null;
      }
    }

    this.client = axios.create({
      baseURL: this.baseUrl,
      headers: {
        'X-API-Key': apiKey,
        'Content-Type': 'application/json',
      },
      timeout: 10000, // 10s timeout
    });

    // Add retry interceptor
    this.client.interceptors.response.use(
      (response: any) => response,
      async (error: any) => {
        const config = error.config;
        if (!config || !config.retryCount) {
          config.retryCount = 0;
        }

        if (config.retryCount < this.retryConfig.maxRetries) {
          config.retryCount++;
          const delay = this.retryConfig.delays[config.retryCount - 1];
          await new Promise((resolve) => setTimeout(resolve, delay));
          return this.client(config);
        }

        throw error;
      }
    );
  }

  /**
   * Search for firms by name (with caching)
   */
  async search(params: FCASearchParams): Promise<FCAFirmSearchResult[]> {
    const cacheKey = `fca:search:${this.normalizeName(params.name)}`;

    // Try cache first
    if (this.cache) {
      const cached = await this.cache.get<FCAFirmSearchResult[]>(cacheKey);
      if (cached) {
        console.log(`Cache HIT for search: ${params.name}`);
        return cached;
      }
      console.log(`Cache MISS for search: ${params.name}`);
    }

    // Acquire rate limit token
    if (this.rateLimiter) {
      await this.rateLimiter.acquire();
    }

    try {
      const response = await this.client.get('/v1/firms/search', {
        params: {
          q: params.name,
          country: params.country,
          limit: params.limit || 10,
          offset: params.offset || 0,
        },
      });

      const results = (response.data.firms || []).map((firm: any) => ({
        firm_id: firm.firm_id,
        name: firm.name,
        authorization_status: firm.authorization_status,
        authorization_date: new Date(firm.authorization_date),
        type: firm.type,
        country: firm.country,
        regulated_activities: firm.regulated_activities || [],
        website: firm.website,
      }));

      // Cache results for 1 hour
      if (this.cache) {
        await this.cache.set(cacheKey, results, 3600);
      }

      return results;
    } catch (error: any) {
      console.error(`FCA search failed for "${params.name}":`, error);
      const errorMsg = error instanceof Error ? error.message : String(error);
      throw new FCAPIError(`Search failed: ${errorMsg}`);
    }
  }

  /**
   * Get detailed firm information (with caching)
   */
  async getFirmDetails(firmId: string): Promise<FCAFirmDetails> {
    const cacheKey = `fca:firm:${firmId}`;

    // Try cache first
    if (this.cache) {
      const cached = await this.cache.get<FCAFirmDetails>(cacheKey);
      if (cached) {
        console.log(`Cache HIT for firm details: ${firmId}`);
        // Convert date strings back to Date objects
        return {
          ...cached,
          authorization_date: new Date(cached.authorization_date),
          last_update: new Date(cached.last_update),
          permissions: cached.permissions.map((p) => ({
            ...p,
            since: new Date(p.since),
          })),
          enforcement_actions: cached.enforcement_actions.map((a) => ({
            ...a,
            date: new Date(a.date),
          })),
        };
      }
      console.log(`Cache MISS for firm details: ${firmId}`);
    }

    // Acquire rate limit token
    if (this.rateLimiter) {
      await this.rateLimiter.acquire();
    }

    try {
      const response = await this.client.get(`/v1/firms/${firmId}`);
      const data = response.data;

      const details: FCAFirmDetails = {
        firm_id: data.firm_id,
        name: data.name,
        authorization_status: data.authorization_status,
        authorization_date: new Date(data.authorization_date),
        type: data.type,
        country: data.country,
        regulated_activities: data.regulated_activities || [],
        permissions: (data.permissions || []).map((p: any) => ({
          activity: p.activity,
          label: p.label,
          authorized: p.authorized,
          since: new Date(p.since),
        })),
        enforcement_actions: (data.enforcement_actions || []).map(
          (a: any) => ({
            date: new Date(a.date),
            type: a.type,
            amount: a.amount,
            description: a.description,
            status: a.status,
          })
        ),
        address: {
          street: data.address.street,
          city: data.address.city,
          postcode: data.address.postcode,
          country: data.address.country,
        },
        last_update: new Date(data.last_update),
      };

      // Cache firm details for 24 hours
      if (this.cache) {
        await this.cache.set(cacheKey, details, 86400);
      }

      return details;
    } catch (error: any) {
      console.error(`FCA firm details failed for "${firmId}":`, error);
      const errorMsg = error instanceof Error ? error.message : String(error);
      throw new FCAPIError(`Details failed: ${errorMsg}`);
    }
  }

  /**
   * Normalize firm name for caching
   */
  private normalizeName(name: string): string {
    return name.toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  /**
   * Get cache metrics
   */
  getCacheMetrics() {
    return this.cache?.getMetrics() || null;
  }

  /**
   * Get rate limiter stats
   */
  getRateLimiterStats() {
    return this.rateLimiter?.getStats() || null;
  }

  /**
   * Clear cache for specific firm or all
   */
  async clearCache(firmId?: string): Promise<boolean> {
    if (!this.cache) return false;

    if (firmId) {
      return await this.cache.delete(`fca:firm:${firmId}`);
    } else {
      return await this.cache.deletePattern('fca:*') > 0;
    }
  }

  /**
   * Bulk status check for multiple firms
   */
  async statusCheck(
    request: FCAStatusCheckRequest
  ): Promise<FCAStatusCheckResult[]> {
    try {
      const response = await this.client.post('/v1/firms/status-check', request);

      return response.data.results || [];
    } catch (error: any) {
      console.error(`FCA status check failed:`, error);
      const errorMsg = error instanceof Error ? error.message : String(error);
      throw new FCAPIError(`Status check failed: ${errorMsg}`);
    }
  }

  /**
   * Check if API credentials are valid
   */
  async validateCredentials(): Promise<boolean> {
    try {
      await this.client.get('/v1/health');
      return true;
    } catch (error) {
      console.error('FCA API credentials invalid:', error);
      return false;
    }
  }
}

// Custom Error Class
export class FCAPIError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'FCAPIError';
  }
}

// Mock Client for Testing
export class FCAClientMock extends FCAClient {
  constructor() {
    super('mock-key', false);
  }

  async search(params: FCASearchParams): Promise<FCAFirmSearchResult[]> {
    // Mock data for testing
    const mockData: Record<string, FCAFirmSearchResult[]> = {
      ftmo: [
        {
          firm_id: 'FIRM123456',
          name: 'FTMO Limited',
          authorization_status: 'authorized',
          authorization_date: new Date('2015-03-12'),
          type: 'Investment Firm',
          country: 'GB',
          regulated_activities: ['DRVSTR', 'EDDCAS'],
          website: 'https://ftmo.com',
        },
      ],
      xm: [
        {
          firm_id: 'FIRM654321',
          name: 'XM Limited',
          authorization_status: 'authorized',
          authorization_date: new Date('2008-06-15'),
          type: 'Investment Firm',
          country: 'AU', // Non-UK (would not be in real FCA registry)
          regulated_activities: ['DRVSTR'],
          website: 'https://xm.com',
        },
      ],
    };

    // Search in mock data (case-insensitive, partial match)
    const searchTerm = params.name.toLowerCase().replace(/\s+(ltd|limited|llc|inc|corp)\.?$/i, '').trim();
    
    for (const [key, firms] of Object.entries(mockData)) {
      const keyBase = key.replace(/\s+(ltd|limited|llc|inc|corp)\.?$/i, '').trim();
      if (searchTerm.includes(key) || key.includes(searchTerm) || 
          searchTerm.includes(keyBase) || keyBase.includes(searchTerm.split(' ')[0])) {
        return firms;
      }
    }
    
    return [];
  }

  async getFirmDetails(firmId: string): Promise<FCAFirmDetails> {
    // Mock details
    return {
      firm_id: firmId,
      name: 'FTMO Limited',
      authorization_status: 'authorized',
      authorization_date: new Date('2015-03-12'),
      type: 'Investment Firm',
      country: 'GB',
      regulated_activities: ['DRVSTR', 'EDDCAS'],
      permissions: [
        {
          activity: 'DRVSTR',
          label: 'Dealing in investments as principal',
          authorized: true,
          since: new Date('2015-03-12'),
        },
        {
          activity: 'EDDCAS',
          label: 'Arranging deals in investments',
          authorized: true,
          since: new Date('2015-03-12'),
        },
      ],
      enforcement_actions: [],
      address: {
        street: '10 Newgate Street',
        city: 'London',
        postcode: 'EC1A 7AZ',
        country: 'GB',
      },
      last_update: new Date(),
    };
  }

  async statusCheck(
    request: FCAStatusCheckRequest
  ): Promise<FCAStatusCheckResult[]> {
    return request.firms.map((firm) => ({
      input: { name: firm.name, country: firm.country },
      found: firm.name.toLowerCase().includes('ftmo'),
      firm_id: firm.name.toLowerCase().includes('ftmo') ? 'FIRM123456' : undefined,
      status: firm.name.toLowerCase().includes('ftmo') ? 'authorized' : 'not_found',
      confidence: firm.name.toLowerCase().includes('ftmo') ? 0.98 : 0.0,
    }));
  }

  async validateCredentials(): Promise<boolean> {
    return true;
  }
}
