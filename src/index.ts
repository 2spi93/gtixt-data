/**
 * GPTI Verification Service - Main Entry Point
 */

import createServer from './api/server';

/**
 * Start the service
 */
async function main(): Promise<void> {
  try {
    // Create and start server
    const app = createServer({
      port: parseInt(process.env.API_PORT || '3001', 10),
      host: process.env.API_HOST || 'localhost',
      mockMode: process.env.MOCK_MODE !== 'false',
    });

    // Ensure server is running
    app.listen(parseInt(process.env.API_PORT || '3001', 10), process.env.API_HOST || 'localhost');
  } catch (error: any) {
    console.error('Failed to start service:', error.message);
    process.exit(1);
  }
}

// Start if run directly
if (require.main === module) {
  main();
}

export { main };
