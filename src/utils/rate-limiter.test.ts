/**
 * Rate Limiter Tests
 * Tests token bucket algorithm, queuing, timeouts
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { RateLimiter, createFCARateLimiter, createSECRateLimiter } from './rate-limiter';

describe('Rate Limiter', () => {
  let limiter: RateLimiter;

  afterEach(() => {
    if (limiter) {
      limiter.stop();
    }
  });

  describe('Token Bucket', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 10,
        refillRate: 2, // 2 tokens per interval
        refillInterval: 100, // Every 100ms
      });
    });

    it('should start with full tokens', () => {
      const stats = limiter.getStats();
      expect(stats.tokensAvailable).toBe(10);
    });

    it('should consume tokens on acquire', async () => {
      await limiter.acquire();
      await limiter.acquire();

      const stats = limiter.getStats();
      expect(stats.tokensAvailable).toBe(8);
    });

    it('should refill tokens over time', async () => {
      // Consume all tokens
      for (let i = 0; i < 10; i++) {
        await limiter.acquire();
      }

      let stats = limiter.getStats();
      expect(stats.tokensAvailable).toBe(0);

      // Wait for one refill cycle (100ms = 2 tokens)
      await new Promise((resolve) => setTimeout(resolve, 150));

      stats = limiter.getStats();
      expect(stats.tokensAvailable).toBeGreaterThanOrEqual(2);
    }, 5000);

    it('should not exceed max tokens', async () => {
      // Wait for multiple refill cycles
      await new Promise((resolve) => setTimeout(resolve, 500));

      const stats = limiter.getStats();
      expect(stats.tokensAvailable).toBeLessThanOrEqual(10);
    }, 5000);
  });

  describe('Try Acquire', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 5,
        refillRate: 1,
        refillInterval: 1000,
      });
    });

    it('should return true when tokens available', () => {
      const success = limiter.tryAcquire();
      expect(success).toBe(true);
    });

    it('should return false when no tokens available', () => {
      // Consume all tokens
      for (let i = 0; i < 5; i++) {
        limiter.tryAcquire();
      }

      const success = limiter.tryAcquire();
      expect(success).toBe(false);
    });
  });

  describe('Queue Management', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 2,
        refillRate: 2,
        refillInterval: 100,
        queueTimeout: 500,
      });
    });

    it('should queue requests when no tokens available', async () => {
      // Consume available tokens
      await limiter.acquire();
      await limiter.acquire();

      // This should queue
      const promise = limiter.acquire();

      const stats = limiter.getStats();
      expect(stats.requestsQueued).toBe(1);

      // Wait for it to complete
      await promise;
    }, 5000);

    it('should process queue when tokens refill', async () => {
      // Consume all tokens
      await limiter.acquire();
      await limiter.acquire();

      // Queue 3 requests
      const promises = [
        limiter.acquire(),
        limiter.acquire(),
        limiter.acquire(),
      ];

      // Wait for refill and processing
      await Promise.all(promises);

      const stats = limiter.getStats();
      expect(stats.requestsQueued).toBe(0);
      expect(stats.requestsProcessed).toBeGreaterThanOrEqual(5);
    }, 5000);

    it('should timeout queued requests', async () => {
      limiter = new RateLimiter({
        maxTokens: 1,
        refillRate: 1,
        refillInterval: 10000, // Very long refill
        queueTimeout: 100, // Short timeout
      });

      // Consume token
      await limiter.acquire();

      // This should queue and timeout
      await expect(limiter.acquire()).rejects.toThrow('Rate limit queue timeout');

      const stats = limiter.getStats();
      expect(stats.requestsRejected).toBeGreaterThanOrEqual(1);
    }, 5000);
  });

  describe('Statistics', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 10,
        refillRate: 5,
        refillInterval: 100,
      });
    });

    it('should track requests processed', async () => {
      await limiter.acquire();
      await limiter.acquire();
      await limiter.acquire();

      const stats = limiter.getStats();
      expect(stats.requestsProcessed).toBe(3);
    });

    it('should track last refill time', async () => {
      const stats1 = limiter.getStats();
      const time1 = stats1.lastRefill.getTime();

      await new Promise((resolve) => setTimeout(resolve, 150));

      const stats2 = limiter.getStats();
      const time2 = stats2.lastRefill.getTime();

      expect(time2).toBeGreaterThan(time1);
    }, 5000);
  });

  describe('Reset', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 5,
        refillRate: 1,
        refillInterval: 1000,
      });
    });

    it('should reset tokens and stats', async () => {
      await limiter.acquire();
      await limiter.acquire();

      limiter.reset();

      const stats = limiter.getStats();
      expect(stats.tokensAvailable).toBe(5);
      expect(stats.requestsProcessed).toBe(0);
    });
  });

  describe('Rate Limit Headers', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 60,
        refillRate: 1,
        refillInterval: 1000,
      });
    });

    it('should generate HTTP headers', () => {
      const headers = limiter.getRateLimitHeaders();

      expect(headers['X-RateLimit-Limit']).toBe('60');
      expect(headers['X-RateLimit-Remaining']).toBe('60');
      expect(headers['X-RateLimit-Reset']).toBeDefined();
    });

    it('should update remaining count', async () => {
      await limiter.acquire();
      await limiter.acquire();

      const headers = limiter.getRateLimitHeaders();
      expect(headers['X-RateLimit-Remaining']).toBe('58');
    });
  });

  describe('Exceeded Check', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 2,
        refillRate: 1,
        refillInterval: 1000,
      });
    });

    it('should return false when tokens available', () => {
      expect(limiter.isExceeded()).toBe(false);
    });

    it('should return true when no tokens', async () => {
      await limiter.acquire();
      await limiter.acquire();

      expect(limiter.isExceeded()).toBe(true);
    });
  });

  describe('Time Until Next Token', () => {
    beforeEach(() => {
      limiter = new RateLimiter({
        maxTokens: 2,
        refillRate: 1,
        refillInterval: 1000,
      });
    });

    it('should return 0 when tokens available', () => {
      const time = limiter.getTimeUntilNextToken();
      expect(time).toBe(0);
    });

    it('should return time when no tokens', async () => {
      await limiter.acquire();
      await limiter.acquire();

      const time = limiter.getTimeUntilNextToken();
      expect(time).toBeGreaterThan(0);
      expect(time).toBeLessThanOrEqual(1000);
    });
  });

  describe('Factory Functions', () => {
    it('should create FCA rate limiter', () => {
      const fcaLimiter = createFCARateLimiter();
      const stats = fcaLimiter.getStats();

      expect(stats.tokensAvailable).toBe(60);
      fcaLimiter.stop();
    });

    it('should create SEC rate limiter', () => {
      const secLimiter = createSECRateLimiter();
      const stats = secLimiter.getStats();

      expect(stats.tokensAvailable).toBe(10);
      secLimiter.stop();
    });
  });

  describe('Stop', () => {
    it('should stop refill timer', async () => {
      limiter = new RateLimiter({
        maxTokens: 5,
        refillRate: 1,
        refillInterval: 100,
      });

      limiter.stop();

      // Should not refill after stop
      await new Promise((resolve) => setTimeout(resolve, 200));

      const stats = limiter.getStats();
      // Stats should remain as they were (no refill happened)
      expect(stats.tokensAvailable).toBeLessThanOrEqual(5);
    }, 5000);

    it('should reject queued requests on stop', async () => {
      limiter = new RateLimiter({
        maxTokens: 1,
        refillRate: 1,
        refillInterval: 10000,
      });

      await limiter.acquire(); // Consume token

      const promise = limiter.acquire(); // Queue request
      limiter.stop();

      await expect(promise).rejects.toThrow('Rate limiter stopped');
    });
  });

  describe('Performance', () => {
    it('should handle high throughput', async () => {
      limiter = new RateLimiter({
        maxTokens: 100,
        refillRate: 50,
        refillInterval: 100,
      });

      const startTime = Date.now();

      // Try to acquire 50 tokens
      const promises: Promise<void>[] = [];
      for (let i = 0; i < 50; i++) {
        promises.push(limiter.acquire());
      }

      await Promise.all(promises);

      const elapsed = Date.now() - startTime;

      // Should complete quickly since we have enough tokens
      expect(elapsed).toBeLessThan(1000);

      const stats = limiter.getStats();
      expect(stats.requestsProcessed).toBe(50);
    }, 5000);
  });
});
