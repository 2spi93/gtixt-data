# Phase 3 - OFAC/ONU Sanctions Integration
**Agent:** SSS (Sanctions Screening)  
**Timeline:** Week 3-4 (Mar 1-14, 2026)  
**Status:** PENDING ⏳

---

## 📋 Data Sources

### 1. OFAC SDN List
```
Source: https://www.treasury.gov/ofac
Type: Specially Designated Nationals List
Update Frequency: Daily
Format: CSV, XML
Size: ~8,000-10,000 records
Cost: Free
```

**Fields:**
- `ent_num`: Entity number (unique)
- `SDN_Name`: Full name
- `SDN_Type`: Individual | Organization | Aircraft | Vessel
- `Program`: PROGRAM_NAME
- `Title`: Job title (if individual)
- `Call_Sign`: Vessel call sign
- `Vessel_Type`: Type of vessel
- `Tonnage`: Ship tonnage
- `GRT`: Gross registered tonnage
- `Vessel_Flag`: Country flag
- `Vessel_Owner`: Owner name
- `Remarks`: Additional notes
- `List_Type`: OFAC SDN

### 2. Non-SDN Blocked Entities List
```
Source: https://www.treasury.gov/ofac
Type: Blocked list but not SDN
Update Frequency: Daily
Size: ~500-1,000 records
```

### 3. UN Sanctions Lists
```
Source: https://www.un.org/securitycouncil/sanctions
Types:
  - Al-Qaeda/ISIS lists
  - DPRK (North Korea)
  - Iran
  - Syria
  - Zimbabwe
Update Frequency: Weekly
Format: PDF, XML
Size: ~15,000+ records combined
```

### 4. EU Sanctions Lists
```
Source: https://webgate.ec.europa.eu/europeana-sanctions
Update Frequency: Weekly
Format: XML
Size: ~5,000+ records
```

---

## 🔧 Implementation Details

### Data Import Process

```
Weekly Batch Job:
1. Download latest OFAC CSV
2. Download latest UN/EU lists
3. Parse and normalize names
4. Insert into PostgreSQL
5. Build search indexes
6. Generate statistics
7. Run validation tests
```

### Name Matching Algorithm

```typescript
function calculateMatchScore(
  queryName: string,
  registeredName: string
): MatchResult {
  // Score components
  const exactMatch = queryName.toLowerCase() === registeredName.toLowerCase() 
    ? 100 
    : 0;
  
  // Levenshtein distance (up to 90)
  const levenshteinScore = calculateLevenshteinSimilarity(queryName, registeredName) * 90;
  
  // Fuzzy matching (soundex/metaphone, up to 70)
  const fuzzyScore = calculateFuzzySimilarity(queryName, registeredName) * 70;
  
  // Weighted average
  const finalScore = (exactMatch * 0.5) + (levenshteinScore * 0.3) + (fuzzyScore * 0.2);
  
  return {
    score: Math.round(finalScore),
    matchType: finalScore >= 95 
      ? 'EXACT' 
      : finalScore >= 80 
      ? 'PARTIAL' 
      : 'PHONETIC',
    confidence: finalScore / 100
  };
}
```

### Database Schema

```sql
CREATE TABLE ofac_sanctions (
  id SERIAL PRIMARY KEY,
  entity_number VARCHAR(20) UNIQUE,
  entity_name VARCHAR(500) NOT NULL,
  entity_type VARCHAR(50), -- Individual, Organization, Aircraft, Vessel
  program VARCHAR(100),
  list_source VARCHAR(50), -- OFAC_SDN, OFAC_BLOCKED, UN_DPRK, etc
  title VARCHAR(255),
  remarks TEXT,
  added_to_list DATE,
  last_updated TIMESTAMP,
  
  -- Search optimization
  name_lower VARCHAR(500),
  name_phonetic VARCHAR(500),
  
  -- Metadata
  country VARCHAR(2),
  keywords TEXT[],
  
  INDEX idx_entity_name (entity_name),
  INDEX idx_entity_number (entity_number),
  INDEX idx_program (program),
  INDEX idx_list_source (list_source),
  INDEX idx_name_lower (name_lower),
  FULLTEXT INDEX idx_keywords (keywords)
);

CREATE TABLE ofac_search_cache (
  id SERIAL PRIMARY KEY,
  query_name VARCHAR(500),
  best_match_id INT REFERENCES ofac_sanctions(id),
  match_score INT,
  match_type VARCHAR(20),
  searched_at TIMESTAMP,
  ttl TIMESTAMP,
  
  INDEX idx_query (query_name),
  INDEX idx_ttl (ttl)
);
```

### Data Structures

```typescript
interface OFACSanction {
  entity_id: string;
  entity_name: string;
  entity_type: 'INDIVIDUAL' | 'ORGANIZATION' | 'AIRCRAFT' | 'VESSEL';
  program: string;
  list_source: 'OFAC_SDN' | 'OFAC_BLOCKED' | 'UN_' | 'EU_';
  title?: string;
  remarks?: string;
  added_date: Date;
  last_updated: Date;
}

interface SanctionsMatch {
  found: boolean;
  match_type: 'EXACT' | 'PARTIAL' | 'PHONETIC' | 'NOT_FOUND';
  confidence: number; // 0-1
  sanctions: OFACSanction[];
  list_sources: string[];
}

// GPTI Evidence mapping
interface WatchlistMatchEvidence {
  evidence_type: 'WATCHLIST_MATCH';
  status: 'CONFIRMED' | 'REJECTED';
  firm_id: string;
  firm_name: string;
  match_type: 'EXACT' | 'PARTIAL' | 'PHONETIC';
  confidence: number;
  lists_matched: string[];
  sanctions_count: number;
  data_sources: string[];
  details: OFACSanction[];
  collected_at: Date;
}
```

### Integration in Agent

```typescript
async function screenSanctions(firm: Firm): Promise<WatchlistMatchEvidence> {
  try {
    // 1. Search all lists
    const matches = await sanctionsDb.search({
      name: firm.name,
      country: firm.country
    });
    
    // 2. Calculate confidence
    const bestMatch = matches.length > 0 
      ? matches[0] 
      : null;
    
    const confidence = bestMatch?.confidence || 0;
    
    if (confidence < 0.70) {
      return {
        evidence_type: 'WATCHLIST_MATCH',
        status: 'REJECTED',
        confidence: 0,
        // ...
      };
    }
    
    // 3. Return evidence
    return {
      evidence_type: 'WATCHLIST_MATCH',
      status: 'CONFIRMED',
      firm_id: firm.firm_id,
      firm_name: firm.name,
      match_type: bestMatch.match_type,
      confidence: confidence,
      lists_matched: [...new Set(matches.map(m => m.list_source))],
      sanctions_count: matches.length,
      data_sources: ['OFAC', 'UN', 'EU'],
      details: matches,
      collected_at: new Date()
    };
  } catch (error) {
    console.error(`Sanctions screening failed for ${firm.name}:`, error);
    throw new SanctionsScreeningError(`Failed: ${error.message}`);
  }
}
```

---

## 🧪 Test Cases (10+ scenarios)

### Test 1: Exact Match - SDN List
```
Input: "Semyon Vitalyevich Morozov"
Expected:
  - Match found: EXACT
  - Confidence: 100%
  - Source: OFAC_SDN
  - Program: UKRAINE
```

### Test 2: Partial Match - Organization
```
Input: "North Korean Trading"
Expected:
  - Match found: PARTIAL
  - Confidence: 85-95%
  - Source: UN_DPRK
```

### Test 3: Phonetic Match
```
Input: "Semion Morozoff" (spelling variation)
Expected:
  - Match found: PHONETIC
  - Confidence: 75-85%
  - Source: OFAC_SDN
```

### Test 4: No Match
```
Input: "Random Company LLC"
Expected:
  - Match found: NOT_FOUND
  - Confidence: 0%
```

### Test 5: Multiple Sanctions
```
Input: "Iran Bank" (matches multiple entities)
Expected:
  - Matches: 3-5 results
  - All from OFAC_SDN & UN_IRAN
  - Top match used for evidence
```

### Test 6: Cache Hit
```
Input: Same firm name twice in 1 hour
Expected:
  - First: Database query (~50ms)
  - Second: Cache hit (~5ms)
  - Cache TTL: 1 hour
```

### Test 7: Cache Expiry
```
Input: Firm name after 2 hours (1h TTL)
Expected:
  - Cache expired
  - Fresh database query
  - New result cached
```

### Test 8: Bulk Search Performance
```
Input: 1,000 firm names
Expected:
  - Complete in <30s
  - <30ms per lookup
  - No timeouts
```

### Test 9: Special Characters
```
Input: "Company & Associates Ltd."
Expected:
  - Normalized to "Company Associates Ltd"
  - Correct matches found
```

### Test 10: Case Insensitivity
```
Input: "semyon vitalyevich morozov" (all lowercase)
Expected:
  - Matches: EXACT
  - Confidence: 100%
  - Same as uppercase
```

---

## 📊 Success Metrics

| Metric | Target | Acceptance |
|--------|--------|-----------|
| **Coverage** | 8,000+ records | >7,000 |
| **Accuracy** | 99%+ correct matches | >95% |
| **False Positive** | <0.5% false alerts | <1% |
| **Search Speed** | <50ms per lookup | <200ms |
| **Bulk Performance** | <30ms avg/firm | <100ms |
| **Data Freshness** | Updated daily | Updated weekly |

---

## 📅 Update Process

```
Daily Cron Job (02:00 UTC):
1. Download OFAC CSV (10-15MB)
2. Parse 8,000+ records (~1s)
3. Compare with current DB
4. Insert new/updated records (~5s)
5. Rebuild search indexes (~30s)
6. Validate data integrity (~2s)
7. Generate statistics
8. Alert if changes >10%
```

---

## 🚀 Deployment Checklist

- [ ] PostgreSQL schema created
- [ ] Initial data import (OFAC, UN, EU)
- [ ] Search algorithm implemented
- [ ] 10+ test cases passing
- [ ] Bulk import working
- [ ] Caching layer operational
- [ ] Daily update job configured
- [ ] Performance tested (1,000 searches)
- [ ] Error handling complete
- [ ] Monitoring setup
- [ ] Documentation complete
- [ ] Code review passed
- [ ] Staging deployment verified
- [ ] Production ready

---

## 📝 Notes

- **Data Privacy:** Handle sanctions data securely
- **Legal Review:** Compliance verified with sanctions laws
- **Update Cadence:** Download at 02:00 UTC daily
- **Alerting:** Alert if match confidence >80%
- **Fallback:** Use cached data if download fails
- **Compliance:** Log all lookups (audit trail)

---

**Created:** Feb 1, 2026  
**Status:** Specification Complete - Ready for Data Import
