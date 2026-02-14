# Phase 3 - TrustPilot API Integration
**Agent:** FRP (Reputation & Payout Risk)  
**Timeline:** Week 7-8 (Mar 29 - Apr 11, 2026)  
**Status:** PENDING ⏳

---

## 📋 TrustPilot API

### Authentication
```
Auth Type: OAuth 2.0
Grant Type: Client Credentials
Token URL: https://api.trustpilot.com/v1/oauth/oauth-token
Scope: ratings:read, reviews:read
Rate Limit: 10,000 requests/hour
Retry Strategy: Exponential backoff (3x with 1s, 2s, 5s delays)
```

### Rate Limits
```
Calls per minute: 20-30 (recommend 5-10 safe)
Calls per hour: 10,000
Burst capacity: 100 calls/minute
Cost: Free tier (public data)
```

### Key Endpoints

#### 1. Business Search
```
GET /v1/business-units/search?query={business_name}&country={country_code}

Response (200 OK):
{
  "businessUnits": [
    {
      "id": "614c2e2c92e80400a9e0a4a9",
      "name": "FTMO",
      "displayName": "FTMO",
      "website": "https://ftmo.com",
      "countryCode": "CZ",
      "industryId": "5568e4b05ead45f288bd0101",
      "industryName": "Financial Services",
      "stars": 4.6,
      "numberOfReviews": {
        "1Star": 124,
        "2Star": 89,
        "3Star": 201,
        "4Star": 512,
        "5Star": 1205
      },
      "links": {
        "businessUnit": "https://www.trustpilot.com/review/ftmo.com"
      }
    }
  ]
}
```

#### 2. Business Details
```
GET /v1/business-units/{businessUnitId}

Response:
{
  "id": "614c2e2c92e80400a9e0a4a9",
  "name": "FTMO",
  "website": "https://ftmo.com",
  "countryCode": "CZ",
  "businessType": "Online Business",
  "industryId": "5568e4b05ead45f288bd0101",
  "stars": 4.6,
  "numberOfReviews": 2131,
  "numberOfReviewsLastYear": 523,
  "numberOfReviewsLastMonth": 45,
  "avgRating": 4.6,
  "ratingDistribution": {
    "1Star": { "count": 124, "percentage": 5.8 },
    "2Star": { "count": 89, "percentage": 4.2 },
    "3Star": { "count": 201, "percentage": 9.4 },
    "4Star": { "count": 512, "percentage": 24.0 },
    "5Star": { "count": 1205, "percentage": 56.5 }
  },
  "trustScore": 98
}
```

#### 3. Reviews (Paginated)
```
GET /v1/business-units/{businessUnitId}/reviews?pageSize=20&page=0&orderBy=recency

Response:
{
  "reviews": [
    {
      "id": "64f2e3c4d8e9f1a2b3c4d5e6",
      "rating": 5,
      "title": "Excellent trading platform",
      "text": "Great experience with FTMO...",
      "consumer": {
        "id": "64f2e3c4d8e9f1a2b3c4d5e7",
        "displayName": "John D.",
        "countryCode": "GB"
      },
      "createdAt": "2024-01-15T10:30:00Z",
      "updatedAt": "2024-01-15T10:30:00Z",
      "isVerified": true,
      "numHelpful": 45,
      "numNotHelpful": 2,
      "companyReply": null
    },
    // ... more reviews
  ],
  "pagination": {
    "pageNumber": 0,
    "pageSize": 20,
    "totalResults": 2131,
    "totalPages": 107
  }
}
```

#### 4. Review Sentiment Analysis (using NLP)
```
Manual NLP Processing:
- Analyze review text
- Extract sentiment: positive / neutral / negative
- Identify common complaint keywords
- Track sentiment trends
```

---

## 🔧 Implementation Details

### Data Structures

```typescript
interface TrustPilotBusiness {
  id: string;
  name: string;
  website: string;
  country: string;
  industry: string;
  overall_rating: number; // 1-5
  total_reviews: number;
  reviews_last_year: number;
  reviews_last_month: number;
  rating_distribution: {
    one_star: number;
    two_star: number;
    three_star: number;
    four_star: number;
    five_star: number;
  };
  trust_score: number; // 0-100
}

interface TrustPilotReview {
  id: string;
  rating: 1 | 2 | 3 | 4 | 5;
  title: string;
  text: string;
  consumer_country: string;
  created_at: Date;
  is_verified: boolean;
  helpful_count: number;
  not_helpful_count: number;
  sentiment?: 'positive' | 'neutral' | 'negative';
}

interface SentimentAnalysisResult {
  text: string;
  sentiment: 'positive' | 'neutral' | 'negative';
  confidence: number; // 0-1
  keywords: string[];
  score: number; // -1 to 1
}

interface ReputationRiskEvidence {
  evidence_type: 'REPUTATION_RISK';
  status: 'CONFIRMED' | 'REJECTED';
  firm_id: string;
  firm_name: string;
  overall_rating: number;
  total_reviews: number;
  rating_trend: number; // change in last 30 days
  negative_sentiment_percentage: number;
  common_complaints: string[];
  trust_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
  data_source: 'TRUSTPILOT';
  collected_at: Date;
}
```

### Sentiment Analysis Pipeline

```typescript
async function analyzeReputationRisk(firm: Firm): Promise<ReputationRiskEvidence> {
  try {
    // 1. Search TrustPilot business
    const business = await trustpilotClient.search(firm.name, firm.country);
    
    if (!business) {
      return {
        evidence_type: 'REPUTATION_RISK',
        status: 'REJECTED',
        risk_level: 'UNKNOWN',
        // ...
      };
    }
    
    // 2. Get business details
    const details = await trustpilotClient.getDetails(business.id);
    
    // 3. Fetch recent reviews (last 30 days)
    const recentReviews = await trustpilotClient.getReviews(
      business.id,
      { 
        limit: 100,
        sort: 'recent'
      }
    );
    
    // 4. Analyze sentiment for each review
    const analyzedReviews = await Promise.all(
      recentReviews.map(async (review) => ({
        ...review,
        sentiment: await sentimentAnalyzer.analyze(review.text)
      }))
    );
    
    // 5. Calculate metrics
    const totalReviews = analyzedReviews.length;
    const negativeCount = analyzedReviews.filter(
      r => r.sentiment === 'negative'
    ).length;
    const negativePercentage = (negativeCount / totalReviews) * 100;
    
    // 6. Extract common complaints
    const complaints = extractKeywords(
      analyzedReviews.filter(r => r.sentiment === 'negative')
    );
    
    // 7. Calculate trend (vs 60 days ago)
    const oldRating = details.rating_distribution.avg_60days || details.overall_rating;
    const ratingTrend = details.overall_rating - oldRating;
    
    // 8. Determine risk level
    let riskLevel = 'LOW';
    if (details.overall_rating < 3.0 || negativePercentage > 30) riskLevel = 'HIGH';
    else if (details.overall_rating < 3.5 || negativePercentage > 15) riskLevel = 'MEDIUM';
    
    // 9. Return evidence
    return {
      evidence_type: 'REPUTATION_RISK',
      status: details.overall_rating >= 3.0 ? 'REJECTED' : 'CONFIRMED',
      firm_id: firm.firm_id,
      firm_name: firm.name,
      overall_rating: details.overall_rating,
      total_reviews: details.total_reviews,
      rating_trend: ratingTrend,
      negative_sentiment_percentage: negativePercentage,
      common_complaints: complaints,
      trust_score: details.trust_score,
      risk_level: riskLevel,
      data_source: 'TRUSTPILOT',
      collected_at: new Date()
    };
  } catch (error) {
    console.error(`TrustPilot lookup failed for ${firm.name}:`, error);
    throw new TrustPilotError(`Failed: ${error.message}`);
  }
}
```

---

## 🧪 Test Cases (10+ scenarios)

### Test 1: High Rating Business
```
Input: FTMO (rating 4.6, 2,100+ reviews)
Expected:
  - Status: REJECTED (low risk)
  - Risk Level: LOW
  - Trust Score: >90
```

### Test 2: Low Rating Business
```
Input: Business with 2.1 rating
Expected:
  - Status: CONFIRMED (high risk)
  - Risk Level: HIGH
  - Negative %: >30%
```

### Test 3: Negative Trend
```
Input: Rating dropped 1.0 points in 30 days
Expected:
  - Rating Trend: -1.0
  - Risk Level: MEDIUM
  - Alert: Rating declining
```

### Test 4: High Negative Sentiment
```
Input: 40% negative reviews
Expected:
  - Negative %: 40%
  - Risk Level: HIGH
  - Common complaints: extracted
```

### Test 5: No Reviews
```
Input: Business not on TrustPilot
Expected:
  - Status: REJECTED
  - Reviews: 0
```

### Test 6: Recent Reviews
```
Input: Business with 50+ reviews last month
Expected:
  - Reviews last month: 50+
  - Trend: calculated
  - High volume indicator
```

### Test 7: Sentiment Variation
```
Input: Mix of positive and negative reviews
Expected:
  - Sentiment distribution calculated
  - Both positive & negative identified
  - Balanced assessment
```

### Test 8: Multi-language Reviews
```
Input: Reviews in English, German, Czech
Expected:
  - All languages analyzed
  - Sentiment extracted correctly
  - Aggregated results
```

### Test 9: API Rate Limiting
```
Input: 100 rapid requests
Expected:
  - First 10/minute succeed
  - Remaining queued
  - No errors
```

### Test 10: Verified Reviews
```
Input: Filter by verified reviews only
Expected:
  - Only verified reviews analyzed
  - More trustworthy sentiment
  - Separate count from all reviews
```

---

## 📊 Success Metrics

| Metric | Target | Acceptance |
|--------|--------|-----------|
| **Lookup Speed** | <2s per business | <5s |
| **Sentiment Accuracy** | 85%+ | >75% |
| **Coverage** | 80% of businesses | >60% |
| **API Uptime** | 99%+ | >95% |
| **Review Volume** | 100+ reviews/business | 50+ minimum |

---

## 🚀 Deployment Checklist

- [ ] TrustPilot API credentials provisioned
- [ ] OAuth token flow implemented
- [ ] Business search working
- [ ] Review fetching implemented
- [ ] Sentiment analyzer trained/integrated
- [ ] 10+ test cases passing
- [ ] Rate limiting implemented
- [ ] Caching for business data (7 day TTL)
- [ ] Error handling complete
- [ ] Monitoring setup
- [ ] Documentation complete
- [ ] Code review passed
- [ ] Staging deployment verified
- [ ] Production ready

---

## 📝 Notes

- **Sentiment:** Use pre-trained model (e.g., HuggingFace DistilBERT)
- **Caching:** Cache business data for 7 days (changes slowly)
- **Fallback:** If TrustPilot API down, use cached data
- **Privacy:** Don't store review text long-term (PII concern)
- **Compliance:** Follow TrustPilot ToS for API usage
- **Updates:** Daily check for new reviews

---

**Created:** Feb 1, 2026  
**Status:** Specification Complete - Ready for Implementation
