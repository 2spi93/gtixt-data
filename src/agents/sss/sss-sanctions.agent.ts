/**
 * SSS Agent - Sanctions Screening Service
 * Screens entities against OFAC and UN sanctions lists
 * Uses exact, fuzzy, and phonetic matching
 */

import { getDatabase, SanctionsEntity, DatabaseClient } from '../../db/postgres-client';
import { stringSimilarity, levenshteinDistance, soundex } from '../../utils/string-similarity';

export interface ScreeningRequest {
  name: string;
  entityType?: 'individual' | 'entity' | 'all';
  threshold?: number; // Fuzzy match threshold (0-1)
  includeAliases?: boolean; // Search name variants
  matchTypes?: ('exact' | 'fuzzy' | 'phonetic')[];
}

export interface ScreeningMatch {
  entity: SanctionsEntity;
  matchType: 'exact' | 'fuzzy' | 'phonetic' | 'alias';
  matchedName: string; // Which name matched (primary or alias)
  similarityScore: number; // 0-1
  confidence: 'high' | 'medium' | 'low';
  reason: string;
}

export interface ScreeningResult {
  request: ScreeningRequest;
  status: 'CLEAR' | 'SANCTIONED' | 'POTENTIAL_MATCH' | 'REVIEW_REQUIRED';
  matches: ScreeningMatch[];
  screenedAt: Date;
  duration: number; // milliseconds
  metadata: {
    exact_matches: number;
    fuzzy_matches: number;
    phonetic_matches: number;
    alias_matches: number;
    total_entities_checked: number;
  };
}

export interface BatchScreeningResult {
  requests: ScreeningRequest[];
  results: ScreeningResult[];
  totalDuration: number;
  averageDuration: number;
}

export class SSSAgent {
  private db: DatabaseClient;
  private defaultThreshold: number = 0.85; // Higher threshold for sanctions
  private phoneticThreshold: number = 0.90; // Even higher for phonetic

  constructor(db?: DatabaseClient) {
    this.db = db || getDatabase();
  }

  /**
   * Screen a single entity
   */
  async screen(request: ScreeningRequest): Promise<ScreeningResult> {
    const startTime = Date.now();

    // Set defaults
    const threshold = request.threshold || this.defaultThreshold;
    const includeAliases = request.includeAliases !== false;
    const matchTypes = request.matchTypes || ['exact', 'fuzzy', 'phonetic'];

    const matches: ScreeningMatch[] = [];
    const metadata = {
      exact_matches: 0,
      fuzzy_matches: 0,
      phonetic_matches: 0,
      alias_matches: 0,
      total_entities_checked: 0,
    };

    try {
      // 1. Exact match
      if (matchTypes.includes('exact')) {
        const exactMatches = await this.exactMatch(request.name);
        for (const entity of exactMatches) {
          matches.push({
            entity,
            matchType: 'exact',
            matchedName: entity.primary_name,
            similarityScore: 1.0,
            confidence: 'high',
            reason: 'Exact name match',
          });
          metadata.exact_matches++;
        }
        metadata.total_entities_checked += exactMatches.length;
      }

      // 2. Alias match (if enabled and no exact match)
      if (includeAliases && matches.length === 0) {
        const aliasMatches = await this.aliasMatch(request.name);
        for (const entity of aliasMatches) {
          const matchedAlias = this.findMatchingAlias(request.name, entity);
          if (matchedAlias) {
            matches.push({
              entity,
              matchType: 'alias',
              matchedName: matchedAlias,
              similarityScore: 1.0,
              confidence: 'high',
              reason: 'Alias match',
            });
            metadata.alias_matches++;
          }
        }
      }

      // 3. Fuzzy match (if no exact/alias match)
      if (matchTypes.includes('fuzzy') && matches.length === 0) {
        const fuzzyMatches = await this.fuzzyMatch(request.name, threshold);
        for (const entity of fuzzyMatches) {
          const score = stringSimilarity(
            this.normalizeName(request.name),
            entity.name_normalized
          );
          
          if (score >= threshold) {
            matches.push({
              entity,
              matchType: 'fuzzy',
              matchedName: entity.primary_name,
              similarityScore: score,
              confidence: this.getConfidenceLevel(score),
              reason: `Fuzzy match (${(score * 100).toFixed(1)}% similarity)`,
            });
            metadata.fuzzy_matches++;
          }
        }
        metadata.total_entities_checked += fuzzyMatches.length;
      }

      // 4. Phonetic match (if enabled and no strong match)
      if (matchTypes.includes('phonetic') && matches.length === 0) {
        const phoneticMatches = await this.phoneticMatch(request.name);
        for (const entity of phoneticMatches) {
          const score = stringSimilarity(
            this.normalizeName(request.name),
            entity.name_normalized
          );
          
          if (score >= this.phoneticThreshold * threshold) {
            matches.push({
              entity,
              matchType: 'phonetic',
              matchedName: entity.primary_name,
              similarityScore: score,
              confidence: this.getConfidenceLevel(score),
              reason: `Phonetic match (sounds similar)`,
            });
            metadata.phonetic_matches++;
          }
        }
        metadata.total_entities_checked += phoneticMatches.length;
      }

      // Sort matches by confidence and score
      matches.sort((a, b) => {
        if (a.confidence !== b.confidence) {
          const confidenceOrder = { high: 3, medium: 2, low: 1 };
          return confidenceOrder[b.confidence] - confidenceOrder[a.confidence];
        }
        return b.similarityScore - a.similarityScore;
      });

      // Determine status
      const status = this.determineStatus(matches);

      // Record matches in database
      for (const match of matches) {
        await this.db.recordMatch({
          search_name: request.name,
          search_type: match.matchType,
          entity_id: match.entity.id,
          similarity_score: match.similarityScore,
          match_reason: match.reason,
          screening_status: status,
        });
      }

      const duration = Date.now() - startTime;

      return {
        request,
        status,
        matches,
        screenedAt: new Date(),
        duration,
        metadata,
      };
    } catch (error: any) {
      console.error('Screening error:', error.message);
      throw error;
    }
  }

  /**
   * Screen multiple entities in batch
   */
  async screenBatch(requests: ScreeningRequest[]): Promise<BatchScreeningResult> {
    const startTime = Date.now();
    const results: ScreeningResult[] = [];

    for (const request of requests) {
      const result = await this.screen(request);
      results.push(result);
    }

    const rawDuration = Date.now() - startTime;
    const totalDuration = requests.length > 0 ? Math.max(1, rawDuration) : 0;
    const averageDuration = requests.length > 0 ? totalDuration / requests.length : 0;

    return {
      requests,
      results,
      totalDuration,
      averageDuration,
    };
  }

  /**
   * Exact name match
   */
  private async exactMatch(name: string): Promise<SanctionsEntity[]> {
    return await this.db.searchExact(name);
  }

  /**
   * Alias match (search in name_variants array)
   */
  private async aliasMatch(name: string): Promise<SanctionsEntity[]> {
    const normalized = this.normalizeName(name);
    const result = await this.db.query<SanctionsEntity>(
      `SELECT * FROM sanctions_entities
       WHERE $1 = ANY(name_variants)
       OR name_normalized = $2
       LIMIT 20`,
      [name, normalized]
    );
    return result.rows;
  }

  /**
   * Fuzzy match using similarity
   */
  private async fuzzyMatch(name: string, threshold: number): Promise<SanctionsEntity[]> {
    // Use PostgreSQL's pg_trgm extension if available, otherwise fallback
    try {
      return await this.db.searchFuzzy(name, threshold);
    } catch (error) {
      // Fallback to manual fuzzy matching
      return await this.manualFuzzyMatch(name, threshold);
    }
  }

  /**
   * Manual fuzzy matching (fallback)
   */
  private async manualFuzzyMatch(name: string, threshold: number): Promise<SanctionsEntity[]> {
    const normalized = this.normalizeName(name);
    const result = await this.db.query<SanctionsEntity>(
      `SELECT * FROM sanctions_entities
       WHERE name_normalized ILIKE $1
       LIMIT 100`,
      [`%${normalized.split(' ')[0]}%`] // Search first word
    );

    // Filter by similarity
    return result.rows.filter((entity) => {
      const score = stringSimilarity(normalized, entity.name_normalized);
      return score >= threshold;
    });
  }

  /**
   * Phonetic match using Soundex
   */
  private async phoneticMatch(name: string): Promise<SanctionsEntity[]> {
    const nameSoundex = soundex(name);
    
    // Get candidates based on first word
    const normalized = this.normalizeName(name);
    const firstWord = normalized.split(' ')[0];
    
    const result = await this.db.query<SanctionsEntity>(
      `SELECT * FROM sanctions_entities
       WHERE name_normalized ILIKE $1
       LIMIT 200`,
      [`%${firstWord}%`]
    );

    // Filter by Soundex similarity
    return result.rows.filter((entity) => {
      const entitySoundex = soundex(entity.primary_name);
      return nameSoundex === entitySoundex;
    });
  }

  /**
   * Find which alias matched
   */
  private findMatchingAlias(searchName: string, entity: SanctionsEntity): string | null {
    const normalized = this.normalizeName(searchName);
    
    if (entity.name_normalized === normalized) {
      return entity.primary_name;
    }

    for (const alias of entity.name_variants || []) {
      if (this.normalizeName(alias) === normalized) {
        return alias;
      }
    }

    return null;
  }

  /**
   * Get confidence level based on similarity score
   */
  private getConfidenceLevel(score: number): 'high' | 'medium' | 'low' {
    if (score >= 0.95) return 'high';
    if (score >= 0.85) return 'medium';
    return 'low';
  }

  /**
   * Determine overall screening status
   */
  private determineStatus(matches: ScreeningMatch[]): 'CLEAR' | 'SANCTIONED' | 'POTENTIAL_MATCH' | 'REVIEW_REQUIRED' {
    if (matches.length === 0) {
      return 'CLEAR';
    }

    // Any high confidence match = SANCTIONED
    const hasHighConfidence = matches.some((m) => m.confidence === 'high');
    if (hasHighConfidence) {
      return 'SANCTIONED';
    }

    // Medium confidence = REVIEW_REQUIRED
    const hasMediumConfidence = matches.some((m) => m.confidence === 'medium');
    if (hasMediumConfidence) {
      return 'REVIEW_REQUIRED';
    }

    // Low confidence = POTENTIAL_MATCH
    return 'POTENTIAL_MATCH';
  }

  /**
   * Normalize name for matching
   */
  private normalizeName(name: string): string {
    return name
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9\s]/g, ' ')
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim();
  }

  /**
   * Get screening statistics
   */
  async getStatistics(): Promise<any> {
    const stats = await this.db.getStatistics();
    
    const matchStats = await this.db.query(
      `SELECT 
        screening_status,
        COUNT(*) as count,
        COUNT(DISTINCT search_name) as unique_searches,
        AVG(similarity_score) as avg_score
       FROM sanctions_matches
       GROUP BY screening_status`
    );

    return {
      sanctions_lists: stats,
      screening_results: matchStats.rows,
    };
  }

  /**
   * Get recent screenings
   */
  async getRecentScreenings(limit: number = 100): Promise<any[]> {
    const result = await this.db.query(
      `SELECT 
        m.*,
        e.primary_name,
        e.entity_type,
        e.program,
        e.sanctions_list
       FROM sanctions_matches m
       JOIN sanctions_entities e ON m.entity_id = e.id
       ORDER BY m.matched_at DESC
       LIMIT $1`,
      [limit]
    );
    return result.rows;
  }
}

// Export singleton instance
let sssAgentInstance: SSSAgent | null = null;

export function getSSSAgent(db?: DatabaseClient): SSSAgent {
  if (!sssAgentInstance) {
    sssAgentInstance = new SSSAgent(db);
  }
  return sssAgentInstance;
}
