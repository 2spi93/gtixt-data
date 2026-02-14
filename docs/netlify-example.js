// Example Netlify function to fetch GPTI public data
// File: netlify/functions/fetch-gpti-data.js

const fetch = require('node-fetch');

exports.handler = async (event, context) => {
  try {
    // Base URL for production (replace with actual domain when available)
    const baseUrl = process.env.GPTI_DATA_URL || 'https://51.210.246.61';

    // Fetch latest metadata
    const latestResponse = await fetch(`${baseUrl}/gpti-snapshots/universe_v0.1_public/_public/latest.json`);
    if (!latestResponse.ok) {
      throw new Error(`Failed to fetch latest.json: ${latestResponse.status}`);
    }
    const latest = await latestResponse.json();

    // Fetch actual data
    const dataResponse = await fetch(`${baseUrl}/gpti-snapshots/${latest.object}`);
    if (!dataResponse.ok) {
      throw new Error(`Failed to fetch data: ${dataResponse.status}`);
    }
    const data = await dataResponse.json();

    // Optional: Verify SHA256 integrity
    const crypto = require('crypto');
    const calculatedSha256 = crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex');
    if (calculatedSha256 !== latest.sha256) {
      throw new Error('SHA256 integrity check failed');
    }

    return {
      statusCode: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        metadata: latest,
        data: data.records, // Note: data.records contains the firms array
        verified: true
      })
    };

  } catch (error) {
    console.error('Error fetching GPTI data:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to fetch GPTI data' })
    };
  }
};