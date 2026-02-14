/**
 * Main API Server for gpti-data-bot
 * Exposes all 7 agents via REST API
 */

import express from 'express';
import cors from 'cors';
import { getAgentRegistry } from '../agents/agent-registry';
import { testInternetConnectivity } from '../utils/internet-connectivity-test';

const app = express();
const PORT = process.env.PORT || 3001;
const MOCK_MODE = process.env.MOCK_MODE === 'true';

// Middleware
app.use(cors());
app.use(express.json());

// Initialize agent registry
const registry = getAgentRegistry(MOCK_MODE);

/**
 * Health check endpoint
 */
app.get('/health', async (req, res) => {
  try {
    const agents = registry.getAgentMetadata();
    const connectivity = await testInternetConnectivity();
    
    res.json({
      status: 'healthy',
      mode: MOCK_MODE ? 'mock' : 'production',
      agents: agents.map(a => ({ name: a.name, label: a.label })),
      connectivity: {
        total: connectivity.length,
        success: connectivity.filter(c => c.status === 'SUCCESS').length,
        services: connectivity.map(c => ({
          service: c.service,
          status: c.status,
          responseTime: c.responseTime,
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    res.status(500).json({
      status: 'unhealthy',
      error: error.message,
    });
  }
});

/**
 * Get all agents metadata
 */
app.get('/agents', (req, res) => {
  const metadata = registry.getAgentMetadata();
  res.json({
    agents: metadata,
    count: metadata.length,
  });
});

/**
 * Get specific agent metadata
 */
app.get('/agents/:agentName', (req, res) => {
  const { agentName } = req.params;
  const agent = registry.getAgent(agentName);
  
  if (!agent) {
    return res.status(404).json({ error: `Agent ${agentName} not found` });
  }
  
  res.json(agent.getMetadata());
});

/**
 * Run agent verification for a firm
 */
app.post('/agents/:agentName/verify', async (req, res) => {
  const { agentName } = req.params;
  const { firm } = req.body;
  
  if (!firm || !firm.firm_id) {
    return res.status(400).json({ error: 'firm object with firm_id required' });
  }
  
  const agent = registry.getAgent(agentName);
  if (!agent) {
    return res.status(404).json({ error: `Agent ${agentName} not found` });
  }
  
  try {
    const result = await agent.verify(firm);
    res.json({
      agent: agentName,
      firmId: firm.firm_id,
      evidence: result,
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    res.status(500).json({
      error: 'Verification failed',
      message: error.message,
    });
  }
});

/**
 * Run all agents for a firm
 */
app.post('/verify/all', async (req, res) => {
  const { firm } = req.body;
  
  if (!firm || !firm.firm_id) {
    return res.status(400).json({ error: 'firm object with firm_id required' });
  }
  
  try {
    const results = await registry.verifyFirmAllAgents(firm);
    res.json({
      firmId: firm.firm_id,
      firmName: firm.name,
      agents: results,
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    res.status(500).json({
      error: 'Verification failed',
      message: error.message,
    });
  }
});

/**
 * Test internet connectivity
 */
app.get('/test/connectivity', async (req, res) => {
  try {
    const results = await testInternetConnectivity();
    const successCount = results.filter(r => r.status === 'SUCCESS').length;
    
    res.json({
      success: successCount === results.length,
      successCount,
      totalCount: results.length,
      services: results,
      timestamp: new Date().toISOString(),
    });
  } catch (error: any) {
    res.status(500).json({
      error: 'Connectivity test failed',
      message: error.message,
    });
  }
});

/**
 * Start server
 */
if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`\n🤖 GPTI Data Bot API Server`);
    console.log(`Mode: ${MOCK_MODE ? 'MOCK' : 'PRODUCTION'}`);
    console.log(`Port: ${PORT}`);
    console.log(`Agents: ${registry.getAgentNames().join(', ')}`);
    console.log(`\n✓ Server running at http://localhost:${PORT}`);
    console.log(`✓ Health check: http://localhost:${PORT}/health\n`);
  });
}

export default app;
