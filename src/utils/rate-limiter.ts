/**
 * Rate Limiter - Token Bucket Algorithm
 * Prevents exceeding API rate limits
 * 
 * Strategy:
 * - Token bucket with configurable capacity
 * - Tokens refill at constant rate
 * - Request queued if no tokens available
 * - Configurable wait timeout
 */

export interface RateLimiterConfig {
  maxTokens: number;      // Maximum tokens in bucket (e.g., 60 for 60 req/min)
  refillRate: number;     // Tokens added per interval (e.g., 1 token per second)
  refillInterval: number; // Interval in milliseconds (e.g., 1000 = 1 second)
  queueTimeout?: number;  // Max wait time for queued requests (default: 30000ms)
}

export interface RateLimiterStats {
  tokensAvailable: number;
  requestsQueued: number;
  requestsProcessed: number;
  requestsRejected: number;
  lastRefill: Date;
}

interface QueuedRequest {
  resolve: () => void;
  reject: (error: Error) => void;
  timestamp: number;
}

export class RateLimiter {
  private tokens: number;
  private maxTokens: number;
  private refillRate: number;
  private refillInterval: number;
  private queueTimeout: number;
  private queue: QueuedRequest[] = [];
  private refillTimer: NodeJS.Timeout | null = null;
  private stats = {
    requestsProcessed: 0,
    requestsRejected: 0,
    lastRefill: new Date(),
  };

  constructor(config: RateLimiterConfig) {
    this.maxTokens = config.maxTokens;
    this.refillRate = config.refillRate;
    this.refillInterval = config.refillInterval;
    this.queueTimeout = config.queueTimeout || 30000;
    this.tokens = this.maxTokens;

    // Start refill timer
    this.startRefill();
  }

  /**
   * Acquire a token (wait if necessary)
   * @returns Promise that resolves when token is acquired
   */
  async acquire(): Promise<void> {
    // If token available, use it immediately
    if (this.tokens > 0) {
      this.tokens--;
      this.stats.requestsProcessed++;
      return Promise.resolve();
    }

    // Otherwise, queue the request
    return new Promise((resolve, reject) => {
      const timestamp = Date.now();
      const timeoutId = setTimeout(() => {
        // Remove from queue if timeout
        const index = this.queue.findIndex((req) => req.timestamp === timestamp);
        if (index !== -1) {
          this.queue.splice(index, 1);
          this.stats.requestsRejected++;
          reject(new Error(`Rate limit queue timeout after ${this.queueTimeout}ms`));
        }
      }, this.queueTimeout);

      this.queue.push({
        resolve: () => {
          clearTimeout(timeoutId);
          resolve();
        },
        reject: (error) => {
          clearTimeout(timeoutId);
          reject(error);
        },
        timestamp,
      });
    });
  }

  /**
   * Try to acquire token without waiting
   * @returns true if token acquired, false if none available
   */
  tryAcquire(): boolean {
    if (this.tokens > 0) {
      this.tokens--;
      this.stats.requestsProcessed++;
      return true;
    }
    return false;
  }

  /**
   * Start refill timer
   */
  private startRefill(): void {
    this.refillTimer = setInterval(() => {
      this.refill();
    }, this.refillInterval);
  }

  /**
   * Refill tokens and process queue
   */
  private refill(): void {
    // Add tokens up to max capacity
    this.tokens = Math.min(this.tokens + this.refillRate, this.maxTokens);
    this.stats.lastRefill = new Date();

    // Process queued requests
    while (this.tokens > 0 && this.queue.length > 0) {
      const request = this.queue.shift();
      if (request) {
        this.tokens--;
        this.stats.requestsProcessed++;
        request.resolve();
      }
    }
  }

  /**
   * Get current statistics
   */
  getStats(): RateLimiterStats {
    return {
      tokensAvailable: this.tokens,
      requestsQueued: this.queue.length,
      requestsProcessed: this.stats.requestsProcessed,
      requestsRejected: this.stats.requestsRejected,
      lastRefill: this.stats.lastRefill,
    };
  }

  /**
   * Reset rate limiter
   */
  reset(): void {
    this.tokens = this.maxTokens;
    this.queue = [];
    this.stats = {
      requestsProcessed: 0,
      requestsRejected: 0,
      lastRefill: new Date(),
    };
  }

  /**
   * Stop rate limiter
   */
  stop(): void {
    if (this.refillTimer) {
      clearInterval(this.refillTimer);
      this.refillTimer = null;
    }
    
    // Reject all queued requests
    this.queue.forEach((request) => {
      request.reject(new Error('Rate limiter stopped'));
    });
    this.queue = [];
  }

  /**
   * Get rate limit headers for HTTP responses
   */
  getRateLimitHeaders(): Record<string, string> {
    const resetTime = new Date(
      this.stats.lastRefill.getTime() + this.refillInterval
    );

    return {
      'X-RateLimit-Limit': this.maxTokens.toString(),
      'X-RateLimit-Remaining': this.tokens.toString(),
      'X-RateLimit-Reset': Math.floor(resetTime.getTime() / 1000).toString(),
    };
  }

  /**
   * Check if rate limit is exceeded
   */
  isExceeded(): boolean {
    return this.tokens === 0;
  }

  /**
   * Get time until next token available (in milliseconds)
   */
  getTimeUntilNextToken(): number {
    if (this.tokens > 0) return 0;
    
    const timeSinceLastRefill = Date.now() - this.stats.lastRefill.getTime();
    const timeUntilNextRefill = this.refillInterval - timeSinceLastRefill;
    return Math.max(0, timeUntilNextRefill);
  }
}

/**
 * Create rate limiter for FCA API (60 requests per minute)
 */
export function createFCARateLimiter(): RateLimiter {
  return new RateLimiter({
    maxTokens: 60,           // 60 requests
    refillRate: 1,           // 1 token per second
    refillInterval: 1000,    // Every 1 second
    queueTimeout: 30000,     // 30 second timeout
  });
}

/**
 * Create rate limiter for SEC API (10 requests per second)
 */
export function createSECRateLimiter(): RateLimiter {
  return new RateLimiter({
    maxTokens: 10,           // 10 requests
    refillRate: 10,          // 10 tokens per second
    refillInterval: 1000,    // Every 1 second
    queueTimeout: 10000,     // 10 second timeout
  });
}
