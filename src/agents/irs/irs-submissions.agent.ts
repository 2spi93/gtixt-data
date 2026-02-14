/**
 * IRS Agent - Independent Review System
 * Handles user submissions and manual reviews
 */

import { Agent, AgentContext } from '../../types/agent';
import { Firm } from '../../types/firm';
import { getDatabase } from '../../db/postgres-client';
import { getSlackNotifier } from '../../utils/slack-notifier';

export interface UserSubmissionEvidence {
  evidence_type: 'USER_SUBMISSION';
  firm_id: string;
  firm_name: string;
  submission_id: string;
  submission_type: 'COMPLAINT' | 'REVIEW' | 'VERIFICATION' | 'UPDATE';
  status: 'PENDING' | 'VERIFIED' | 'REJECTED';
  content: string;
  user_id?: string;
  verification_score: number;
  reviewed_by?: string;
  reviewed_at?: Date;
  confidence: number;
  collected_at: Date;
}

export class IRSAgent implements Agent {
  name = 'IRS';
  label = 'Independent Review System';
  description = 'Processes user submissions and manual reviews';

  private useMock: boolean;
  private db: any;

  constructor(useMock: boolean = false) {
    this.useMock = useMock;
    if (!useMock) {
      this.db = getDatabase();
    }
  }

  /**
   * Get submissions for a firm
   */
  async verify(firm: Firm, context?: AgentContext): Promise<UserSubmissionEvidence[]> {
    if (this.useMock) {
      return this.getMockSubmissions(firm);
    }

    try {
      // Fetch submissions from database
      const result = await this.db.query(
        `SELECT * FROM user_submissions 
         WHERE firm_id = $1 
         AND status IN ('VERIFIED', 'PENDING')
         ORDER BY created_at DESC
         LIMIT 20`,
        [firm.firm_id]
      );

      return result.rows.map((row: any) => ({
        evidence_type: 'USER_SUBMISSION',
        firm_id: firm.firm_id,
        firm_name: firm.name,
        submission_id: row.submission_id,
        submission_type: row.submission_type,
        status: row.status,
        content: row.content,
        user_id: row.user_id,
        verification_score: row.verification_score || 0,
        reviewed_by: row.reviewed_by,
        reviewed_at: row.reviewed_at,
        confidence: row.status === 'VERIFIED' ? 0.9 : 0.5,
        collected_at: new Date(),
      }));
    } catch (error) {
      console.error(`IRS Agent error for ${firm.name}:`, error);
      return [];
    }
  }

  /**
   * Submit new evidence
   */
  async submitEvidence(
    firmId: string,
    firmName: string,
    submissionType: string,
    content: string,
    userId?: string
  ): Promise<string> {
    if (this.useMock) {
      return `mock-submission-${Date.now()}`;
    }

    try {
      const result = await this.db.query(
        `INSERT INTO user_submissions (firm_id, submission_type, content, user_id, status, created_at)
         VALUES ($1, $2, $3, $4, 'PENDING', NOW())
         RETURNING submission_id`,
        [firmId, submissionType, content, userId || 'anonymous']
      );

      const submissionId = result.rows[0].submission_id;

      // 🚀 Send Slack notification
      const notifier = getSlackNotifier();
      await notifier.notifyIRSSubmission({
        firm_id: firmId,
        firm_name: firmName,
        submission_type: submissionType,
        content,
        user_id: userId,
        submission_id: submissionId,
      });

      return submissionId;
    } catch (error) {
      console.error('Failed to submit evidence:', error);
      throw error;
    }
  }

  /**
   * Verify submission (admin action)
   */
  async verifySubmission(submissionId: string, reviewedBy: string): Promise<boolean> {
    if (this.useMock) {
      return true;
    }

    try {
      await this.db.query(
        `UPDATE user_submissions 
         SET status = 'VERIFIED', reviewed_by = $1, reviewed_at = NOW()
         WHERE submission_id = $2`,
        [reviewedBy, submissionId]
      );

      return true;
    } catch (error) {
      console.error('Failed to verify submission:', error);
      return false;
    }
  }

  private getMockSubmissions(firm: Firm): UserSubmissionEvidence[] {
    return [
      {
        evidence_type: 'USER_SUBMISSION',
        firm_id: firm.firm_id,
        firm_name: firm.name,
        submission_id: `mock-${Date.now()}`,
        submission_type: 'REVIEW',
        status: 'VERIFIED',
        content: 'Positive experience with this firm',
        verification_score: 0.8,
        confidence: 0.7,
        collected_at: new Date(),
      },
    ];
  }

  async verifyBatch(firms: Firm[], context?: AgentContext): Promise<UserSubmissionEvidence[][]> {
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
      capabilities: ['user_submissions', 'manual_verification', 'evidence_tracking'],
    };
  }
}
