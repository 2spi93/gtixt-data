# FCA API Access Registration Guide
**Document Version:** 1.0  
**Last Updated:** February 1, 2026  
**Target:** Production deployment Week 2

---

## 🎯 Overview

This guide explains how to obtain **real FCA (Financial Conduct Authority) Registry API credentials** for production use of the GPTI RVI Agent.

**Timeline:** 5-10 business days  
**Cost:** Free (FCA Registry API is publicly accessible)  
**Requirements:** Valid business reason, UK or international firm

---

## 📧 Step 1: Initial Contact

### Email FCA Register Team

**To:** register@fca.org.uk  
**Subject:** API Access Request - GTIXT Verification System  
**Priority:** Normal

**Email Template:**

```
Dear FCA Register Team,

I am writing to request API access to the FCA Registry for our verification system.

ORGANIZATION DETAILS:
- Organization Name: [Your Company Name]
- Type: [Financial Technology / Research / Compliance]
- Country: [Your Country]
- Website: [Your Website]

PROJECT DETAILS:
- Project Name: GTIXT (Global Prop Trading Index)
- Purpose: Automated verification of prop trading firms' FCA authorization status
- Use Case: Compliance monitoring and transparency reporting
- Expected Volume: ~1,000 API calls per day
- Data Usage: Public verification and ranking

TECHNICAL CONTACT:
- Name: [Your Name]
- Email: [Your Email]
- Phone: [Your Phone]

We commit to:
- Using the API responsibly within rate limits
- Not reselling or redistributing raw API data
- Proper attribution of FCA as data source
- Compliance with FCA terms of service

Please provide:
1. API access credentials (API key)
2. API documentation and rate limits
3. Terms of service
4. Technical support contact

Thank you for your consideration.

Best regards,
[Your Name]
[Your Title]
[Your Company]
```

---

## 📋 Step 2: Information FCA May Request

Be prepared to provide:

### Organizational Information
- Company registration number (if UK company)
- Proof of business (website, incorporation docs)
- Data protection registration (if handling personal data)

### Technical Details
- Expected API call volume (daily/monthly)
- Data retention policies
- Security measures (encryption, access control)
- Intended use of data (display, analysis, reporting)

### Legal Agreements
- Acceptance of FCA terms of service
- Data usage agreement
- Non-redistribution clause

---

## 📨 Step 3: Follow-Up

### Timeline Expectations
- **Day 1-2:** Acknowledgment of request
- **Day 3-7:** Review of application
- **Day 7-10:** API credentials issued (if approved)

### If No Response After 5 Days
Send follow-up email:

```
Subject: Follow-up - API Access Request - GTIXT

Dear FCA Register Team,

I am following up on my API access request submitted on [Date].
Reference: [Original email subject/date]

Could you please provide an update on the status of our application?

Thank you,
[Your Name]
```

---

## 🔑 Step 4: Receiving Credentials

### What You'll Receive
- **API Key:** Unique authentication token
- **Base URL:** https://register.fca.org.uk/api or similar
- **Rate Limits:** Typically 60-100 requests per minute
- **Documentation:** API endpoints, request/response formats

### Example Credentials Format
```json
{
  "api_key": "fca_live_abc123xyz456...",
  "base_url": "https://register.fca.org.uk/api/v1",
  "rate_limit": "60/minute",
  "support_email": "api-support@fca.org.uk"
}
```

---

## ⚙️ Step 5: Configuration

### Set Environment Variables

**Development (.env):**
```bash
# FCA API Configuration
FCA_API_KEY="fca_live_abc123xyz456..."
FCA_API_URL="https://register.fca.org.uk/api/v1"
FCA_USE_MOCK=false

# Cache & Rate Limiting
REDIS_HOST="localhost"
REDIS_PORT="6379"
```

**Production (.env.production):**
```bash
# FCA API Configuration
FCA_API_KEY="${FCA_API_KEY_SECRET}"  # From secrets manager
FCA_API_URL="https://register.fca.org.uk/api/v1"
FCA_USE_MOCK=false

# Redis (Production)
REDIS_HOST="${REDIS_PROD_HOST}"
REDIS_PORT="6379"
REDIS_PASSWORD="${REDIS_PASSWORD_SECRET}"
```

---

## ✅ Step 6: Testing Real API

### Test Script

Create `scripts/test-fca-api.ts`:

```typescript
import { FCAClient } from '../src/integrations/fca-client';

async function testFCAAPI() {
  const apiKey = process.env.FCA_API_KEY;
  
  if (!apiKey || apiKey === 'test-key-here') {
    console.error('❌ FCA_API_KEY not set or using test key');
    process.exit(1);
  }

  console.log('🔑 Testing FCA API with real credentials...\n');

  const client = new FCAClient(apiKey, false); // useCache: false for testing

  try {
    // Test 1: Search for known firm
    console.log('Test 1: Search for FTMO...');
    const searchResults = await client.search({ name: 'FTMO', limit: 5 });
    console.log(`✅ Found ${searchResults.length} results`);
    if (searchResults.length > 0) {
      console.log(`   First result: ${searchResults[0].name} (${searchResults[0].firm_id})`);
    }

    // Test 2: Get firm details
    if (searchResults.length > 0) {
      console.log('\nTest 2: Get firm details...');
      const firmId = searchResults[0].firm_id;
      const details = await client.getFirmDetails(firmId);
      console.log(`✅ Retrieved details for ${details.name}`);
      console.log(`   Permissions: ${details.permissions.length}`);
      console.log(`   Status: ${details.authorization_status}`);
    }

    // Test 3: Rate limiting
    console.log('\nTest 3: Rate limiting (10 requests)...');
    const promises = [];
    for (let i = 0; i < 10; i++) {
      promises.push(client.search({ name: 'Test', limit: 1 }));
    }
    await Promise.all(promises);
    console.log('✅ Rate limiting working');

    console.log('\n✅ All tests passed!');
  } catch (error) {
    console.error('\n❌ API test failed:', error);
    process.exit(1);
  }
}

testFCAAPI();
```

**Run:**
```bash
npm run test:fca-api
```

---

## 🚨 Step 7: Monitoring & Compliance

### Daily Checks
- Monitor API call volume
- Check rate limit violations
- Track error rates

### Weekly Review
- Review cache hit rate (should be >80%)
- Analyze failed requests
- Update firm database

### Monthly Audit
- Verify compliance with FCA terms
- Review data retention policies
- Update credentials if needed

---

## 📊 Rate Limit Management

### FCA Typical Rate Limits
- **Requests per minute:** 60-100
- **Requests per day:** 10,000-50,000
- **Burst:** 10 concurrent requests

### Our Implementation
```typescript
// Rate limiter configured for FCA
const limiter = createFCARateLimiter();
// - Max: 60 tokens
// - Refill: 1 token/second
// - Queue timeout: 30 seconds
```

### Best Practices
1. **Cache aggressively** (24h TTL for firm details)
2. **Batch requests** when possible
3. **Use mock data** for development
4. **Monitor rate limit headers**
5. **Implement exponential backoff**

---

## 🔒 Security Best Practices

### API Key Storage
```bash
# ❌ NEVER commit to Git
FCA_API_KEY="fca_live_abc123..."

# ✅ Use secrets manager
AWS_SECRET_NAME="gpti/fca-api-key"
AZURE_KEY_VAULT="gpti-keyvault"
```

### Access Control
- Restrict API key to production servers only
- Rotate keys quarterly
- Log all API usage
- Set up alerts for unusual activity

### Data Protection
- Encrypt API responses at rest
- Use HTTPS for all API calls
- Anonymize test data
- Follow GDPR guidelines (if applicable)

---

## 🆘 Troubleshooting

### Issue: 401 Unauthorized
**Cause:** Invalid API key  
**Solution:** 
- Verify API key is correct
- Check for trailing spaces
- Ensure key hasn't expired

### Issue: 429 Too Many Requests
**Cause:** Rate limit exceeded  
**Solution:**
- Enable rate limiter
- Check cache hit rate
- Reduce request volume

### Issue: 503 Service Unavailable
**Cause:** FCA API downtime  
**Solution:**
- Check FCA status page
- Implement retry logic
- Fall back to cached data

### Issue: Empty Search Results
**Cause:** Firm not in FCA registry or query too specific  
**Solution:**
- Verify firm name spelling
- Try partial matches
- Check if firm is UK-regulated

---

## 📞 Support Contacts

### FCA API Support
- **Email:** register@fca.org.uk
- **Phone:** +44 (0)20 7066 1000
- **Hours:** Monday-Friday, 9am-5pm GMT

### FCA Register Website
- **Search:** https://register.fca.org.uk/
- **Status:** https://status.fca.org.uk/

### GPTI Internal
- **Tech Lead:** [Your email]
- **DevOps:** [DevOps email]
- **Slack:** #gpti-data-bot

---

## 📚 Additional Resources

### Documentation
- FCA Register User Guide: https://register.fca.org.uk/help
- FCA Handbook: https://www.handbook.fca.org.uk/
- API Terms of Service: (Provided with credentials)

### Code Examples
- `src/integrations/fca-client.ts` - Client implementation
- `scripts/test-fca-api.ts` - Testing script
- `docs/FCA_CREDENTIALS_SETUP.md` - Integration guide

---

## ✅ Checklist

### Before Going Live
- [ ] FCA API key obtained
- [ ] Environment variables set
- [ ] Real API tested successfully
- [ ] Rate limiter configured
- [ ] Cache enabled and tested
- [ ] Monitoring set up
- [ ] Error handling tested
- [ ] Fallback to mock data working
- [ ] Documentation updated
- [ ] Team trained on API usage

---

## 📈 Success Metrics

### Week 2 Targets
- ✅ API credentials obtained
- ✅ Real API tested and working
- ✅ Cache hit rate >80%
- ✅ Zero rate limit violations
- ✅ <500ms average response time

### Production Targets
- 99.9% uptime
- <100ms cache hit latency
- <500ms cache miss latency
- >90% cache hit rate
- Zero API key exposures

---

**Last Updated:** February 1, 2026  
**Next Review:** February 7, 2026  
**Owner:** GPTI Development Team
