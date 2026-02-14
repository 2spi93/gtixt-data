/**
 * PostgreSQL Database Client
 * Connection pool and query helpers for sanctions database
 */

import { Pool, PoolClient, QueryResult, QueryResultRow } from 'pg';

export interface DatabaseConfig {
  host?: string;
  port?: number;
  database?: string;
  user?: string;
  password?: string;
  max?: number; // Maximum pool size
  idleTimeoutMillis?: number;
  connectionTimeoutMillis?: number;
}

export interface SanctionsList {
  id: number;
  list_name: string;
  source_url: string;
  last_updated: Date;
  record_count: number;
  checksum: string;
  status: string;
}

export interface SanctionsEntity {
  id: number;
  list_id: number;
  entity_id: string;
  entity_type: string;
  primary_name: string;
  name_variants: string[];
  name_normalized: string;
  program: string;
  sanctions_list: string;
  nationality: string[];
  added_date: Date;
  raw_data: any;
}

export interface SanctionsMatch {
  id: number;
  search_name: string;
  search_type: string;
  entity_id: number;
  similarity_score: number;
  match_reason: string;
  screening_status: string;
  matched_at: Date;
}

export class DatabaseClient {
  private pool: Pool;
  private isConnected: boolean = false;

  constructor(config?: DatabaseConfig) {
    const defaultConfig: DatabaseConfig = {
      host: process.env.POSTGRES_HOST || 'localhost',
      port: parseInt(process.env.POSTGRES_PORT || '5432'),
      database: process.env.POSTGRES_DB || 'gpti_sanctions',
      user: process.env.POSTGRES_USER || 'postgres',
      password: process.env.POSTGRES_PASSWORD || '',
      max: 20, // Maximum 20 connections in pool
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 10000,
    };

    this.pool = new Pool({ ...defaultConfig, ...config });

    // Handle pool errors
    this.pool.on('error', (err) => {
      console.error('Unexpected error on idle PostgreSQL client', err);
    });

    // Test connection on initialization
    this.testConnection();
  }

  /**
   * Test database connection
   */
  private async testConnection(): Promise<void> {
    try {
      const client = await this.pool.connect();
      await client.query('SELECT NOW()');
      client.release();
      this.isConnected = true;
      console.log('PostgreSQL connected successfully');
    } catch (error) {
      console.error('PostgreSQL connection failed:', error);
      this.isConnected = false;
    }
  }

  /**
   * Execute a query
   */
  async query<T extends QueryResultRow = any>(
    text: string,
    params?: any[]
  ): Promise<QueryResult<T>> {
    const start = Date.now();
    try {
      const result = await this.pool.query<T>(text, params);
      const duration = Date.now() - start;
      
      if (duration > 1000) {
        console.warn(`Slow query (${duration}ms):`, text.substring(0, 100));
      }
      
      return result;
    } catch (error: any) {
      console.error('Query error:', error.message);
      console.error('Query:', text);
      throw error;
    }
  }

  /**
   * Get a client from pool (for transactions)
   */
  async getClient(): Promise<PoolClient> {
    return await this.pool.connect();
  }

  /**
   * Execute transaction
   */
  async transaction<T>(
    callback: (client: PoolClient) => Promise<T>
  ): Promise<T> {
    const client = await this.getClient();
    try {
      await client.query('BEGIN');
      const result = await callback(client);
      await client.query('COMMIT');
      return result;
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  /**
   * Get sanctions list by name
   */
  async getSanctionsList(listName: string): Promise<SanctionsList | null> {
    const result = await this.query<SanctionsList>(
      'SELECT * FROM sanctions_lists WHERE list_name = $1',
      [listName]
    );
    return result.rows[0] || null;
  }

  /**
   * Update sanctions list metadata
   */
  async updateSanctionsList(
    listName: string,
    data: { last_updated?: Date; record_count?: number; checksum?: string; status?: string }
  ): Promise<void> {
    const fields: string[] = [];
    const values: any[] = [];
    let paramIndex = 1;

    if (data.last_updated) {
      fields.push(`last_updated = $${paramIndex++}`);
      values.push(data.last_updated);
    }
    if (data.record_count !== undefined) {
      fields.push(`record_count = $${paramIndex++}`);
      values.push(data.record_count);
    }
    if (data.checksum) {
      fields.push(`checksum = $${paramIndex++}`);
      values.push(data.checksum);
    }
    if (data.status) {
      fields.push(`status = $${paramIndex++}`);
      values.push(data.status);
    }

    values.push(listName);

    await this.query(
      `UPDATE sanctions_lists SET ${fields.join(', ')} WHERE list_name = $${paramIndex}`,
      values
    );
  }

  /**
   * Insert sanctions entity
   */
  async insertEntity(entity: Omit<SanctionsEntity, 'id' | 'created_at' | 'updated_at'>): Promise<number> {
    const result = await this.query<{ id: number }>(
      `INSERT INTO sanctions_entities (
        list_id, entity_id, entity_type, primary_name, name_variants,
        name_normalized, program, sanctions_list, nationality, added_date, raw_data
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      ON CONFLICT (list_id, entity_id) 
      DO UPDATE SET
        primary_name = EXCLUDED.primary_name,
        name_variants = EXCLUDED.name_variants,
        name_normalized = EXCLUDED.name_normalized,
        program = EXCLUDED.program,
        raw_data = EXCLUDED.raw_data,
        updated_at = NOW()
      RETURNING id`,
      [
        entity.list_id,
        entity.entity_id,
        entity.entity_type,
        entity.primary_name,
        entity.name_variants,
        entity.name_normalized,
        entity.program,
        entity.sanctions_list,
        entity.nationality,
        entity.added_date,
        JSON.stringify(entity.raw_data),
      ]
    );
    return result.rows[0].id;
  }

  /**
   * Bulk insert entities (more efficient)
   */
  async bulkInsertEntities(entities: Omit<SanctionsEntity, 'id' | 'created_at' | 'updated_at'>[]): Promise<number> {
    if (entities.length === 0) return 0;

    const client = await this.getClient();
    try {
      await client.query('BEGIN');

      let inserted = 0;
      for (const entity of entities) {
        await client.query(
          `INSERT INTO sanctions_entities (
            list_id, entity_id, entity_type, primary_name, name_variants,
            name_normalized, program, sanctions_list, nationality, added_date, raw_data
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
          ON CONFLICT (list_id, entity_id) DO NOTHING`,
          [
            entity.list_id,
            entity.entity_id,
            entity.entity_type,
            entity.primary_name,
            entity.name_variants,
            entity.name_normalized,
            entity.program,
            entity.sanctions_list,
            entity.nationality,
            entity.added_date,
            JSON.stringify(entity.raw_data),
          ]
        );
        inserted++;
      }

      await client.query('COMMIT');
      return inserted;
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  /**
   * Search entities by name (exact match)
   */
  async searchExact(name: string): Promise<SanctionsEntity[]> {
    const normalized = this.normalizeName(name);
    const result = await this.query<SanctionsEntity>(
      'SELECT * FROM sanctions_entities WHERE name_normalized = $1',
      [normalized]
    );
    return result.rows;
  }

  /**
   * Search entities by name (fuzzy match using similarity)
   */
  async searchFuzzy(name: string, threshold: number = 0.7): Promise<SanctionsEntity[]> {
    const normalized = this.normalizeName(name);
    const result = await this.query<SanctionsEntity>(
      `SELECT *, similarity(name_normalized, $1) as sim
       FROM sanctions_entities
       WHERE similarity(name_normalized, $1) > $2
       ORDER BY sim DESC
       LIMIT 20`,
      [normalized, threshold]
    );
    return result.rows;
  }

  /**
   * Search entities using full-text search
   */
  async searchFullText(query: string): Promise<SanctionsEntity[]> {
    const result = await this.query<SanctionsEntity>(
      `SELECT *, ts_rank(to_tsvector('english', primary_name || ' ' || 
         COALESCE(array_to_string(name_variants, ' '), '')), 
         plainto_tsquery('english', $1)) as rank
       FROM sanctions_entities
       WHERE to_tsvector('english', primary_name || ' ' || 
         COALESCE(array_to_string(name_variants, ' '), '')) @@ 
         plainto_tsquery('english', $1)
       ORDER BY rank DESC
       LIMIT 20`,
      [query]
    );
    return result.rows;
  }

  /**
   * Record a screening match
   */
  async recordMatch(match: Omit<SanctionsMatch, 'id' | 'matched_at' | 'created_at'>): Promise<number> {
    const result = await this.query<{ id: number }>(
      `INSERT INTO sanctions_matches (
        search_name, search_type, entity_id, similarity_score,
        match_reason, screening_status, matched_by
      ) VALUES ($1, $2, $3, $4, $5, $6, $7)
      RETURNING id`,
      [
        match.search_name,
        match.search_type,
        match.entity_id,
        match.similarity_score,
        match.match_reason,
        match.screening_status,
        (match as any).matched_by || 'SSS_AGENT',
      ]
    );
    return result.rows[0].id;
  }

  /**
   * Get sanctions statistics
   */
  async getStatistics(): Promise<any> {
    const result = await this.query('SELECT * FROM sanctions_statistics');
    return result.rows;
  }

  /**
   * Clear all entities for a list (for reimport)
   */
  async clearList(listName: string): Promise<number> {
    const list = await this.getSanctionsList(listName);
    if (!list) return 0;

    const result = await this.query(
      'DELETE FROM sanctions_entities WHERE list_id = $1',
      [list.id]
    );
    return result.rowCount || 0;
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
   * Check if connected
   */
  isReady(): boolean {
    return this.isConnected;
  }

  /**
   * Get pool statistics
   */
  getPoolStats() {
    return {
      total: this.pool.totalCount,
      idle: this.pool.idleCount,
      waiting: this.pool.waitingCount,
    };
  }

  /**
   * Close all connections
   */
  async close(): Promise<void> {
    await this.pool.end();
    this.isConnected = false;
    console.log('PostgreSQL connections closed');
  }
}

// Singleton instance
let dbInstance: DatabaseClient | null = null;

/**
 * Get singleton database instance
 */
export function getDatabase(config?: DatabaseConfig): DatabaseClient {
  if (!dbInstance) {
    dbInstance = new DatabaseClient(config);
  }
  return dbInstance;
}

/**
 * Close database connection (for cleanup)
 */
export async function closeDatabase(): Promise<void> {
  if (dbInstance) {
    await dbInstance.close();
    dbInstance = null;
  }
}
