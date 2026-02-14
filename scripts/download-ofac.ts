/**
 * OFAC SDN List Downloader
 * Downloads and parses OFAC Specially Designated Nationals (SDN) list
 * Source: https://www.treasury.gov/ofac/downloads/sdn.csv
 */

import axios from 'axios';
import { parse } from 'csv-parse/sync';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { getDatabase, SanctionsEntity } from '../src/db/postgres-client';

const OFAC_SDN_URL = 'https://www.treasury.gov/ofac/downloads/sdn.csv';
const OFAC_DATA_DIR = path.join(__dirname, '../data/sanctions');

interface OFACRecord {
  ent_num: string; // Entity number (unique ID)
  sdn_name: string; // Full name
  sdn_type: string; // Individual, Entity, Vessel, Aircraft
  program: string; // Sanctions program
  title: string; // Title (for individuals)
  call_sign: string; // For vessels
  vess_type: string; // Vessel type
  tonnage: string;
  grt: string;
  vess_flag: string; // Vessel flag
  vess_owner: string;
  remarks: string; // Additional info
}

export class OFACDownloader {
  private db = getDatabase();

  /**
   * Download OFAC SDN CSV file
   */
  async download(): Promise<string> {
    console.log('Downloading OFAC SDN list...');
    
    try {
      const response = await axios.get(OFAC_SDN_URL, {
        timeout: 60000, // 60 seconds
        maxContentLength: 50 * 1024 * 1024, // 50MB max
      });

      // Ensure data directory exists
      if (!fs.existsSync(OFAC_DATA_DIR)) {
        fs.mkdirSync(OFAC_DATA_DIR, { recursive: true });
      }

      const filePath = path.join(OFAC_DATA_DIR, 'ofac_sdn.csv');
      fs.writeFileSync(filePath, response.data);

      console.log(`✓ Downloaded OFAC SDN list (${response.data.length} bytes)`);
      return filePath;
    } catch (error: any) {
      console.error('Failed to download OFAC SDN list:', error.message);
      throw error;
    }
  }

  /**
   * Parse CSV file
   */
  parseCSV(filePath: string): OFACRecord[] {
    console.log('Parsing OFAC CSV...');

    const fileContent = fs.readFileSync(filePath, 'utf-8');
    
    // Calculate checksum
    const checksum = crypto.createHash('sha256').update(fileContent).digest('hex');
    console.log(`File checksum: ${checksum.substring(0, 16)}...`);

    // Parse CSV
    const records = parse(fileContent, {
      columns: [
        'ent_num',
        'sdn_name',
        'sdn_type',
        'program',
        'title',
        'call_sign',
        'vess_type',
        'tonnage',
        'grt',
        'vess_flag',
        'vess_owner',
        'remarks',
      ],
      skip_empty_lines: true,
      trim: true,
      relax_column_count: true, // Handle variable column counts
    }) as OFACRecord[];

    console.log(`✓ Parsed ${records.length} OFAC records`);
    return records;
  }

  /**
   * Convert OFAC record to database entity
   */
  convertToEntity(listId: number, record: OFACRecord): Omit<SanctionsEntity, 'id' | 'created_at' | 'updated_at'> {
    // Normalize name
    const primaryName = record.sdn_name.trim();
    const nameNormalized = this.normalizeName(primaryName);

    // Extract name variants from remarks (often contains aliases)
    const nameVariants = this.extractAliases(record.remarks);

    // Determine entity type
    let entityType = 'entity';
    if (record.sdn_type) {
      const type = record.sdn_type.toLowerCase();
      if (type.includes('individual')) entityType = 'individual';
      else if (type.includes('vessel')) entityType = 'vessel';
      else if (type.includes('aircraft')) entityType = 'aircraft';
    }

    // Extract nationality from remarks or program
    const nationality: string[] = [];
    const nationMatch = record.remarks?.match(/nationality\s+([A-Z]{2,3})/i);
    if (nationMatch) nationality.push(nationMatch[1]);

    return {
      list_id: listId,
      entity_id: record.ent_num,
      entity_type: entityType,
      primary_name: primaryName,
      name_variants: nameVariants,
      name_normalized: nameNormalized,
      program: record.program || 'UNKNOWN',
      sanctions_list: 'SDN',
      nationality: nationality,
      added_date: new Date(), // OFAC CSV doesn't include dates, use current
      raw_data: record,
    };
  }

  /**
   * Extract aliases from remarks field
   */
  private extractAliases(remarks: string): string[] {
    if (!remarks) return [];

    const aliases: string[] = [];
    
    // Common patterns: "a.k.a.", "also known as", "f.k.a.", "formerly known as"
    const patterns = [
      /a\.k\.a\.\s+"([^"]+)"/gi,
      /also known as\s+"([^"]+)"/gi,
      /f\.k\.a\.\s+"([^"]+)"/gi,
      /formerly known as\s+"([^"]+)"/gi,
    ];

    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(remarks)) !== null) {
        aliases.push(match[1].trim());
      }
    }

    return [...new Set(aliases)]; // Remove duplicates
  }

  /**
   * Normalize name for matching
   */
  private normalizeName(name: string): string {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /**
   * Import to database
   */
  async importToDatabase(records: OFACRecord[]): Promise<number> {
    console.log('Importing OFAC records to database...');

    try {
      // Get or create list
      let list = await this.db.getSanctionsList('OFAC_SDN');
      if (!list) {
        throw new Error('OFAC_SDN list not found in database');
      }

      // Clear existing data
      const deleted = await this.db.clearList('OFAC_SDN');
      console.log(`Cleared ${deleted} existing OFAC records`);

      // Import in batches
      const batchSize = 1000;
      let imported = 0;

      for (let i = 0; i < records.length; i += batchSize) {
        const batch = records.slice(i, i + batchSize);
        const entities = batch.map((record) => this.convertToEntity(list!.id, record));
        
        await this.db.bulkInsertEntities(entities);
        imported += batch.length;

        if (imported % 5000 === 0) {
          console.log(`Imported ${imported}/${records.length} records...`);
        }
      }

      // Update list metadata
      await this.db.updateSanctionsList('OFAC_SDN', {
        last_updated: new Date(),
        record_count: imported,
        status: 'active',
      });

      console.log(`✓ Successfully imported ${imported} OFAC records`);
      return imported;
    } catch (error: any) {
      console.error('Failed to import OFAC data:', error.message);
      throw error;
    }
  }

  /**
   * Full download and import pipeline
   */
  async run(): Promise<void> {
    console.log('=== OFAC SDN Download & Import ===\n');

    const startTime = Date.now();

    try {
      // 1. Download
      const filePath = await this.download();

      // 2. Parse
      const records = this.parseCSV(filePath);

      // 3. Import
      const imported = await this.importToDatabase(records);

      const duration = Date.now() - startTime;
      console.log(`\n✓ OFAC import complete in ${(duration / 1000).toFixed(2)}s`);
      console.log(`  Total records: ${imported}`);

      // 4. Statistics
      const stats = await this.db.getStatistics();
      console.log('\nSanctions Statistics:');
      console.log(JSON.stringify(stats, null, 2));
    } catch (error: any) {
      console.error('\n✗ OFAC import failed:', error.message);
      throw error;
    }
  }
}

// Run if called directly
if (require.main === module) {
  const downloader = new OFACDownloader();
  downloader
    .run()
    .then(() => {
      console.log('\n✓ OFAC download complete');
      process.exit(0);
    })
    .catch((error) => {
      console.error('\n✗ OFAC download failed:', error);
      process.exit(1);
    });
}
