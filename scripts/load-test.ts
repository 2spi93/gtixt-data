/**
 * Load Testing Script
 * Tests system performance with 1,000+ firms
 * 
 * Usage:
 *   npm run load-test
 *   npm run load-test -- --firms=2000 --cache=false
 */

import RVIAgent from '../src/agents/rvi/rvi-fca.agent';
import { Firm } from '../src/types/firm';
import { MOCK_FIRMS } from '../src/data/mock-firms';
import { getCache, closeCache } from '../src/cache/redis-client';

interface LoadTestConfig {
  firmCount: number;
  useMock: boolean;
  useCache: boolean;
  batchSize: number;
}

interface LoadTestResults {
  totalFirms: number;
  totalDuration: number;
  throughput: number; // firms per second
  averageLatency: number;
  minLatency: number;
  maxLatency: number;
  successful: number;
  failed: number;
  cacheMetrics?: {
    hits: number;
    misses: number;
    hitRate: number;
  };
  memoryUsage: {
    heapUsed: number;
    heapTotal: number;
    external: number;
  };
}

/**
 * Generate test firms (mix of real mock data + synthetic)
 */
function generateTestFirms(count: number): Firm[] {
  const firms: Firm[] = [];

  // Use real mock firms first
  for (let i = 0; i < Math.min(count, MOCK_FIRMS.length); i++) {
    const mockFirm = MOCK_FIRMS[i];
    firms.push({
      firm_id: `TEST_${mockFirm.firm_id}`,
      name: mockFirm.name,
      country: mockFirm.country,
      sector: 'Financial Services',
    });
  }

  // Generate synthetic firms for remaining
  for (let i = MOCK_FIRMS.length; i < count; i++) {
    firms.push({
      firm_id: `SYNTHETIC_${i}`,
      name: `Test Firm ${i}`,
      country: 'GB',
      sector: 'Financial Services',
    });
  }

  return firms;
}

/**
 * Run load test
 */
async function runLoadTest(config: LoadTestConfig): Promise<LoadTestResults> {
  console.log('\n🚀 Starting Load Test');
  console.log('='.repeat(60));
  console.log(`Firms: ${config.firmCount}`);
  console.log(`Use Mock: ${config.useMock}`);
  console.log(`Use Cache: ${config.useCache}`);
  console.log(`Batch Size: ${config.batchSize}`);
  console.log('='.repeat(60));

  // Generate test data
  const firms = generateTestFirms(config.firmCount);
  console.log(`✅ Generated ${firms.length} test firms`);

  // Initialize agent
  const agent = new RVIAgent(config.useMock);
  console.log('✅ Agent initialized');

  // Clear cache if using cache
  if (config.useCache) {
    const cache = getCache();
    await cache.clear();
    console.log('✅ Cache cleared');
  }

  // Track metrics
  const latencies: number[] = [];
  let successful = 0;
  let failed = 0;

  // Record start time
  const startTime = Date.now();
  const startMemory = process.memoryUsage();

  console.log('\n⏳ Running verification...\n');

  // Process in batches
  for (let i = 0; i < firms.length; i += config.batchSize) {
    const batch = firms.slice(i, i + config.batchSize);
    const batchStart = Date.now();

    try {
      const results = await agent.verifyBatch(batch);
      const batchEnd = Date.now();
      const batchLatency = batchEnd - batchStart;

      latencies.push(batchLatency / batch.length); // Average per firm

      // Count successes/failures
      results.forEach((result) => {
        if (result.status === 'CONFIRMED' || result.status === 'REJECTED' || result.status === 'SUSPENDED') {
          successful++;
        } else {
          failed++;
        }
      });

      // Progress update
      const progress = Math.round(((i + batch.length) / firms.length) * 100);
      console.log(`  Batch ${Math.floor(i / config.batchSize) + 1}: ${batch.length} firms in ${batchLatency}ms (${progress}%)`);
    } catch (error) {
      console.error(`  ❌ Batch failed:`, error);
      failed += batch.length;
    }
  }

  // Record end time
  const endTime = Date.now();
  const endMemory = process.memoryUsage();

  // Calculate metrics
  const totalDuration = endTime - startTime;
  const throughput = (firms.length / totalDuration) * 1000; // firms per second
  const averageLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;
  const minLatency = Math.min(...latencies);
  const maxLatency = Math.max(...latencies);

  // Get cache metrics if enabled
  let cacheMetrics;
  if (config.useCache) {
    const cache = getCache();
    const metrics = cache.getMetrics();
    cacheMetrics = {
      hits: metrics.hits,
      misses: metrics.misses,
      hitRate: metrics.hitRate,
    };
  }

  return {
    totalFirms: firms.length,
    totalDuration,
    throughput,
    averageLatency,
    minLatency,
    maxLatency,
    successful,
    failed,
    cacheMetrics,
    memoryUsage: {
      heapUsed: (endMemory.heapUsed - startMemory.heapUsed) / 1024 / 1024,
      heapTotal: endMemory.heapTotal / 1024 / 1024,
      external: endMemory.external / 1024 / 1024,
    },
  };
}

/**
 * Display results
 */
function displayResults(results: LoadTestResults) {
  console.log('\n📊 Load Test Results');
  console.log('='.repeat(60));

  // Performance metrics
  console.log('\n⚡ Performance:');
  console.log(`  Total Firms:     ${results.totalFirms}`);
  console.log(`  Total Duration:  ${results.totalDuration.toFixed(0)}ms (${(results.totalDuration / 1000).toFixed(2)}s)`);
  console.log(`  Throughput:      ${results.throughput.toFixed(2)} firms/second`);
  console.log(`  Avg Latency:     ${results.averageLatency.toFixed(2)}ms per firm`);
  console.log(`  Min Latency:     ${results.minLatency.toFixed(2)}ms`);
  console.log(`  Max Latency:     ${results.maxLatency.toFixed(2)}ms`);

  // Success/failure
  console.log('\n✅ Results:');
  console.log(`  Successful:      ${results.successful} (${((results.successful / results.totalFirms) * 100).toFixed(1)}%)`);
  console.log(`  Failed:          ${results.failed} (${((results.failed / results.totalFirms) * 100).toFixed(1)}%)`);

  // Cache metrics
  if (results.cacheMetrics) {
    console.log('\n💾 Cache:');
    console.log(`  Hits:            ${results.cacheMetrics.hits}`);
    console.log(`  Misses:          ${results.cacheMetrics.misses}`);
    console.log(`  Hit Rate:        ${results.cacheMetrics.hitRate.toFixed(2)}%`);
  }

  // Memory usage
  console.log('\n🧠 Memory:');
  console.log(`  Heap Used:       ${results.memoryUsage.heapUsed.toFixed(2)} MB`);
  console.log(`  Heap Total:      ${results.memoryUsage.heapTotal.toFixed(2)} MB`);
  console.log(`  External:        ${results.memoryUsage.external.toFixed(2)} MB`);

  // Target comparison
  console.log('\n🎯 Target Comparison:');
  const targetThroughput = 10; // 10 firms/sec
  const targetLatency = 500; // 500ms per firm
  const targetHitRate = 80; // 80% hit rate

  console.log(`  Throughput:      ${results.throughput >= targetThroughput ? '✅' : '❌'} ${results.throughput.toFixed(2)} / ${targetThroughput} (target)`);
  console.log(`  Latency:         ${results.averageLatency <= targetLatency ? '✅' : '❌'} ${results.averageLatency.toFixed(2)}ms / ${targetLatency}ms (target)`);
  if (results.cacheMetrics) {
    console.log(`  Cache Hit Rate:  ${results.cacheMetrics.hitRate >= targetHitRate ? '✅' : '❌'} ${results.cacheMetrics.hitRate.toFixed(2)}% / ${targetHitRate}% (target)`);
  }

  console.log('\n' + '='.repeat(60));
}

/**
 * Parse command line arguments
 */
function parseArgs(): LoadTestConfig {
  const args = process.argv.slice(2);
  const config: LoadTestConfig = {
    firmCount: 1000,
    useMock: true,
    useCache: true,
    batchSize: 10,
  };

  args.forEach((arg) => {
    const [key, value] = arg.replace('--', '').split('=');
    switch (key) {
      case 'firms':
        config.firmCount = parseInt(value);
        break;
      case 'mock':
        config.useMock = value === 'true';
        break;
      case 'cache':
        config.useCache = value === 'true';
        break;
      case 'batch':
        config.batchSize = parseInt(value);
        break;
    }
  });

  return config;
}

/**
 * Main execution
 */
async function main() {
  try {
    const config = parseArgs();
    const results = await runLoadTest(config);
    displayResults(results);

    // Cleanup
    if (config.useCache) {
      await closeCache();
    }

    // Exit with code based on success
    const passRate = (results.successful / results.totalFirms) * 100;
    if (passRate >= 95 && results.throughput >= 10) {
      console.log('\n✅ LOAD TEST PASSED\n');
      process.exit(0);
    } else {
      console.log('\n❌ LOAD TEST FAILED\n');
      process.exit(1);
    }
  } catch (error) {
    console.error('\n❌ Load test error:', error);
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  main();
}

export { runLoadTest, LoadTestConfig, LoadTestResults };
