/**
 * Agent Registry
 * Central registry of all 7 agents
 */

import { Agent } from '../types/agent';
import { RVIAgent } from '../agents/rvi/rvi-fca.agent';
import { SSSAgentWrapper } from '../agents/sss/sss-agent-wrapper';
import { REMAgent } from '../agents/rem/rem-regulatory.agent';
import { FRPAgent } from '../agents/frp/frp-reputation.agent';
import { IRSAgent } from '../agents/irs/irs-submissions.agent';
import { MISAgent } from '../agents/mis/mis-investigation.agent';
import { IIPAgent } from '../agents/iip/iip-iosco.agent';

export class AgentRegistry {
  private agents: Map<string, Agent>;

  constructor(useMock: boolean = false) {
    this.agents = new Map();
    
    // Initialize all 7 agents
    this.agents.set('RVI', new RVIAgent(useMock));
    this.agents.set('SSS', new SSSAgentWrapper(useMock));
    this.agents.set('REM', new REMAgent(useMock));
    this.agents.set('FRP', new FRPAgent(useMock));
    this.agents.set('IRS', new IRSAgent(useMock));
    this.agents.set('MIS', new MISAgent(useMock));
    this.agents.set('IIP', new IIPAgent(useMock));
  }

  getAgent(name: string): Agent | undefined {
    return this.agents.get(name.toUpperCase());
  }

  getAllAgents(): Agent[] {
    return Array.from(this.agents.values());
  }

  getAgentNames(): string[] {
    return Array.from(this.agents.keys());
  }

  getAgentMetadata(): Record<string, any>[] {
    return this.getAllAgents().map(agent => agent.getMetadata());
  }

  async verifyFirm(firmId: string, agentName: string, firm: any): Promise<any> {
    const agent = this.getAgent(agentName);
    if (!agent) {
      throw new Error(`Agent ${agentName} not found`);
    }

    return await agent.verify(firm);
  }

  async verifyFirmAllAgents(firm: any): Promise<Record<string, any>> {
    const results: Record<string, any> = {};

    for (const [name, agent] of this.agents) {
      try {
        results[name] = await agent.verify(firm);
      } catch (error: any) {
        results[name] = {
          error: error.message,
          status: 'FAILED',
        };
      }
    }

    return results;
  }
}

// Singleton instance
let registry: AgentRegistry | null = null;

export function getAgentRegistry(useMock: boolean = false): AgentRegistry {
  if (!registry) {
    registry = new AgentRegistry(useMock);
  }
  return registry;
}

export function resetAgentRegistry(): void {
  registry = null;
}
