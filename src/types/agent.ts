/**
 * Agent Interface and Types
 * Base interfaces for all data verification agents
 */

export interface AgentContext {
  requestId?: string;
  userId?: string;
  timestamp?: Date;
  metadata?: Record<string, any>;
}

export interface Agent {
  name: string;
  label: string;
  description: string;
  verify(entity: any, context?: AgentContext): Promise<any>;
  verifyBatch?(entities: any[], context?: AgentContext): Promise<any[]>;
  getMetadata(): Record<string, any>;
}
