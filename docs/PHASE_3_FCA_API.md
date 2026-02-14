# Phase 3 - FCA Registry API Integration
**Agent:** RVI (Registry Verification)  
**Timeline:** Week 1-2 (Feb 15 - Feb 28, 2026)  
**Status:** IN PROGRESS ⚙️

---

## 📋 FCA API Specification

### Authentication
```
Base URL: https://register.fca.org.uk/api
Auth Type: API Key (header)
Header: X-API-Key: {FCA_API_KEY}
Rate Limit: 1,000 requests/hour
Retry Strategy: Exponential backoff (3x with 5s, 10s, 20s)
```

### Endpoints

#### 1. Firm Search by Name
```
GET /v1/firms/search
Query Parameters:
  - q: string (firm name, wildcard supported)
  - limit: int (default: 10, max: 100)
  - offset: int (default: 0)

Response (200 OK):
{
  "total": 45,
  "limit": 10,
  "offset": 0,
  "firms": [
    {
      "firm_id": "FIRM123456",
      "name": "FTMO Limited",
      "authorization_status": "authorized",
      "authorization_date": "2015-03-12",
      "type": "Investment Firm",
      "country": "GB",
      "regulated_activities": ["DRVSTR", "EDDCAS"],
      "website": "https://ftmo.com"
    }
  ]
}

Error Codes:
  - 400: Invalid parameters
  - 401: Invalid API key
  - 429: Rate limit exceeded
  - 500: Server error
```

#### 2. Firm Details by ID
```
GET /v1/firms/{firm_id}

Response (200 OK):
{
  "firm_id": "FIRM123456",
  "name": "FTMO Limited",
  "authorization_status": "authorized",
  "authorization_date": "2015-03-12",
  "type": "Investment Firm",
  "permissions": [
    {
      "activity": "DRVSTR",
      "label": "Dealing in investments as principal",
      "authorized": true,
      "since": "2015-03-12"
    },
    {
      "activity": "EDDCAS",
      "label": "Arranging deals in investments",
      "authorized": true,
      "since": "2015-03-12"
    }
  ],
  "enforcement_actions": [
    {
      "date": "2024-01-15",
      "type": "fine",
      "amount": 50000,
      "description": "Breach of COBS rules",
      "status": "resolved"
    }
  ],
  "address": {
    "street": "10 Newgate Street",
    "city": "London",
    "postcode": "EC1A 7AZ",
    "country": "GB"
  },
  "last_update": "2026-01-28T15:22:00Z"
}
```

#### 3. License Status Check (Bulk)
```
POST /v1/firms/status-check
Content-Type: application/json

Request Body:
{
  "firms": [
    { "name": "FTMO Limited", "country": "GB" },
    { "name": "XM Limited", "country": "AU" }
  ]
}

Response (200 OK):
{
  "results": [
    {
      "input": { "name": "FTMO Limited", "country": "GB" },
      "found": true,
      "firm_id": "FIRM123456",
      "status": "authorized",
      "confidence": 0.98
    },
    {
      "input": { "name": "XM Limited", "country": "AU" },
      "found": false,
      "status": "not_found",
      "confidence": 0.0
    }
  ]
}
```

---

## 🔧 Implementation Details

### Data Structures

```typescript
// Request type
interface FCAFirmSearch {
  name: string;
  country?: string;
  limit?: number;
  offset?: number;
}

// Response type
interface FCAFirmInfo {
  firm_id: string;
  name: string;
  authorization_status: 'authorized' | 'suspended' | 'revoked';
  authorization_date: Date;
  type: string;
  permissions: {
    activity: string;
    label: string;
    authorized: boolean;
    since: Date;
  }[];
  enforcement_actions: {
    date: Date;
    type: 'fine' | 'warning' | 'suspension';
    amount?: number;
    description: string;
    status: 'active' | 'resolved';
  }[];
  address: {
    street: string;
    city: string;
    postcode: string;
    country: string;
  };
  last_update: Date;
}

// GPTI Evidence mapping
interface LicenseVerificationEvidence {
  evidence_type: 'LICENSE_VERIFICATION';
  status: 'CONFIRMED' | 'REJECTED' | 'SUSPENDED';
  firm_id: string;
  firm_name: string;
  fca_firm_id: string;
  authorization_date: Date;
  permissions: string[];
  enforcement_actions: number; // count of active enforcement
  confidence: number; // 0-100
  data_source: 'FCA_REGISTRY';
  collected_at: Date;
}
```

### Integration Points

#### In `src/agents/rvi/rvi.agent.ts`
```typescript
async function verifyLicense(firm: Firm): Promise<LicenseVerificationEvidence> {
  try {
    // 1. Search FCA registry by firm name
    const searchResults = await fcaClient.search({
      name: firm.name,
      country: firm.country,
      limit: 5
    });
    
    // 2. Find best match (highest confidence)
    const bestMatch = searchResults.firms
      .map(f => ({
        firm: f,
        confidence: calculateNameSimilarity(firm.name, f.name)
      }))
      .sort((a, b) => b.confidence - a.confidence)[0];
    
    if (!bestMatch || bestMatch.confidence < 0.70) {
      return {
        status: 'REJECTED',
        confidence: bestMatch?.confidence || 0,
        // ...
      };
    }
    
    // 3. Get detailed firm info
    const firmDetails = await fcaClient.getFirmDetails(bestMatch.firm.firm_id);
    
    // 4. Check authorization status
    const status = firmDetails.authorization_status === 'authorized' 
      ? 'CONFIRMED' 
      : firmDetails.authorization_status === 'suspended'
      ? 'SUSPENDED'
      : 'REJECTED';
    
    // 5. Count active enforcement actions
    const activeEnforcement = firmDetails.enforcement_actions
      .filter(a => a.status === 'active').length;
    
    // 6. Return evidence
    return {
      evidence_type: 'LICENSE_VERIFICATION',
      status,
      firm_id: firm.firm_id,
      firm_name: firm.name,
      fca_firm_id: firmDetails.firm_id,
      authorization_date: firmDetails.authorization_date,
      permissions: firmDetails.permissions
        .filter(p => p.authorized)
        .map(p => p.activity),
      enforcement_actions: activeEnforcement,
      confidence: bestMatch.confidence,
      data_source: 'FCA_REGISTRY',
      collected_at: new Date()
    };
  } catch (error) {
    console.error(`FCA lookup failed for ${firm.name}:`, error);
    throw new FCARuntimeError(`FCA verification failed: ${error.message}`);
  }
}
```

---

## 🧪 Test Cases (10+ scenarios)

### Test 1: Valid Authorized Firm
```
Input: { name: "FTMO Limited", country: "GB" }
Expected:
  - Status: CONFIRMED
  - Confidence: ≥0.95
  - Permissions: ["DRVSTR", "EDDCAS"]
  - Enforcement: 0
```

### Test 2: Suspended Firm
```
Input: { name: "SuspendedFirm", country: "GB" }
Expected:
  - Status: SUSPENDED
  - Confidence: ≥0.85
  - Enforcement: ≥1 active
```

### Test 3: Non-existent Firm
```
Input: { name: "FakeCompany XYZ", country: "GB" }
Expected:
  - Status: REJECTED
  - Confidence: <0.70
```

### Test 4: Name Variation Match
```
Input: { name: "FTMO Ltd", country: "GB" }
Expected:
  - Status: CONFIRMED (fuzzy match)
  - Confidence: ≥0.85
```

### Test 5: Multiple Matches
```
Input: { name: "Limited" }
Expected:
  - Returns top 5 matches
  - Selects best match by confidence
```

### Test 6: API Rate Limit
```
Input: 1,100 requests in sequence
Expected:
  - First 1,000 succeed
  - Request 1,001 gets 429
  - Retry after 60s succeeds
```

### Test 7: API Timeout
```
Input: API response >30s
Expected:
  - Timeout after 10s
  - Retry with exponential backoff
  - Fail gracefully after 3 retries
```

### Test 8: Network Error
```
Input: Connection refused
Expected:
  - Catch error
  - Retry 3x
  - Return error evidence
```

### Test 9: Invalid API Key
```
Input: Wrong API key
Expected:
  - 401 response
  - Fail immediately (no retry)
  - Alert: Invalid credentials
```

### Test 10: Enforcement Actions
```
Input: Firm with 3 active enforcement
Expected:
  - Status: CONFIRMED (still authorized)
  - Enforcement count: 3
  - Evidence includes action details
```

---

## 📊 Success Metrics

| Metric | Target | Acceptance |
|--------|--------|-----------|
| **Accuracy** | 95%+ match rate | >90% |
| **Speed** | <500ms avg | <2s |
| **Uptime** | 99.5% availability | >95% |
| **Coverage** | All UK firms | 80%+ |
| **Error Handling** | Zero crashes | Max 1 error/1000 |

---

## 🚀 Deployment Checklist

- [ ] FCA API credentials provisioned
- [ ] Client library implemented
- [ ] 10+ test cases passing
- [ ] Error handling complete
- [ ] Rate limiting implemented
- [ ] Caching strategy (24h TTL)
- [ ] Logging & monitoring setup
- [ ] Documentation complete
- [ ] Code review passed
- [ ] Integration tested with mock data
- [ ] Performance tested (1000 queries)
- [ ] Staging deployment verified
- [ ] Production ready

---

## 📝 Notes

- **API Throttling:** Implement adaptive throttling (back off if rate limit approaching)
- **Caching:** Cache results for 24h (firm data changes slowly)
- **Fallback:** If FCA API down, use cached data from last successful run
- **Monitoring:** Alert if >50 consecutive failures
- **Cost:** No cost (FCA API is free)

---

**Created:** Feb 1, 2026  
**Updated:** Feb 1, 2026  
**Status:** Specification Complete - Ready for Implementation
