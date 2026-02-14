/**
 * Slack Notification Service
 * Sends alerts for IRS submissions and MIS investigations
 */

import axios from 'axios';

interface SlackMessage {
  text: string;
  blocks?: any[];
  attachments?: any[];
}

export class SlackNotifier {
  private webhookUrl: string;
  private enabled: boolean;

  constructor() {
    this.webhookUrl = process.env.SLACK_WEBHOOK_URL || '';
    this.enabled = !!this.webhookUrl;
    
    if (!this.enabled) {
      console.warn('SLACK_WEBHOOK_URL not set - notifications disabled');
    }
  }

  /**
   * Send IRS submission notification
   */
  async notifyIRSSubmission(submission: {
    firm_id: string;
    firm_name: string;
    submission_type: string;
    content: string;
    user_id?: string;
    submission_id: string;
  }): Promise<boolean> {
    if (!this.enabled) return false;

    const message: SlackMessage = {
      text: '📝 New IRS Submission',
      blocks: [
        {
          type: 'header',
          text: {
            type: 'plain_text',
            text: '📝 New User Submission - Action Required',
          },
        },
        {
          type: 'section',
          fields: [
            {
              type: 'mrkdwn',
              text: `*Firm:*\n${submission.firm_name}`,
            },
            {
              type: 'mrkdwn',
              text: `*Type:*\n${submission.submission_type}`,
            },
            {
              type: 'mrkdwn',
              text: `*Submitted by:*\n${submission.user_id || 'Anonymous'}`,
            },
            {
              type: 'mrkdwn',
              text: `*Submission ID:*\n${submission.submission_id}`,
            },
          ],
        },
        {
          type: 'section',
          text: {
            type: 'mrkdwn',
            text: `*Content:*\n${submission.content}`,
          },
        },
        {
          type: 'actions',
          elements: [
            {
              type: 'button',
              text: {
                type: 'plain_text',
                text: '✅ Approve',
              },
              style: 'primary',
              value: `approve_${submission.submission_id}`,
              action_id: 'approve_submission',
            },
            {
              type: 'button',
              text: {
                type: 'plain_text',
                text: '❌ Reject',
              },
              style: 'danger',
              value: `reject_${submission.submission_id}`,
              action_id: 'reject_submission',
            },
            {
              type: 'button',
              text: {
                type: 'plain_text',
                text: '🔍 View Firm',
              },
              url: `${process.env.NEXT_PUBLIC_SITE_URL}/firm/${submission.firm_id}`,
            },
          ],
        },
      ],
    };

    return this.send(message);
  }

  /**
   * Send MIS investigation alert
   */
  async notifyMISInvestigation(investigation: {
    firm_id: string;
    firm_name: string;
    investigation_id: string;
    risk_level: string;
    findings: string[];
  }): Promise<boolean> {
    if (!this.enabled) return false;

    const emoji = {
      CRITICAL: '🚨',
      HIGH: '⚠️',
      MEDIUM: '🟡',
      LOW: '✅',
    }[investigation.risk_level] || '🔍';

    const color = {
      CRITICAL: '#dc3545',
      HIGH: '#fd7e14',
      MEDIUM: '#ffc107',
      LOW: '#28a745',
    }[investigation.risk_level] || '#6c757d';

    const message: SlackMessage = {
      text: `${emoji} MIS Investigation Alert - ${investigation.risk_level} Risk`,
      attachments: [
        {
          color,
          blocks: [
            {
              type: 'header',
              text: {
                type: 'plain_text',
                text: `${emoji} Investigation Alert - ${investigation.risk_level} Risk`,
              },
            },
            {
              type: 'section',
              fields: [
                {
                  type: 'mrkdwn',
                  text: `*Firm:*\n${investigation.firm_name}`,
                },
                {
                  type: 'mrkdwn',
                  text: `*Risk Level:*\n${investigation.risk_level}`,
                },
              ],
            },
            {
              type: 'section',
              text: {
                type: 'mrkdwn',
                text: `*Findings:*\n${investigation.findings.map(f => `• ${f}`).join('\n')}`,
              },
            },
            {
              type: 'actions',
              elements: [
                {
                  type: 'button',
                  text: {
                    type: 'plain_text',
                    text: '🕵️ Review Investigation',
                  },
                  url: `${process.env.NEXT_PUBLIC_SITE_URL}/firm/${investigation.firm_id}`,
                },
              ],
            },
          ],
        },
      ],
    };

    return this.send(message);
  }

  /**
   * Send generic notification
   */
  private async send(message: SlackMessage): Promise<boolean> {
    try {
      await axios.post(this.webhookUrl, message, {
        timeout: 5000,
      });
      return true;
    } catch (error) {
      console.error('Slack notification failed:', error);
      return false;
    }
  }
}

// Singleton instance
let notifier: SlackNotifier | null = null;

export function getSlackNotifier(): SlackNotifier {
  if (!notifier) {
    notifier = new SlackNotifier();
  }
  return notifier;
}
