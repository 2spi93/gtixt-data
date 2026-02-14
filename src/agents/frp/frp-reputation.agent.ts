/**
 * FRP Agent - Firm Reputation & Payout
 * Analyzes TrustPilot reviews and payout reputation
 */

import { Agent, AgentContext } from '../../types/agent';
import { Firm } from '../../types/firm';
import axios from 'axios';
import * as cheerio from 'cheerio';

export interface ReputationEvidence {
  evidence_type: 'REPUTATION_ANALYSIS';
  firm_id: string;
  firm_name: string;
  trustpilot_score?: number;
  trustpilot_reviews?: number;
  trustpilot_url?: string;
  sentiment: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE';
  payout_issues: number;
  common_complaints: string[];
  confidence: number;
  data_source: 'TRUSTPILOT' | 'REVIEWS' | 'MOCK';
  collected_at: Date;
}

export class FRPAgent implements Agent {
  name = 'FRP';
  label = 'Firm Reputation & Payout';
  description = 'Analyzes firm reputation and payout reliability';

  private useMock: boolean;

  constructor(useMock: boolean = false) {
    this.useMock = useMock;
  }

  /**
   * Analyze reputation for a firm
   */
  async verify(firm: Firm, context?: AgentContext): Promise<ReputationEvidence> {
    if (this.useMock) {
      return this.getMockReputation(firm);
    }

    try {
      // Try to fetch TrustPilot data
      const trustpilotData = await this.fetchTrustPilot(firm);
      
      return {
        evidence_type: 'REPUTATION_ANALYSIS',
        firm_id: firm.firm_id,
        firm_name: firm.name,
        trustpilot_score: trustpilotData.score,
        trustpilot_reviews: trustpilotData.reviews,
        trustpilot_url: trustpilotData.url,
        sentiment: this.analyzeSentiment(trustpilotData.score),
        payout_issues: trustpilotData.payoutComplaints,
        common_complaints: trustpilotData.complaints,
        confidence: trustpilotData.score ? 0.9 : 0.5,
        data_source: trustpilotData.score ? 'TRUSTPILOT' : 'MOCK',
        collected_at: new Date(),
      };
    } catch (error) {
      console.error(`FRP Agent error for ${firm.name}:`, error);
      return this.getMockReputation(firm);
    }
  }

  private async fetchTrustPilot(firm: Firm): Promise<any> {
    try {
      // Convert firm name to TrustPilot slug
      const slug = firm.website_root
        ? this.extractDomain(firm.website_root)
        : firm.name.toLowerCase().replace(/\s+/g, '-');

      const url = `https://www.trustpilot.com/review/${slug}`;
      
      const response = await axios.get(url, {
        timeout: 10000,
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; GTIXT-Bot/1.0)',
        },
      });

      const $ = cheerio.load(response.data);
      
      // Extract score
      const scoreText = $('[data-rating-typography]').first().text();
      const score = parseFloat(scoreText) || 0;
      
      // Extract review count
      const reviewsText = $('[data-reviews-count-typography]').first().text();
      const reviews = parseInt(reviewsText.replace(/[^0-9]/g, '')) || 0;

      // Extract complaints
      const complaints: string[] = [];
      $('.review-content').slice(0, 20).each((i, el) => {
        const text = $(el).text().toLowerCase();
        if (text.includes('payout') || text.includes('withdrawal')) {
          complaints.push('payout issues');
        }
        if (text.includes('scam') || text.includes('fraud')) {
          complaints.push('fraud allegations');
        }
        if (text.includes('customer service') || text.includes('support')) {
          complaints.push('customer service');
        }
      });

      const uniqueComplaints = [...new Set(complaints)];
      const payoutComplaints = complaints.filter(c => c === 'payout issues').length;

      return {
        score,
        reviews,
        url,
        complaints: uniqueComplaints,
        payoutComplaints,
      };
    } catch (error) {
      // TrustPilot not found or error
      return {
        score: 0,
        reviews: 0,
        url: '',
        complaints: [],
        payoutComplaints: 0,
      };
    }
  }

  private extractDomain(url: string): string {
    try {
      const domain = url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0];
      return domain.replace(/\./g, '-');
    } catch {
      return '';
    }
  }

  private analyzeSentiment(score: number): 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' {
    if (score >= 4.0) return 'POSITIVE';
    if (score >= 3.0) return 'NEUTRAL';
    return 'NEGATIVE';
  }

  private getMockReputation(firm: Firm): ReputationEvidence {
    const mockScore = 3.5 + Math.random() * 1.5; // 3.5-5.0
    
    return {
      evidence_type: 'REPUTATION_ANALYSIS',
      firm_id: firm.firm_id,
      firm_name: firm.name,
      trustpilot_score: mockScore,
      trustpilot_reviews: Math.floor(Math.random() * 500) + 100,
      sentiment: this.analyzeSentiment(mockScore),
      payout_issues: Math.floor(Math.random() * 5),
      common_complaints: ['customer service', 'verification delays'],
      confidence: 0.7,
      data_source: 'MOCK',
      collected_at: new Date(),
    };
  }

  async verifyBatch(firms: Firm[], context?: AgentContext): Promise<ReputationEvidence[]> {
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
      capabilities: ['trustpilot_scraping', 'sentiment_analysis', 'payout_tracking'],
    };
  }
}
