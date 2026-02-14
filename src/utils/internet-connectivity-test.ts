/**
 * Internet Connectivity Test
 * Verifies that agents can access external APIs
 */

import axios from 'axios';
import { REMAgent } from '../agents/rem/rem-regulatory.agent';
import { FRPAgent } from '../agents/frp/frp-reputation.agent';

interface ConnectivityResult {
  service: string;
  url: string;
  status: 'SUCCESS' | 'FAILED';
  responseTime: number;
  error?: string;
}

export async function testInternetConnectivity(): Promise<ConnectivityResult[]> {
  const results: ConnectivityResult[] = [];

  // Test NewsAPI
  const newsApiStart = Date.now();
  try {
    await axios.get('https://newsapi.org/v2/top-headlines', {
      params: {
        country: 'us',
        apiKey: process.env.NEWS_API_KEY || 'test',
      },
      timeout: 5000,
    });
    results.push({
      service: 'NewsAPI',
      url: 'https://newsapi.org',
      status: 'SUCCESS',
      responseTime: Date.now() - newsApiStart,
    });
  } catch (error: any) {
    results.push({
      service: 'NewsAPI',
      url: 'https://newsapi.org',
      status: 'FAILED',
      responseTime: Date.now() - newsApiStart,
      error: error.message,
    });
  }

  // Test TrustPilot (web scraping)
  const trustpilotStart = Date.now();
  try {
    await axios.get('https://www.trustpilot.com/', {
      timeout: 5000,
      headers: {
        'User-Agent': 'Mozilla/5.0',
      },
    });
    results.push({
      service: 'TrustPilot',
      url: 'https://www.trustpilot.com',
      status: 'SUCCESS',
      responseTime: Date.now() - trustpilotStart,
    });
  } catch (error: any) {
    results.push({
      service: 'TrustPilot',
      url: 'https://www.trustpilot.com',
      status: 'FAILED',
      responseTime: Date.now() - trustpilotStart,
      error: error.message,
    });
  }

  // Test FCA Registry
  const fcaStart = Date.now();
  try {
    await axios.get('https://register.fca.org.uk/s/', {
      timeout: 5000,
    });
    results.push({
      service: 'FCA Registry',
      url: 'https://register.fca.org.uk',
      status: 'SUCCESS',
      responseTime: Date.now() - fcaStart,
    });
  } catch (error: any) {
    results.push({
      service: 'FCA Registry',
      url: 'https://register.fca.org.uk',
      status: 'FAILED',
      responseTime: Date.now() - fcaStart,
      error: error.message,
    });
  }

  // Test Google (for MIS agent research)
  const googleStart = Date.now();
  try {
    await axios.get('https://www.google.com/', {
      timeout: 5000,
    });
    results.push({
      service: 'Google Search',
      url: 'https://www.google.com',
      status: 'SUCCESS',
      responseTime: Date.now() - googleStart,
    });
  } catch (error: any) {
    results.push({
      service: 'Google Search',
      url: 'https://www.google.com',
      status: 'FAILED',
      responseTime: Date.now() - googleStart,
      error: error.message,
    });
  }

  // Test general internet connectivity
  const dnsStart = Date.now();
  try {
    await axios.get('https://dns.google/resolve?name=example.com', {
      timeout: 5000,
    });
    results.push({
      service: 'DNS Resolution',
      url: 'https://dns.google',
      status: 'SUCCESS',
      responseTime: Date.now() - dnsStart,
    });
  } catch (error: any) {
    results.push({
      service: 'DNS Resolution',
      url: 'https://dns.google',
      status: 'FAILED',
      responseTime: Date.now() - dnsStart,
      error: error.message,
    });
  }

  return results;
}

export function printConnectivityReport(results: ConnectivityResult[]): void {
  console.log('\n=== Internet Connectivity Test ===\n');
  
  results.forEach(result => {
    const statusIcon = result.status === 'SUCCESS' ? '✓' : '✗';
    const statusColor = result.status === 'SUCCESS' ? '\x1b[32m' : '\x1b[31m';
    
    console.log(`${statusColor}${statusIcon}\x1b[0m ${result.service}`);
    console.log(`  URL: ${result.url}`);
    console.log(`  Response Time: ${result.responseTime}ms`);
    if (result.error) {
      console.log(`  Error: ${result.error}`);
    }
    console.log('');
  });

  const successCount = results.filter(r => r.status === 'SUCCESS').length;
  const totalCount = results.length;
  
  console.log(`\n${successCount}/${totalCount} services reachable`);
  
  if (successCount === totalCount) {
    console.log('\x1b[32m✓ All agents have internet access\x1b[0m');
  } else {
    console.log('\x1b[33m⚠ Some services are unreachable\x1b[0m');
  }
}

// Run test if executed directly
if (require.main === module) {
  testInternetConnectivity()
    .then(results => {
      printConnectivityReport(results);
      process.exit(results.every(r => r.status === 'SUCCESS') ? 0 : 1);
    })
    .catch(error => {
      console.error('Connectivity test failed:', error);
      process.exit(1);
    });
}
