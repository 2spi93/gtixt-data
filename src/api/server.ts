/**
 * Express Server with Verification & Screening API
 */

import express, { Express } from 'express';
import cors from 'cors';
import bodyParser from 'body-parser';
import { VerificationAPI } from './verification-api';

/**
 * Server Configuration
 */
interface ServerConfig {
  port: number;
  host: string;
  corsOrigins?: string[];
  mockMode?: boolean;
}

/**
 * Create and configure Express server
 */
export function createServer(config: Partial<ServerConfig> = {}): Express {
  const finalConfig: ServerConfig = {
    port: config.port || 3001,
    host: config.host || 'localhost',
    corsOrigins: config.corsOrigins || ['http://localhost:3000', 'http://localhost:3001'],
    mockMode: config.mockMode !== false,
  };

  const app = express();

  /**
   * Middleware
   */
  app.use(
    cors({
      origin: finalConfig.corsOrigins,
      credentials: true,
    })
  );
  app.use(bodyParser.json({ limit: '1mb' }));
  app.use(bodyParser.urlencoded({ limit: '1mb', extended: true }));

  /**
   * Request logging middleware
   */
  app.use((req, res, next) => {
    const startTime = Date.now();
    res.on('finish', () => {
      const duration = Date.now() - startTime;
      console.log(`[${new Date().toISOString()}] ${req.method} ${req.path} - ${res.statusCode} (${duration}ms)`);
    });
    next();
  });

  /**
   * Health check endpoint
   */
  app.get('/', (req, res) => {
    res.json({
      service: 'GPTI Verification & Screening Service',
      version: '1.0.0',
      status: 'operational',
      timestamp: new Date().toISOString(),
      mode: finalConfig.mockMode ? 'MOCK' : 'PRODUCTION',
      api_endpoints: {
        verify: 'POST /api/verify - Verify firm against FCA + sanctions',
        screen: 'POST /api/screen - Screen entity against sanctions',
        batchScreen: 'POST /api/screen/batch - Batch screen multiple entities',
        statistics: 'GET /api/statistics - Get service statistics',
        health: 'GET /api/health - Health check',
      },
      example_requests: {
        verify: {
          endpoint: 'POST /api/verify',
          body: {
            firmName: 'FTMO Ltd',
            country: 'GB',
          },
        },
        screen: {
          endpoint: 'POST /api/screen',
          body: {
            name: 'Vladimir Sokolov',
            threshold: 0.85,
          },
        },
        batchScreen: {
          endpoint: 'POST /api/screen/batch',
          body: {
            names: ['FTMO Ltd', 'Gazprom Export', 'Al-Faisal Bank'],
            threshold: 0.85,
          },
        },
      },
    });
  });

  /**
   * Setup API routes
   */
  const api = new VerificationAPI();
  app.use('/api', api.getRouter());

  /**
   * Error handling middleware
   */
  app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
    console.error('Error:', {
      message: err.message,
      stack: err.stack,
      path: req.path,
      method: req.method,
    });

    res.status(err.status || 500).json({
      status: 'error',
      error: err.message || 'Internal server error',
      path: req.path,
    });
  });

  /**
   * 404 handler
   */
  app.use((req, res) => {
    res.status(404).json({
      status: 'error',
      error: 'Endpoint not found',
      path: req.path,
      method: req.method,
    });
  });

  /**
   * Start server if module is run directly
   */
  if (require.main === module) {
    const server = app.listen(finalConfig.port, finalConfig.host, () => {
      console.log(`\n✅ GPTI Verification Service Started`);
      console.log(`📍 URL: http://${finalConfig.host}:${finalConfig.port}`);
      console.log(`🔧 Mode: ${finalConfig.mockMode ? 'MOCK' : 'PRODUCTION'}`);
      console.log(`\n📚 API Documentation:`);
      console.log(`   GET  http://${finalConfig.host}:${finalConfig.port}/          - API Overview`);
      console.log(`   GET  http://${finalConfig.host}:${finalConfig.port}/api/health  - Health Check`);
      console.log(`   POST http://${finalConfig.host}:${finalConfig.port}/api/verify  - Verify Firm`);
      console.log(`   POST http://${finalConfig.host}:${finalConfig.port}/api/screen  - Screen Entity`);
      console.log(`\n`);
    });

    // Graceful shutdown
    process.on('SIGTERM', () => {
      console.log('\n⛔ SIGTERM received, shutting down gracefully...');
      server.close(() => {
        console.log('✅ Server closed');
        process.exit(0);
      });
    });
  }

  return app;
}

/**
 * Export server factory
 */
export default createServer;
