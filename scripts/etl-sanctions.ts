/**
 * ETL Pipeline for Sanctions Data
 * Orchestrates download, parse, transform, and load of OFAC and UN sanctions
 */

import { OFACDownloader } from './download-ofac';
import { UNDownloader } from './download-un';
import { getDatabase, closeDatabase } from '../src/db/postgres-client';
import * as fs from 'fs';
import * as path from 'path';

export interface ETLConfig {
  sources: ('ofac' | 'un')[];
  force?: boolean; // Force update even if recent
  updateIntervalHours?: number; // Don't update if last update within this many hours
}

export interface ETLResult {
  source: 'ofac' | 'un';
  success: boolean;
  recordsImported: number;
  duration: number;
  error?: string;
}

export interface ETLReport {
  startTime: Date;
  endTime: Date;
  totalDuration: number;
  results: ETLResult[];
  totalRecords: number;
  successCount: number;
  failureCount: number;
}

export class SanctionsETL {
  private config: ETLConfig;
  private db = getDatabase();

  constructor(config?: Partial<ETLConfig>) {
    this.config = {
      sources: ['ofac', 'un'],
      force: false,
      updateIntervalHours: 24, // Default: update once per day
      ...config,
    };
  }

  /**
   * Run ETL pipeline
   */
  async run(): Promise<ETLReport> {
    console.log('=== Sanctions Data ETL Pipeline ===\n');
    console.log(`Sources: ${this.config.sources.join(', ')}`);
    console.log(`Force update: ${this.config.force}`);
    console.log(`Update interval: ${this.config.updateIntervalHours} hours\n`);

    const startTime = new Date();
    const results: ETLResult[] = [];

    try {
      // Check database connection
      if (!this.db.isReady()) {
        throw new Error('Database not connected');
      }

      // Process each source
      for (const source of this.config.sources) {
        const result = await this.processSource(source);
        results.push(result);
      }

      const endTime = new Date();
      const totalDuration = endTime.getTime() - startTime.getTime();

      const report: ETLReport = {
        startTime,
        endTime,
        totalDuration,
        results,
        totalRecords: results.reduce((sum, r) => sum + r.recordsImported, 0),
        successCount: results.filter((r) => r.success).length,
        failureCount: results.filter((r) => !r.success).length,
      };

      // Print report
      this.printReport(report);

      // Save report
      await this.saveReport(report);

      return report;
    } catch (error: any) {
      console.error('\n✗ ETL pipeline failed:', error.message);
      throw error;
    }
  }

  /**
   * Process a single source
   */
  private async processSource(source: 'ofac' | 'un'): Promise<ETLResult> {
    console.log(`\n--- Processing ${source.toUpperCase()} ---`);
    const startTime = Date.now();

    try {
      // Check if update needed
      if (!this.config.force && !(await this.needsUpdate(source))) {
        console.log(`✓ ${source.toUpperCase()} data is up to date, skipping`);
        return {
          source,
          success: true,
          recordsImported: 0,
          duration: Date.now() - startTime,
        };
      }

      // Run downloader
      let recordsImported = 0;
      if (source === 'ofac') {
        const downloader = new OFACDownloader();
        await downloader.run();
        const list = await this.db.getSanctionsList('OFAC_SDN');
        recordsImported = list?.record_count || 0;
      } else if (source === 'un') {
        const downloader = new UNDownloader();
        await downloader.run();
        const list = await this.db.getSanctionsList('UN_CONSOLIDATED');
        recordsImported = list?.record_count || 0;
      }

      const duration = Date.now() - startTime;
      console.log(`✓ ${source.toUpperCase()} processed in ${(duration / 1000).toFixed(2)}s`);

      return {
        source,
        success: true,
        recordsImported,
        duration,
      };
    } catch (error: any) {
      const duration = Date.now() - startTime;
      console.error(`✗ ${source.toUpperCase()} failed:`, error.message);

      return {
        source,
        success: false,
        recordsImported: 0,
        duration,
        error: error.message,
      };
    }
  }

  /**
   * Check if source needs update
   */
  private async needsUpdate(source: 'ofac' | 'un'): Promise<boolean> {
    const listName = source === 'ofac' ? 'OFAC_SDN' : 'UN_CONSOLIDATED';
    const list = await this.db.getSanctionsList(listName);

    if (!list || !list.last_updated) {
      return true; // No data yet
    }

    const hoursSinceUpdate =
      (Date.now() - list.last_updated.getTime()) / (1000 * 60 * 60);

    return hoursSinceUpdate >= (this.config.updateIntervalHours || 24);
  }

  /**
   * Print ETL report
   */
  private printReport(report: ETLReport): void {
    console.log('\n=== ETL Pipeline Report ===');
    console.log(`Start time: ${report.startTime.toISOString()}`);
    console.log(`End time: ${report.endTime.toISOString()}`);
    console.log(`Total duration: ${(report.totalDuration / 1000).toFixed(2)}s`);
    console.log(`Total records: ${report.totalRecords.toLocaleString()}`);
    console.log(`Success: ${report.successCount}/${report.results.length}`);
    console.log(`Failures: ${report.failureCount}/${report.results.length}`);

    console.log('\nResults by source:');
    for (const result of report.results) {
      const status = result.success ? '✓' : '✗';
      console.log(
        `  ${status} ${result.source.toUpperCase()}: ${result.recordsImported.toLocaleString()} records in ${(
          result.duration / 1000
        ).toFixed(2)}s`
      );
      if (result.error) {
        console.log(`    Error: ${result.error}`);
      }
    }

    // Get statistics
    this.db
      .getStatistics()
      .then((stats) => {
        console.log('\nSanctions Database Statistics:');
        for (const stat of stats) {
          console.log(`  ${stat.list_name}:`);
          console.log(`    Total entities: ${stat.total_entities || 0}`);
          console.log(`    Individuals: ${stat.individuals || 0}`);
          console.log(`    Entities: ${stat.entities || 0}`);
          console.log(`    Programs: ${stat.programs || 0}`);
          console.log(
            `    Last updated: ${stat.last_updated ? new Date(stat.last_updated).toISOString() : 'Never'}`
          );
        }
      })
      .catch((error) => {
        console.error('Failed to get statistics:', error.message);
      });
  }

  /**
   * Save ETL report to file
   */
  private async saveReport(report: ETLReport): Promise<void> {
    const reportsDir = path.join(__dirname, '../data/reports');
    if (!fs.existsSync(reportsDir)) {
      fs.mkdirSync(reportsDir, { recursive: true });
    }

    const timestamp = report.startTime.toISOString().replace(/:/g, '-').replace(/\..+/, '');
    const filename = `etl-report-${timestamp}.json`;
    const filepath = path.join(reportsDir, filename);

    fs.writeFileSync(filepath, JSON.stringify(report, null, 2));
    console.log(`\n✓ Report saved to: ${filepath}`);
  }
}

/**
 * CLI entry point
 */
async function main() {
  const args = process.argv.slice(2);

  // Parse arguments
  const config: Partial<ETLConfig> = {};

  if (args.includes('--ofac-only')) {
    config.sources = ['ofac'];
  } else if (args.includes('--un-only')) {
    config.sources = ['un'];
  }

  if (args.includes('--force')) {
    config.force = true;
  }

  const intervalIndex = args.indexOf('--interval');
  if (intervalIndex >= 0 && args[intervalIndex + 1]) {
    config.updateIntervalHours = parseInt(args[intervalIndex + 1]);
  }

  // Run ETL
  const etl = new SanctionsETL(config);
  try {
    await etl.run();
    await closeDatabase();
    console.log('\n✓ ETL pipeline complete');
    process.exit(0);
  } catch (error: any) {
    console.error('\n✗ ETL pipeline failed:', error.message);
    await closeDatabase();
    process.exit(1);
  }
}

// Run if called directly
if (require.main === module) {
  main();
}

export default SanctionsETL;
