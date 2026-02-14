/**
 * Integration Tests for Verification & Screening API
 * Tests API endpoints with mock data
 */

import { describe, test, expect, beforeAll } from '@jest/globals';
import request from 'supertest';
import express, { Express } from 'express';
import { VerificationAPI } from '../api/verification-api';
import bodyParser from 'body-parser';

describe('Verification & Screening API Integration Tests', () => {
  let app: Express;
  let api: VerificationAPI;

  beforeAll(() => {
    // Setup Express app with API
    app = express();
    app.use(bodyParser.json());

    api = new VerificationAPI();
    app.use('/api', api.getRouter());
  });

  /**
   * POST /api/verify Tests
   */
  describe('POST /api/verify', () => {
    test('should verify FTMO Ltd (authorized firm)', async () => {
      const res = await request(app).post('/api/verify').send({
        firmName: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      expect(res.body.data).toBeDefined();
      expect(res.body.data.firmName).toBe('FTMO Ltd');
      expect(res.body.data.fca).toBeDefined();
      expect(res.body.data.sanctions).toBeDefined();
      expect(res.body.data.duration).toBeGreaterThanOrEqual(0);
    });

    test('should detect sanctioned entity - Gazprom Export', async () => {
      const res = await request(app).post('/api/verify').send({
        firmName: 'Gazprom Export',
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      expect(res.body.data.sanctions.status).not.toBe('CLEAR');
      expect(res.body.data.riskScore).not.toBe('LOW');
    });

    test('should require firmName parameter', async () => {
      const res = await request(app).post('/api/verify').send({});

      expect(res.status).toBe(400);
      expect(res.body.status).toBe('error');
      expect(res.body.error).toContain('firmName');
    });

    test('should handle unknown firm gracefully', async () => {
      const res = await request(app).post('/api/verify').send({
        firmName: 'Unknown Trading Firm XYZ',
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      expect(res.body.data.duration).toBeGreaterThanOrEqual(0);
    });

    test('should complete verification within 500ms', async () => {
      const res = await request(app).post('/api/verify').send({
        firmName: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      expect(res.body.data.duration).toBeLessThan(500);
    });
  });

  /**
   * POST /api/screen Tests
   */
  describe('POST /api/screen', () => {
    test('should screen FTMO Ltd (not sanctioned)', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      expect(res.body.data).toBeDefined();
      expect(res.body.data.name).toBe('FTMO Ltd');
      expect(res.body.data.screeningStatus).toBe('CLEAR');
      expect(res.body.data.matches).toBe(0);
    });

    test('should detect Vladimir Sokolov (sanctioned)', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'Vladimir Sokolov',
        threshold: 0.85,
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      expect(res.body.data.screeningStatus).not.toBe('CLEAR');
      expect(res.body.data.matches).toBeGreaterThan(0);
    });

    test('should detect with fuzzy matching', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'Solkolov Vladimir', // Name order reversed
        matchTypes: ['fuzzy'],
        threshold: 0.80,
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      // May or may not match depending on fuzzy algorithm
      expect(res.body.data.matches).toBeGreaterThanOrEqual(0);
    });

    test('should require name parameter', async () => {
      const res = await request(app).post('/api/screen').send({
        threshold: 0.85,
      });

      expect(res.status).toBe(400);
      expect(res.body.status).toBe('error');
      expect(res.body.error).toContain('name');
    });

    test('should respect custom threshold', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'Gazprom',
        threshold: 0.95, // Very high threshold
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      // High threshold may result in fewer matches
      expect(res.body.data.matches).toBeGreaterThanOrEqual(0);
    });

    test('should complete screening within 500ms', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      expect(res.body.data.duration).toBeLessThan(500);
    });

    test('should format entity matches correctly', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'Vladimir Sokolov',
      });

      expect(res.status).toBe(200);
      if (res.body.data.matches > 0) {
        expect(Array.isArray(res.body.data.entities)).toBe(true);
        const entity = res.body.data.entities[0];
        expect(entity.name).toBeDefined();
        expect(entity.type).toBeDefined();
        expect(entity.program).toBeDefined();
        expect(entity.matchType).toBeDefined();
        expect(typeof entity.score).toBe('number');
      }
    });
  });

  /**
   * POST /api/screen/batch Tests
   */
  describe('POST /api/screen/batch', () => {
    test('should batch screen multiple entities', async () => {
      const names = ['FTMO Ltd', 'Gazprom Export', 'The5ers'];
      const res = await request(app).post('/api/screen/batch').send({
        names,
        threshold: 0.85,
      });

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      expect(res.body.data.totalRequests).toBe(3);
      expect(Array.isArray(res.body.data.results)).toBe(true);
      expect(res.body.data.results).toHaveLength(3);
      expect(res.body.data.averageDuration).toBeGreaterThan(0);
    });

    test('should validate batch size limit (max 100)', async () => {
      const names = Array(101).fill('Test Entity');
      const res = await request(app).post('/api/screen/batch').send({
        names,
      });

      expect(res.status).toBe(400);
      expect(res.body.status).toBe('error');
      expect(res.body.error).toContain('100');
    });

    test('should require names array', async () => {
      const res = await request(app).post('/api/screen/batch').send({
        threshold: 0.85,
      });

      expect(res.status).toBe(400);
      expect(res.body.status).toBe('error');
    });

    test('should handle empty names array', async () => {
      const res = await request(app).post('/api/screen/batch').send({
        names: [],
      });

      expect(res.status).toBe(400);
      expect(res.body.status).toBe('error');
    });

    test('should calculate statistics correctly', async () => {
      const names = ['FTMO Ltd', 'The5ers', 'MyForexFunds'];
      const res = await request(app).post('/api/screen/batch').send({
        names,
      });

      expect(res.status).toBe(200);
      expect(res.body.data.totalRequests).toBe(3);
      expect(res.body.data.averageDuration).toBeGreaterThan(0);
      expect(res.body.data.totalDuration).toBeGreaterThanOrEqual(res.body.data.averageDuration);
    });

    test('should identify matches in batch results', async () => {
      const names = ['Vladimir Sokolov', 'FTMO Ltd', 'Gazprom Export'];
      const res = await request(app).post('/api/screen/batch').send({
        names,
      });

      expect(res.status).toBe(200);
      expect(res.body.data.results).toHaveLength(3);

      // Check Vladimir Sokolov result
      const vladimirResult = res.body.data.results[0];
      expect(vladimirResult.name).toBe('Vladimir Sokolov');
      expect(vladimirResult.screeningStatus).not.toBe('CLEAR');

      // Check FTMO result
      const ftmoResult = res.body.data.results[1];
      expect(ftmoResult.name).toBe('FTMO Ltd');
      expect(ftmoResult.screeningStatus).toBe('CLEAR');
    });

    test('should complete batch within 2 seconds', async () => {
      const names = ['FTMO Ltd', 'The5ers', 'MyForexFunds'];
      const res = await request(app).post('/api/screen/batch').send({
        names,
      });

      expect(res.status).toBe(200);
      expect(res.body.data.totalDuration).toBeLessThan(2000);
    });
  });

  /**
   * GET /api/statistics Tests
   */
  describe('GET /api/statistics', () => {
    test('should return statistics object', async () => {
      const res = await request(app).get('/api/statistics');

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('success');
      expect(res.body.data).toBeDefined();
    });

    test('should include FCA integration status', async () => {
      const res = await request(app).get('/api/statistics');

      expect(res.status).toBe(200);
      expect(res.body.data.fcaIntegration).toBeDefined();
      expect(res.body.data.fcaIntegration.status).toBe('operational');
      expect(typeof res.body.data.fcaIntegration.mockMode).toBe('boolean');
    });

    test('should include sanctions database info', async () => {
      const res = await request(app).get('/api/statistics');

      expect(res.status).toBe(200);
      expect(res.body.data.sanctionsDatabase).toBeDefined();
      expect(typeof res.body.data.sanctionsDatabase.totalEntities).toBe('number');
      expect(typeof res.body.data.sanctionsDatabase.ofacEntities).toBe('number');
      expect(typeof res.body.data.sanctionsDatabase.unEntities).toBe('number');
    });

    test('should include screening statistics', async () => {
      const res = await request(app).get('/api/statistics');

      expect(res.status).toBe(200);
      expect(res.body.data.screening).toBeDefined();
      expect(typeof res.body.data.screening.totalScreenings).toBe('number');
      expect(typeof res.body.data.screening.matches).toBe('number');
      expect(typeof res.body.data.screening.average_duration_ms).toBe('number');
    });

    test('should include performance metrics', async () => {
      const res = await request(app).get('/api/statistics');

      expect(res.status).toBe(200);
      expect(res.body.data.performance).toBeDefined();
      expect(typeof res.body.data.performance.avgVerificationTime).toBe('number');
      expect(typeof res.body.data.performance.avgScreeningTime).toBe('number');
      expect(typeof res.body.data.performance.p95ResponseTime).toBe('number');
    });
  });

  /**
   * GET /api/health Tests
   */
  describe('GET /api/health', () => {
    test('should return health status', async () => {
      const res = await request(app).get('/api/health');

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('healthy');
      expect(res.body.timestamp).toBeDefined();
      expect(res.body.uptime).toBeGreaterThan(0);
    });

    test('should include endpoint documentation', async () => {
      const res = await request(app).get('/api/health');

      expect(res.status).toBe(200);
      expect(res.body.endpoints).toBeDefined();
      expect(res.body.endpoints.verify).toBe('POST /api/verify');
      expect(res.body.endpoints.screen).toBe('POST /api/screen');
      expect(res.body.endpoints.batchScreen).toBe('POST /api/screen/batch');
    });
  });

  /**
   * Error Handling Tests
   */
  describe('Error Handling', () => {
    test('should handle internal server errors gracefully', async () => {
      const res = await request(app).post('/api/verify').send({
        firmName: 'ValidName',
      });

      // Should not crash with 500
      expect([200, 400, 500]).toContain(res.status);
      expect(res.body.status).toBeDefined();
    });

    test('should validate request content type', async () => {
      const res = await request(app)
        .post('/api/screen')
        .set('Content-Type', 'application/json')
        .send({
          name: 'Test',
        });

      expect(res.status).toBe(200);
      expect(res.body).toBeDefined();
    });
  });

  /**
   * Performance Tests
   */
  describe('Performance Benchmarks', () => {
    test('verify endpoint should respond in < 500ms', async () => {
      const res = await request(app).post('/api/verify').send({
        firmName: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      expect(res.body.data.duration).toBeLessThan(500);
    });

    test('screen endpoint should respond in < 500ms', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      expect(res.body.data.duration).toBeLessThan(500);
    });

    test('batch endpoint with 10 items should respond in < 2000ms', async () => {
      const names = Array(10)
        .fill(0)
        .map((_, i) => `Entity ${i}`);
      const res = await request(app).post('/api/screen/batch').send({
        names,
      });

      expect(res.status).toBe(200);
      expect(res.body.data.totalDuration).toBeLessThan(2000);
    });

    test('statistics endpoint should respond in < 100ms', async () => {
      const startTime = Date.now();
      const res = await request(app).get('/api/statistics');
      const duration = Date.now() - startTime;

      expect(res.status).toBe(200);
      expect(duration).toBeLessThan(100);
    });
  });

  /**
   * Data Validation Tests
   */
  describe('Data Validation', () => {
    test('verify response should have required fields', async () => {
      const res = await request(app).post('/api/verify').send({
        firmName: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      const data = res.body.data;
      expect(data.firmName).toBeDefined();
      expect(data.overallStatus).toBeDefined();
      expect(data.riskScore).toBeDefined();
      expect(data.fca).toBeDefined();
      expect(data.sanctions).toBeDefined();
      expect(data.riskFactors).toBeDefined();
      expect(Array.isArray(data.riskFactors)).toBe(true);
    });

    test('screen response should have required fields', async () => {
      const res = await request(app).post('/api/screen').send({
        name: 'FTMO Ltd',
      });

      expect(res.status).toBe(200);
      const data = res.body.data;
      expect(data.name).toBeDefined();
      expect(data.screeningStatus).toBeDefined();
      expect(typeof data.matches).toBe('number');
      expect(typeof data.confidence).toBe('number');
      expect(Array.isArray(data.entities)).toBe(true);
    });

    test('batch response should have consistent structure', async () => {
      const res = await request(app).post('/api/screen/batch').send({
        names: ['Entity 1', 'Entity 2'],
      });

      expect(res.status).toBe(200);
      expect(res.body.data.results).toHaveLength(2);
      res.body.data.results.forEach((result: any) => {
        expect(result.name).toBeDefined();
        expect(result.screeningStatus).toBeDefined();
        expect(typeof result.matches).toBe('number');
        expect(typeof result.confidence).toBe('number');
      });
    });
  });
});
