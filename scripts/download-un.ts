/**
 * UN Consolidated Sanctions List Downloader
 * Downloads and parses UN Security Council Consolidated Sanctions List
 * Source: https://scsanctions.un.org/resources/xml/en/consolidated.xml
 */

import axios from 'axios';
import * as xml2js from 'xml2js';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { getDatabase, SanctionsEntity } from '../src/db/postgres-client';

const UN_SANCTIONS_URL = 'https://scsanctions.un.org/resources/xml/en/consolidated.xml';
const UN_DATA_DIR = path.join(__dirname, '../data/sanctions');

interface UNIndividual {
  DATAID: string[];
  FIRST_NAME?: string[];
  SECOND_NAME?: string[];
  THIRD_NAME?: string[];
  FOURTH_NAME?: string[];
  UN_LIST_TYPE?: string[];
  REFERENCE_NUMBER?: string[];
  LISTED_ON?: string[];
  NAME_ORIGINAL_SCRIPT?: string[];
  COMMENTS1?: string[];
  DESIGNATION?: { VALUE?: string[] }[];
  NATIONALITY?: { VALUE?: string[] }[];
  LIST_TYPE?: { VALUE?: string[] }[];
  INDIVIDUAL_ALIAS?: Array<{
    QUALITY?: string[];
    ALIAS_NAME?: string[];
    DATE_OF_BIRTH?: string[];
    CITY_OF_BIRTH?: string[];
    COUNTRY_OF_BIRTH?: string[];
    NOTE?: string[];
  }>;
  INDIVIDUAL_ADDRESS?: Array<{
    STREET?: string[];
    CITY?: string[];
    STATE_PROVINCE?: string[];
    COUNTRY?: string[];
    NOTE?: string[];
  }>;
  INDIVIDUAL_DATE_OF_BIRTH?: Array<{
    TYPE_OF_DATE?: string[];
    DATE?: string[];
    YEAR?: string[];
    NOTE?: string[];
  }>;
  INDIVIDUAL_PLACE_OF_BIRTH?: Array<{
    CITY?: string[];
    STATE_PROVINCE?: string[];
    COUNTRY?: string[];
    NOTE?: string[];
  }>;
  INDIVIDUAL_DOCUMENT?: Array<{
    TYPE_OF_DOCUMENT?: string[];
    NUMBER?: string[];
    ISSUING_COUNTRY?: string[];
    DATE_OF_ISSUE?: string[];
    NOTE?: string[];
  }>;
}

interface UNEntity {
  DATAID: string[];
  FIRST_NAME: string[];
  UN_LIST_TYPE?: string[];
  REFERENCE_NUMBER?: string[];
  LISTED_ON?: string[];
  NAME_ORIGINAL_SCRIPT?: string[];
  COMMENTS1?: string[];
  ENTITY_ALIAS?: Array<{
    QUALITY?: string[];
    ALIAS_NAME?: string[];
    DATE_OF_BIRTH?: string[];
    CITY_OF_BIRTH?: string[];
    COUNTRY_OF_BIRTH?: string[];
    NOTE?: string[];
  }>;
  ENTITY_ADDRESS?: Array<{
    STREET?: string[];
    CITY?: string[];
    STATE_PROVINCE?: string[];
    ZIP_CODE?: string[];
    COUNTRY?: string[];
    NOTE?: string[];
  }>;
}

interface UNData {
  CONSOLIDATED_LIST?: {
    INDIVIDUALS?: Array<{ INDIVIDUAL?: UNIndividual[] }>;
    ENTITIES?: Array<{ ENTITY?: UNEntity[] }>;
  };
}

export class UNDownloader {
  private db = getDatabase();

  /**
   * Download UN XML file
   */
  async download(): Promise<string> {
    console.log('Downloading UN Consolidated Sanctions List...');

    try {
      const response = await axios.get(UN_SANCTIONS_URL, {
        timeout: 120000, // 120 seconds (larger file)
        maxContentLength: 100 * 1024 * 1024, // 100MB max
        headers: {
          'Accept': 'application/xml',
        },
      });

      // Ensure data directory exists
      if (!fs.existsSync(UN_DATA_DIR)) {
        fs.mkdirSync(UN_DATA_DIR, { recursive: true });
      }

      const filePath = path.join(UN_DATA_DIR, 'un_consolidated.xml');
      fs.writeFileSync(filePath, response.data);

      console.log(`✓ Downloaded UN list (${response.data.length} bytes)`);
      return filePath;
    } catch (error: any) {
      console.error('Failed to download UN list:', error.message);
      throw error;
    }
  }

  /**
   * Parse XML file
   */
  async parseXML(filePath: string): Promise<UNData> {
    console.log('Parsing UN XML...');

    const fileContent = fs.readFileSync(filePath, 'utf-8');

    // Calculate checksum
    const checksum = crypto.createHash('sha256').update(fileContent).digest('hex');
    console.log(`File checksum: ${checksum.substring(0, 16)}...`);

    // Parse XML
    const parser = new xml2js.Parser({
      explicitArray: true,
      trim: true,
    });

    const result = await parser.parseStringPromise(fileContent);
    console.log(`✓ Parsed UN XML successfully`);

    return result as UNData;
  }

  /**
   * Extract individuals from UN data
   */
  extractIndividuals(data: UNData): UNIndividual[] {
    const individuals: UNIndividual[] = [];

    if (data.CONSOLIDATED_LIST?.INDIVIDUALS) {
      for (const individualGroup of data.CONSOLIDATED_LIST.INDIVIDUALS) {
        if (individualGroup.INDIVIDUAL) {
          individuals.push(...individualGroup.INDIVIDUAL);
        }
      }
    }

    console.log(`✓ Extracted ${individuals.length} individuals`);
    return individuals;
  }

  /**
   * Extract entities from UN data
   */
  extractEntities(data: UNData): UNEntity[] {
    const entities: UNEntity[] = [];

    if (data.CONSOLIDATED_LIST?.ENTITIES) {
      for (const entityGroup of data.CONSOLIDATED_LIST.ENTITIES) {
        if (entityGroup.ENTITY) {
          entities.push(...entityGroup.ENTITY);
        }
      }
    }

    console.log(`✓ Extracted ${entities.length} entities`);
    return entities;
  }

  /**
   * Convert UN individual to database entity
   */
  convertIndividual(listId: number, individual: UNIndividual): Omit<SanctionsEntity, 'id' | 'created_at' | 'updated_at'> {
    // Build full name
    const nameParts = [
      individual.FIRST_NAME?.[0],
      individual.SECOND_NAME?.[0],
      individual.THIRD_NAME?.[0],
      individual.FOURTH_NAME?.[0],
    ].filter(Boolean);
    const primaryName = nameParts.join(' ').trim() || 'UNKNOWN';

    // Extract aliases
    const nameVariants: string[] = [];
    if (individual.INDIVIDUAL_ALIAS) {
      for (const alias of individual.INDIVIDUAL_ALIAS) {
        if (alias.ALIAS_NAME?.[0]) {
          nameVariants.push(alias.ALIAS_NAME[0]);
        }
      }
    }
    if (individual.NAME_ORIGINAL_SCRIPT?.[0]) {
      nameVariants.push(individual.NAME_ORIGINAL_SCRIPT[0]);
    }

    // Extract nationality
    const nationality: string[] = [];
    if (individual.NATIONALITY) {
      for (const nat of individual.NATIONALITY) {
        if (nat.VALUE?.[0]) {
          nationality.push(nat.VALUE[0]);
        }
      }
    }

    // Get list type (AL-QAIDA, ISIL, Taliban, etc.)
    const listType = individual.UN_LIST_TYPE?.[0] || individual.LIST_TYPE?.[0]?.VALUE?.[0] || 'UNKNOWN';

    // Parse date
    let listedDate = new Date();
    if (individual.LISTED_ON?.[0]) {
      try {
        listedDate = new Date(individual.LISTED_ON[0]);
      } catch (e) {
        // Keep default
      }
    }

    return {
      list_id: listId,
      entity_id: individual.REFERENCE_NUMBER?.[0] || individual.DATAID[0],
      entity_type: 'individual',
      primary_name: primaryName,
      name_variants: [...new Set(nameVariants)],
      name_normalized: this.normalizeName(primaryName),
      program: listType,
      sanctions_list: 'UN_CONSOLIDATED',
      nationality: nationality,
      added_date: listedDate,
      raw_data: individual,
    };
  }

  /**
   * Convert UN entity to database entity
   */
  convertEntity(listId: number, entity: UNEntity): Omit<SanctionsEntity, 'id' | 'created_at' | 'updated_at'> {
    const primaryName = entity.FIRST_NAME[0] || 'UNKNOWN';

    // Extract aliases
    const nameVariants: string[] = [];
    if (entity.ENTITY_ALIAS) {
      for (const alias of entity.ENTITY_ALIAS) {
        if (alias.ALIAS_NAME?.[0]) {
          nameVariants.push(alias.ALIAS_NAME[0]);
        }
      }
    }
    if (entity.NAME_ORIGINAL_SCRIPT?.[0]) {
      nameVariants.push(entity.NAME_ORIGINAL_SCRIPT[0]);
    }

    // Get list type
    const listType = entity.UN_LIST_TYPE?.[0] || 'UNKNOWN';

    // Parse date
    let listedDate = new Date();
    if (entity.LISTED_ON?.[0]) {
      try {
        listedDate = new Date(entity.LISTED_ON[0]);
      } catch (e) {
        // Keep default
      }
    }

    return {
      list_id: listId,
      entity_id: entity.REFERENCE_NUMBER?.[0] || entity.DATAID[0],
      entity_type: 'entity',
      primary_name: primaryName,
      name_variants: [...new Set(nameVariants)],
      name_normalized: this.normalizeName(primaryName),
      program: listType,
      sanctions_list: 'UN_CONSOLIDATED',
      nationality: [],
      added_date: listedDate,
      raw_data: entity,
    };
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
  async importToDatabase(individuals: UNIndividual[], entities: UNEntity[]): Promise<number> {
    console.log('Importing UN records to database...');

    try {
      // Get or create list
      let list = await this.db.getSanctionsList('UN_CONSOLIDATED');
      if (!list) {
        throw new Error('UN_CONSOLIDATED list not found in database');
      }

      // Clear existing data
      const deleted = await this.db.clearList('UN_CONSOLIDATED');
      console.log(`Cleared ${deleted} existing UN records`);

      // Convert individuals
      console.log('Converting individuals...');
      const individualEntities = individuals.map((ind) => this.convertIndividual(list!.id, ind));

      // Convert entities
      console.log('Converting entities...');
      const entityEntities = entities.map((ent) => this.convertEntity(list!.id, ent));

      // Combine all
      const allEntities = [...individualEntities, ...entityEntities];

      // Import in batches
      const batchSize = 1000;
      let imported = 0;

      for (let i = 0; i < allEntities.length; i += batchSize) {
        const batch = allEntities.slice(i, i + batchSize);
        await this.db.bulkInsertEntities(batch);
        imported += batch.length;

        if (imported % 5000 === 0) {
          console.log(`Imported ${imported}/${allEntities.length} records...`);
        }
      }

      // Update list metadata
      await this.db.updateSanctionsList('UN_CONSOLIDATED', {
        last_updated: new Date(),
        record_count: imported,
        status: 'active',
      });

      console.log(`✓ Successfully imported ${imported} UN records`);
      return imported;
    } catch (error: any) {
      console.error('Failed to import UN data:', error.message);
      throw error;
    }
  }

  /**
   * Full download and import pipeline
   */
  async run(): Promise<void> {
    console.log('=== UN Consolidated Sanctions Download & Import ===\n');

    const startTime = Date.now();

    try {
      // 1. Download
      const filePath = await this.download();

      // 2. Parse
      const data = await this.parseXML(filePath);

      // 3. Extract
      const individuals = this.extractIndividuals(data);
      const entities = this.extractEntities(data);

      // 4. Import
      const imported = await this.importToDatabase(individuals, entities);

      const duration = Date.now() - startTime;
      console.log(`\n✓ UN import complete in ${(duration / 1000).toFixed(2)}s`);
      console.log(`  Total records: ${imported}`);
      console.log(`  Individuals: ${individuals.length}`);
      console.log(`  Entities: ${entities.length}`);

      // 5. Statistics
      const stats = await this.db.getStatistics();
      console.log('\nSanctions Statistics:');
      console.log(JSON.stringify(stats, null, 2));
    } catch (error: any) {
      console.error('\n✗ UN import failed:', error.message);
      throw error;
    }
  }
}

// Run if called directly
if (require.main === module) {
  const downloader = new UNDownloader();
  downloader
    .run()
    .then(() => {
      console.log('\n✓ UN download complete');
      process.exit(0);
    })
    .catch((error) => {
      console.error('\n✗ UN download failed:', error);
      process.exit(1);
    });
}
