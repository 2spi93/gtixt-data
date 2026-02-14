# Phase 3 - SEC EDGAR Integration
**Agents:** IRS (Submission Reviews) + IIP (IOSCO Reporting)  
**Timeline:** Week 5-6 (Mar 15-28, 2026)  
**Status:** PENDING ⏳

---

## 📋 SEC EDGAR API

### Authentication
```
API Type: RESTful (no auth required for public data)
Base URL: https://data.sec.gov
Rate Limit: 10 requests/second (after delays)
Retry Strategy: Exponential backoff with delay
```

### Key Endpoints

#### 1. Company Search by Name
```
GET /cgi-bin/browse-edgar?action=getcompany&company={name}&type=20-F&dateb=&owner=exclude&count=40&search_text=

Response Format: HTML (parse using cheerio/jsdom)
OR use CIK lookup first
```

#### 2. CIK Lookup
```
GET /cgi-bin/browse-edgar?action=getcompany&company={name}&CIK=&type=20-F&dateb=&owner=exclude&match=contains

Returns:
- CIK: Central Index Key (10-digit)
- Company Name
- SIC: Standard Industrial Classification
```

#### 3. Company Facts (JSON)
```
GET /api/xrls/companyfacts/CIK{cik}.json

Response:
{
  "cik": 1018724,
  "entityName": "ORACLE CORP",
  "facts": {
    "us-gaap": {
      "Assets": [
        {
          "end": "2024-05-31",
          "val": 417549000000,
          "filed": "2024-08-22",
          "form": "10-Q",
          "fy": 2024
        }
      ]
    }
  }
}
```

#### 4. Filings (20-F for foreign companies)
```
GET /cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=20-F&dateb=&owner=exclude&count=100

Returns:
- Filing date
- Accession number
- Form type
- Filing URL
```

#### 5. Full Filing Text
```
GET /Archives/edgar/container-summary-{accession}.json

Response:
{
  "filing": {
    "date": "2024-06-28",
    "items": 5,
    "files": [
      {
        "name": "frmt20f.htm",
        "type": "document",
        "size": 5432100
      }
    ]
  }
}
```

---

## 🔧 Implementation Details

### Data Structures

```typescript
interface CompanyFiling {
  cik: string;
  company_name: string;
  form_type: '20-F' | '10-K' | '10-Q';
  filing_date: Date;
  accession_number: string;
  period_of_report: Date;
  url: string;
  filing_status: 'accepted' | 'incomplete';
  items: string[]; // e.g., ["Item 1", "Item 1A"]
}

interface CompanyFacts {
  cik: string;
  company_name: string;
  assets: number;
  liabilities: number;
  stockholders_equity: number;
  revenue: number;
  net_income: number;
  last_period: Date;
}

interface SECSubmissionEvidence {
  evidence_type: 'SUBMISSION_VERIFICATION';
  status: 'CONFIRMED' | 'REJECTED' | 'PENDING';
  firm_id: string;
  firm_name: string;
  cik: string;
  company_name: string;
  latest_filing_date: Date;
  filing_type: '20-F' | 'NOT_FOUND';
  filing_status: string;
  periods_filed: number; // last 3 years
  enforcement_actions: number;
  data_source: 'SEC_EDGAR';
  collected_at: Date;
}
```

### Integration Points

```typescript
async function verifySecSubmission(firm: Firm): Promise<SECSubmissionEvidence> {
  try {
    // 1. Search for CIK by company name
    const cikResult = await secClient.searchByCIK(firm.name);
    
    if (!cikResult || !cikResult.cik) {
      return {
        evidence_type: 'SUBMISSION_VERIFICATION',
        status: 'REJECTED',
        firm_name: firm.name,
        // ...
      };
    }
    
    // 2. Get company facts
    const facts = await secClient.getCompanyFacts(cikResult.cik);
    
    // 3. Search for 20-F filings (foreign issuers)
    const filings = await secClient.getFilings(cikResult.cik, '20-F');
    
    if (filings.length === 0) {
      return {
        evidence_type: 'SUBMISSION_VERIFICATION',
        status: 'PENDING', // Company exists but no 20-F
        cik: cikResult.cik,
        company_name: cikResult.company_name,
        periods_filed: 0,
        filing_type: 'NOT_FOUND',
        // ...
      };
    }
    
    // 4. Get latest filing details
    const latestFiling = filings[0];
    const filingDetails = await secClient.getFilingDetails(
      latestFiling.accession_number
    );
    
    // 5. Check for enforcement actions
    const enforcement = await checkEnforcement(cikResult.cik);
    
    // 6. Return evidence
    return {
      evidence_type: 'SUBMISSION_VERIFICATION',
      status: 'CONFIRMED',
      firm_id: firm.firm_id,
      firm_name: firm.name,
      cik: cikResult.cik,
      company_name: cikResult.company_name,
      latest_filing_date: latestFiling.filing_date,
      filing_type: '20-F',
      filing_status: latestFiling.filing_status,
      periods_filed: filings.length,
      enforcement_actions: enforcement.count,
      data_source: 'SEC_EDGAR',
      collected_at: new Date()
    };
  } catch (error) {
    console.error(`SEC lookup failed for ${firm.name}:`, error);
    throw new SECLookupError(`Failed: ${error.message}`);
  }
}
```

---

## 🧪 Test Cases (10+ scenarios)

### Test 1: Foreign Company with 20-F
```
Input: Oracle Corporation (ORCL)
Expected:
  - Status: CONFIRMED
  - Form: 20-F (if foreign)
  - Filing date: Last year
  - Periods: 3+
```

### Test 2: Non-existent Company
```
Input: "Fake Company LLC"
Expected:
  - Status: REJECTED
  - CIK: Not found
```

### Test 3: Company with Enforcement
```
Input: Company with SEC enforcement action
Expected:
  - Status: CONFIRMED
  - Enforcement count: ≥1
```

### Test 4: Recent Filing
```
Input: Company with filing <30 days old
Expected:
  - Filing status: accepted
  - Recent update indicator
```

### Test 5: Name Variation
```
Input: "Berkshire Hathaway Inc" vs "Berkshire Hathaway Inc."
Expected:
  - Same CIK found
  - Correct matching
```

### Test 6: Bulk CIK Lookup
```
Input: 100 company names
Expected:
  - All lookups complete <60s
  - No rate limit hits (10/sec)
```

### Test 7: API Rate Limiting
```
Input: 15 requests/second
Expected:
  - First 10 succeed immediately
  - Requests 11-15 delayed
  - No errors
```

### Test 8: Connection Timeout
```
Input: SEC API unreachable
Expected:
  - Retry with backoff
  - Fail after 3 attempts
  - Error evidence
```

### Test 9: Partial Data
```
Input: Company with incomplete facts
Expected:
  - Use available data
  - Mark missing fields as null
  - Status: CONFIRMED (if CIK found)
```

### Test 10: Financial Data
```
Input: Company with financial facts
Expected:
  - Assets, revenue, net income extracted
  - Used for risk scoring (Phase 4)
```

---

## 📊 Success Metrics

| Metric | Target | Acceptance |
|--------|--------|-----------|
| **Lookup Speed** | <1s per company | <3s |
| **Accuracy** | 99% correct CIK | >95% |
| **Coverage** | 90% of public firms | >70% |
| **API Uptime** | 99.5% | >95% |
| **Rate Compliance** | <10 req/sec | No violations |

---

## 🚀 Deployment Checklist

- [ ] SEC API access configured
- [ ] CIK lookup implemented
- [ ] 20-F filing search working
- [ ] Company facts parser ready
- [ ] 10+ test cases passing
- [ ] Rate limiting implemented
- [ ] Error handling complete
- [ ] Caching for CIK (7 day TTL)
- [ ] Monitoring setup
- [ ] Documentation complete
- [ ] Code review passed
- [ ] Staging deployment verified
- [ ] Production ready

---

**Created:** Feb 1, 2026  
**Status:** Specification Complete - Ready for Implementation
