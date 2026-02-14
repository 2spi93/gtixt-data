/**
 * Redis Cache Client Tests
 * Tests caching operations, TTL, metrics tracking
 */

import { describe, it, expect, beforeAll, afterAll } from '@jest/globals';
import { RedisCache, getCache, closeCache } from './redis-client';

// Check if Redis is available
let redisAvailable = false;
let cache: RedisCache | null = null;

describe('Redis Cache Client', () => {
  beforeAll(async () => {
    // Test Redis connection
    try {
      cache = new RedisCache({
        host: process.env.REDIS_HOST || 'localhost',
        port: parseInt(process.env.REDIS_PORT || '6379'),
        db: 15,
        keyPrefix: 'test:',
      });
      await cache!.ping();
      redisAvailable = true;
      console.log('✅ Redis available, running tests');
    } catch (error) {
      console.log('⚠️  Redis not available, all tests will be skipped');
      redisAvailable = false;
      cache = null;
    }
  }, 10000);

  afterAll(async () => {
    if (cache && redisAvailable) {
      try {
        await cache!.clear();
        await cache!.close();
      } catch (error) {
        // Ignore cleanup errors
      }
    }
  });

  const runIfRedis = (name: string, fn: () => Promise<void>, timeout?: number) => {
    const runner = redisAvailable && cache ? it : it.skip;

    runner(name, async () => {
      if (!redisAvailable || !cache) {
        return;
      }

      // Clear before each test
      try {
        await cache.clear();
        cache.resetMetrics();
      } catch (error) {
        // Ignore
      }

      await fn();
    }, timeout);
  };

  describe('Connection', () => {
    runIfRedis('should connect to Redis', async () => {
      const isConnected = cache!.isConnected();
      expect(isConnected).toBe(true);
    });

    runIfRedis('should ping Redis successfully', async () => {
      const pong = await cache!.ping();
      expect(pong).toBe(true);
    });
  });

  describe('Basic Operations', () => {
    runIfRedis('should set and get a value', async () => {
      const key = 'test:key1';
      const value = { name: 'FTMO Limited', frn: 'FRN123456' };

      await cache!.set(key, value, 60);
      const result = await cache!.get<typeof value>(key);

      expect(result).toEqual(value);
    });

    runIfRedis('should return null for non-existent key', async () => {
      const result = await cache!.get('test:nonexistent');
      expect(result).toBeNull();
    });

    runIfRedis('should delete a key', async () => {
      const key = 'test:delete-me';
      await cache!.set(key, { data: 'test' });

      const deleted = await cache!.delete(key);
      expect(deleted).toBe(true);

      const result = await cache!.get(key);
      expect(result).toBeNull();
    });

    runIfRedis('should check if key exists', async () => {
      const key = 'test:exists-check';
      
      let exists = await cache!.exists(key);
      expect(exists).toBe(false);

      await cache!.set(key, { data: 'test' });
      exists = await cache!.exists(key);
      expect(exists).toBe(true);
    });
  });

  describe('TTL (Time To Live)', () => {
    runIfRedis('should expire key after TTL', async () => {
      const key = 'test:expire-soon';
      await cache!.set(key, { data: 'test' }, 1); // 1 second TTL

      let result = await cache!.get(key);
      expect(result).not.toBeNull();

      // Wait for expiration
      await new Promise((resolve) => setTimeout(resolve, 1500));

      result = await cache!.get(key);
      expect(result).toBeNull();
    }, 3000);

    runIfRedis('should get remaining TTL', async () => {
      const key = 'test:ttl-check';
      await cache!.set(key, { data: 'test' }, 60);

      const ttl = await cache!.getTTL(key);
      expect(ttl).toBeGreaterThan(50);
      expect(ttl).toBeLessThanOrEqual(60);
    });

    runIfRedis('should return -2 for non-existent key TTL', async () => {
      const ttl = await cache!.getTTL('test:nonexistent');
      expect(ttl).toBe(-2);
    });
  });

  describe('Pattern Matching', () => {
    runIfRedis('should delete keys matching pattern', async () => {
      await cache!.set('test:firm:1', { name: 'Firm 1' });
      await cache!.set('test:firm:2', { name: 'Firm 2' });
      await cache!.set('test:firm:3', { name: 'Firm 3' });
      await cache!.set('test:other:1', { name: 'Other' });

      const deleted = await cache!.deletePattern('test:firm:*');
      expect(deleted).toBe(3);

      const firm1 = await cache!.get('test:firm:1');
      expect(firm1).toBeNull();

      const other = await cache!.get('test:other:1');
      expect(other).not.toBeNull();
    });
  });

  describe('Cache Metrics', () => {
    runIfRedis('should track cache hits', async () => {
      const key = 'test:metrics-hit';
      await cache!.set(key, { data: 'test' });

      await cache!.get(key); // HIT
      await cache!.get(key); // HIT

      const metrics = cache!.getMetrics();
      expect(metrics.hits).toBe(2);
      expect(metrics.misses).toBe(0);
      expect(metrics.hitRate).toBe(100);
    });

    runIfRedis('should track cache misses', async () => {
      await cache!.get('test:miss1'); // MISS
      await cache!.get('test:miss2'); // MISS

      const metrics = cache!.getMetrics();
      expect(metrics.hits).toBe(0);
      expect(metrics.misses).toBe(2);
      expect(metrics.hitRate).toBe(0);
    });

    runIfRedis('should calculate hit rate correctly', async () => {
      const key = 'test:hitrate';
      await cache!.set(key, { data: 'test' });

      await cache!.get(key); // HIT
      await cache!.get('test:miss'); // MISS
      await cache!.get(key); // HIT
      await cache!.get('test:miss'); // MISS

      const metrics = cache!.getMetrics();
      expect(metrics.hits).toBe(2);
      expect(metrics.misses).toBe(2);
      expect(metrics.hitRate).toBe(50);
    });

    runIfRedis('should track sets', async () => {
      await cache!.set('test:set1', { data: 'test1' });
      await cache!.set('test:set2', { data: 'test2' });

      const metrics = cache!.getMetrics();
      expect(metrics.sets).toBe(2);
    });

    runIfRedis('should reset metrics', async () => {
      await cache!.set('test:key', { data: 'test' });
      cache!.resetMetrics();

      const metrics = cache!.getMetrics();
      expect(metrics.hits).toBe(0);
      expect(metrics.misses).toBe(0);
      expect(metrics.sets).toBe(0);
      expect(metrics.hitRate).toBe(0);
    });
  });

  describe('Complex Data Types', () => {
    runIfRedis('should handle nested objects', async () => {
      const key = 'test:nested';
      const value = {
        firm: {
          name: 'FTMO Limited',
          permissions: ['DRVSTR', 'EDDCAS'],
          address: {
            city: 'London',
            postcode: 'EC1A 7AZ',
          },
        },
      };

      await cache!.set(key, value);
      const result = await cache!.get<typeof value>(key);

      expect(result).toEqual(value);
    });

    runIfRedis('should handle arrays', async () => {
      const key = 'test:array';
      const value = [
        { id: 1, name: 'Firm 1' },
        { id: 2, name: 'Firm 2' },
      ];

      await cache!.set(key, value);
      const result = await cache!.get<typeof value>(key);

      expect(result).toEqual(value);
    });
  });

  describe('Singleton Pattern', () => {
    runIfRedis('should return same instance', async () => {
      const cache1 = getCache({ db: 15, keyPrefix: 'test:' });
      const cache2 = getCache({ db: 15, keyPrefix: 'test:' });

      expect(cache1).toBe(cache2);

      await closeCache();
    });
  });

  describe('Error Handling', () => {
    runIfRedis('should handle get errors gracefully', async () => {
      // Close connection to simulate error
      await cache!.close();

      const result = await cache!.get('test:error');
      expect(result).toBeNull();
    });

    runIfRedis('should handle set errors gracefully', async () => {
      await cache!.close();

      const success = await cache!.set('test:error', { data: 'test' });
      expect(success).toBe(false);
    });
  });

  describe('Clear Operations', () => {
    runIfRedis('should clear all keys in database', async () => {
      await cache!.set('test:key1', { data: 'test1' });
      await cache!.set('test:key2', { data: 'test2' });

      await cache!.clear();

      const key1 = await cache!.get('test:key1');
      const key2 = await cache!.get('test:key2');

      expect(key1).toBeNull();
      expect(key2).toBeNull();
    });
  });
});
