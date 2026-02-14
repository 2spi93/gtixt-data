/**
 * REM Agent - Regulatory Event Monitor
 * Monitors regulatory news, SEC filings, and enforcement actions
 */

import { Agent, AgentContext } from '../../types/agent';
import { Firm } from '../../types/firm';
import axios from 'axios';

export interface RegulatoryEventEvidence {
  evidence_type: 'REGULATORY_EVENT';
  firm_id: string;
  firm_name: string;
  event_type: 'ENFORCEMENT' | 'WARNING' | 'NEWS' | 'FILING';
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  source: string;
  title: string;
  description?: string;
  url?: string;
  published_date: Date;
  confidence: number;
  collected_at: Date;
}

export class REMAgent implements Agent {
  name = 'REM';
  label = 'Regulatory Event Monitor';
  description = 'Monitors regulatory news and enforcement actions';

  private newsApiKey: string;
  private useMock: boolean;

  constructor(useMock: boolean = false) {
    this.useMock = useMock;
    this.newsApiKey = process.env.NEWS_API_KEY || '';
    
    if (!this.newsApiKey && !useMock) {
      console.warn('NEWS_API_KEY not set, using mock mode');
      this.useMock = true;
    }
  }

  /**
   * Monitor regulatory events for a firm
   */
  async verify(firm: Firm, context?: AgentContext): Promise<RegulatoryEventEvidence[]> {
    if (this.useMock) {
      return this.getMockEvents(firm);
    }

    try {
      // Search news for regulatory events
      const events: RegulatoryEventEvidence[] = [];
      
      // Search queries
      const queries = [
        `${firm.name} regulatory`,
        `${firm.name} SEC`,
        `${firm.name} enforcement`,
        `${firm.name} warning`,
      ];

      for (const query of queries) {
        const newsResults = await this.searchNews(query);
        
        for (const article of newsResults) {
          events.push({
            evidence_type: 'REGULATORY_EVENT',
            firm_id: firm.firm_id,
            firm_name: firm.name,
            event_type: this.classifyEvent(article.title),
            severity: this.assessSeverity(article.title, article.description || ''),
            source: article.source,
            title: article.title,
            description: article.description,
            url: article.url,
            published_date: new Date(article.publishedAt),
            confidence: 0.8,
            collected_at: new Date(),
          });
        }
      }

      return events.slice(0, 10); // Limit to 10 most recent
    } catch (error) {
      console.error(`REM Agent error for ${firm.name}:`, error);
      return [];
    }
  }

  private async searchNews(query: string): Promise<any[]> {
    try {
      const response = await axios.get('https://newsapi.org/v2/everything', {
        params: {
          q: query,
          apiKey: this.newsApiKey,
          language: 'en',
          sortBy: 'publishedAt',
          pageSize: 5,
        },
        timeout: 10000,
      });

      return response.data.articles || [];
    } catch (error) {
      console.error('News API error:', error);
      return [];
    }
  }

  private classifyEvent(title: string): 'ENFORCEMENT' | 'WARNING' | 'NEWS' | 'FILING' {
    const lowerTitle = title.toLowerCase();
    
    if (lowerTitle.includes('enforcement') || lowerTitle.includes('penalty') || lowerTitle.includes('fine')) {
      return 'ENFORCEMENT';
    }
    if (lowerTitle.includes('warning') || lowerTitle.includes('alert')) {
      return 'WARNING';
    }
    if (lowerTitle.includes('filing') || lowerTitle.includes('sec')) {
      return 'FILING';
    }
    return 'NEWS';
  }

  private assessSeverity(title: string, description: string): 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' {
    const text = (title + ' ' + description).toLowerCase();
    
    if (text.includes('fraud') || text.includes('suspended') || text.includes('revoked')) {
      return 'CRITICAL';
    }
    if (text.includes('enforcement') || text.includes('violation')) {
      return 'HIGH';
    }
    if (text.includes('warning') || text.includes('investigation')) {
      return 'MEDIUM';
    }
    return 'LOW';
  }

  private getMockEvents(firm: Firm): RegulatoryEventEvidence[] {
    return [
      {
        evidence_type: 'REGULATORY_EVENT',
        firm_id: firm.firm_id,
        firm_name: firm.name,
        event_type: 'NEWS',
        severity: 'LOW',
        source: 'Mock News',
        title: `${firm.name} expands operations`,
        description: 'Company announces expansion plans',
        published_date: new Date(),
        confidence: 1.0,
        collected_at: new Date(),
      },
    ];
  }

  async verifyBatch(firms: Firm[], context?: AgentContext): Promise<RegulatoryEventEvidence[][]> {
    const results = await Promise.all(
      firms.map(firm => this.verify(firm, context))
    );
    return results;
  }

  getMetadata(): Record<string, any> {
    return {
      name: this.name,
      label: this.label,
      description: this.description,
      useMock: this.useMock,
      capabilities: ['news_monitoring', 'sec_filings', 'enforcement_tracking'],
    };
  }
}
