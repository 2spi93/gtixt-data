/**
 * Redis Cache Client
 * Handles caching for FCA API responses to reduce API calls
 * 
 * Cache Strategy:
 * - Firm details: 24-hour TTL (86400 seconds)
 * - Search results: 1-hour TTL (3600 seconds)
 * - Key pattern: `fca:firm:{frn}` or `fca:search:{normalizedName}`
 */

import Redis from 'ioredis';

export interface CacheConfig {
  host?: string;
  port?: number;
  password?: string;
  db?: number;
  keyPrefix?: string;
  enableOfflineQueue?: boolean;
}

export interface CacheMetrics {
  hits: number;
  misses: number;
  sets: number;
  errors: number;
  hitRate: number;
}

export class RedisCache {
  private client: Redis;
  private metrics: CacheMetrics = {
    hits: 0,
    misses: 0,
    sets: 0,
    errors: 0,
    hitRate: 0,
  };

  constructor(config?: CacheConfig) {
    const defaultConfig: CacheConfig = {
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT || '6379'),
      password: process.env.REDIS_PASSWORD,
      db: parseInt(process.env.REDIS_DB || '0'),
      keyPrefix: 'gpti:',
      enableOfflineQueue: false,
    };

    this.client = new Redis({
      ...defaultConfig,
      ...config,
      retryStrategy: (times: number) => {
        if (times > 3) {
          console.error('Redis connection failed after 3 retries');
          return null;
        }
        return Math.min(times * 1000, 3000);
      },
    });

    this.client.on('error', (error) => {
      console.error('Redis error:', error);
      this.metrics.errors++;
    });

    const isTest = process.env.NODE_ENV === 'test' || process.env.JEST_WORKER_ID !== undefined;

    this.client.on('connect', () => {
      if (!isTest) {
        console.log('Redis connected successfully');
      }
    });
  }

  /**
   * Get value from cache
   * @param key Cache key
   * @returns Cached value or null if not found
   */
  async get<T>(key: string): Promise<T | null> {
    try {
      const value = await this.client.get(key);
      
      if (value) {
        this.metrics.hits++;
        this.updateHitRate();
        return JSON.parse(value) as T;
      }
      
      this.metrics.misses++;
      this.updateHitRate();
      return null;
    } catch (error: any) {
      console.error(`Cache get error for key ${key}:`, error.message);
      this.metrics.errors++;
      return null;
    }
  }

  /**
   * Set value in cache with TTL
   * @param key Cache key
   * @param value Value to cache
   * @param ttl Time to live in seconds (default: 24 hours)
   */
  async set(key: string, value: any, ttl: number = 86400): Promise<boolean> {
    try {
      const serialized = JSON.stringify(value);
      await this.client.setex(key, ttl, serialized);
      this.metrics.sets++;
      return true;
    } catch (error: any) {
      console.error(`Cache set error for key ${key}:`, error.message);
      this.metrics.errors++;
      return false;
    }
  }

  /**
   * Delete key from cache
   * @param key Cache key
   */
  async delete(key: string): Promise<boolean> {
    try {
      const result = await this.client.del(key);
      return result > 0;
    } catch (error: any) {
      console.error(`Cache delete error for key ${key}:`, error.message);
      this.metrics.errors++;
      return false;
    }
  }

  /**
   * Delete keys matching pattern
   * @param pattern Key pattern (e.g., "fca:firm:*")
   */
  async deletePattern(pattern: string): Promise<number> {
    try {
      const keys = await this.client.keys(pattern);
      if (keys.length === 0) return 0;
      
      const result = await this.client.del(...keys);
      return result;
    } catch (error: any) {
      console.error(`Cache delete pattern error for ${pattern}:`, error.message);
      this.metrics.errors++;
      return 0;
    }
  }

  /**
   * Check if key exists
   * @param key Cache key
   */
  async exists(key: string): Promise<boolean> {
    try {
      const result = await this.client.exists(key);
      return result === 1;
    } catch (error: any) {
      console.error(`Cache exists error for key ${key}:`, error.message);
      this.metrics.errors++;
      return false;
    }
  }

  /**
   * Get remaining TTL for key
   * @param key Cache key
   * @returns TTL in seconds, -1 if no expiry, -2 if key doesn't exist
   */
  async getTTL(key: string): Promise<number> {
    try {
      return await this.client.ttl(key);
    } catch (error: any) {
      console.error(`Cache TTL error for key ${key}:`, error.message);
      this.metrics.errors++;
      return -2;
    }
  }

  /**
   * Clear all cache (use with caution)
   */
  async clear(): Promise<boolean> {
    try {
      await this.client.flushdb();
      console.log('Cache cleared successfully');
      return true;
    } catch (error: any) {
      console.error('Cache clear error:', error.message);
      this.metrics.errors++;
      return false;
    }
  }

  /**
   * Get cache metrics
   */
  getMetrics(): CacheMetrics {
    return { ...this.metrics };
  }

  /**
   * Reset metrics
   */
  resetMetrics(): void {
    this.metrics = {
      hits: 0,
      misses: 0,
      sets: 0,
      errors: 0,
      hitRate: 0,
    };
  }

  /**
   * Update hit rate percentage
   */
  private updateHitRate(): void {
    const total = this.metrics.hits + this.metrics.misses;
    this.metrics.hitRate = total > 0 ? (this.metrics.hits / total) * 100 : 0;
  }

  /**
   * Close Redis connection
   */
  async close(): Promise<void> {
    if (!this.client) return;

    const status = this.client.status;
    if (status === 'end') return;

    try {
      await this.client.quit();
    } catch (error) {
      try {
        this.client.disconnect();
      } catch {
        // ignore
      }
    }
  }

  /**
   * Check if Redis is connected
   */
  isConnected(): boolean {
    return this.client.status === 'ready';
  }

  /**
   * Ping Redis server
   */
  async ping(): Promise<boolean> {
    try {
      const result = await this.client.ping();
      return result === 'PONG';
    } catch (error) {
      return false;
    }
  }
}

// Singleton instance
let cacheInstance: RedisCache | null = null;

/**
 * Get singleton cache instance
 */
export function getCache(config?: CacheConfig): RedisCache {
  if (!cacheInstance) {
    cacheInstance = new RedisCache(config);
  }
  return cacheInstance;
}

/**
 * Close cache connection (for testing/cleanup)
 */
export async function closeCache(): Promise<void> {
  if (cacheInstance) {
    await cacheInstance.close();
    cacheInstance = null;
  }
}
