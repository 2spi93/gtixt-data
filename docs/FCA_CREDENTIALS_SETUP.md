# FCA API Credentials Integration Guide

## 🔐 Setup Real FCA Registry API Access

### **Prerequisites**
- FCA Registry account with API access
- API Key from FCA
- Whitelisted IP addresses (if required)

---

## **Step-by-Step Integration**

### **1. Obtain Credentials**

Contact FCA Registry team:
- **Email:** register@fca.org.uk
- **Portal:** https://register.fca.org.uk/s/
- **Request:** API access for firm verification

**Required Information:**
- Organization name: GPTI
- Use case: Forex broker verification
- Expected volume: 1,000-10,000 queries/day
- Data retention policy: 24-hour cache

---

### **2. Configure Environment**

#### **Production (Linux Server)**
```bash
# SSH into production server
ssh ubuntu@your-production-server

# Add to system environment
sudo nano /etc/environment

# Add this line:
FCA_API_KEY="your-actual-api-key-here"

# Reload environment
source /etc/environment

# Verify
echo $FCA_API_KEY
```

#### **Development (.env file)**
```bash
cd /opt/gpti/gpti-data-bot

# Create .env file
cat > .env << 'EOF'
# FCA Registry API
FCA_API_KEY=your-dev-api-key-here
FCA_BASE_URL=https://register.fca.org.uk/api
FCA_TIMEOUT_MS=10000
FCA_MAX_RETRIES=3

# Rate Limiting (if known)
FCA_RATE_LIMIT_PER_MINUTE=60
FCA_RATE_LIMIT_PER_HOUR=1000
EOF

# Add .env to .gitignore
echo ".env" >> .gitignore
```

#### **Docker/Kubernetes**
```yaml
# docker-compose.yml or k8s secret
environment:
  - FCA_API_KEY=${FCA_API_KEY}
  - FCA_BASE_URL=https://register.fca.org.uk/api
```

---

### **3. Verify Connection**

```bash
cd /opt/gpti/gpti-data-bot

# Test with a known firm
node -e "
const { FCAClient } = require('./dist/integrations/fca-client.js');
const client = new FCAClient(process.env.FCA_API_KEY);

client.search({ name: 'FTMO', limit: 1 })
  .then(results => {
    console.log('✅ FCA API Connected!');
    console.log('Results:', results.length);
    if (results.length > 0) {
      console.log('First firm:', results[0].name);
    }
  })
  .catch(err => {
    console.error('❌ FCA API Error:', err.message);
  });
"
```

Expected output:
```
✅ FCA API Connected!
Results: 1
First firm: FTMO Limited
```

---

### **4. Update Application Code** (Optional)

If base URL differs from default:

```typescript
// src/integrations/fca-client.ts
export class FCAClient {
  private baseUrl = process.env.FCA_BASE_URL || 'https://register.fca.org.uk/api';
  // ... rest of code
}
```

---

### **5. Run Tests with Real API**

```bash
cd /opt/gpti/gpti-data-bot

# Set env var for test session
export FCA_API_KEY="your-api-key"

# Run tests
npm test

# Expected: All 12 tests should pass
# Note: Some firms in mock data may not exist in real FCA registry
```

---

### **6. Monitor & Validate**

#### **Check API Usage**
```bash
# View agent logs
tail -f logs/gpti-data-bot.log | grep "\[RVI\]"

# Expected output:
# [RVI] Verified FTMO Limited in 234ms - Status: CONFIRMED
# [RVI] Verified XM Global in 189ms - Status: CONFIRMED
```

#### **Validate Data Quality**
```bash
# Check data source in database
psql -d gpti -c "
  SELECT 
    firm_name,
    data_source,
    confidence,
    collected_at
  FROM license_verification_evidence
  WHERE data_source = 'FCA_REGISTRY'
  LIMIT 10;
"
```

Expected:
```
 firm_name      | data_source  | confidence | collected_at
----------------+--------------+------------+-------------------
 FTMO Limited   | FCA_REGISTRY | 1.00       | 2026-02-01 15:30
 XM Global Ltd  | FCA_REGISTRY | 0.95       | 2026-02-01 15:31
```

---

### **7. Fallback Strategy**

If FCA API is unavailable:

```typescript
// Automatic fallback in RVIAgent
if (!apiKey) {
  console.warn('FCA_API_KEY not set, using mock client');
  this.fcaClient = new FCAClientMock();
}

// Or handle API errors gracefully
try {
  const results = await fcaClient.search(params);
} catch (error) {
  // Fall back to cached data or manual review
  console.error('FCA API error, using fallback:', error);
  return getCachedData(firmName);
}
```

---

## 🚨 Troubleshooting

### **Issue: "FCA_API_KEY not set"**
```bash
# Check if variable is set
env | grep FCA_API_KEY

# If not found:
export FCA_API_KEY="your-key"

# Or add to ~/.bashrc for persistence
echo 'export FCA_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc
```

### **Issue: "Connection timeout"**
```bash
# Test network connectivity
curl -v https://register.fca.org.uk/api/v1/health

# Check firewall rules
sudo ufw status

# Add FCA domain to whitelist if needed
```

### **Issue: "Rate limit exceeded"**
```bash
# Wait and retry with exponential backoff
# (Already implemented in FCAClient)

# Or reduce query frequency in Prefect flow
# Edit flow schedule: daily → weekly
```

### **Issue: "Invalid API key"**
```bash
# Verify key format
echo $FCA_API_KEY

# Re-generate key from FCA portal
# Update environment variable
```

---

## 📊 Expected Performance

| Metric | Mock Client | Real FCA API |
|--------|-------------|--------------|
| **Latency** | <10ms | 100-500ms |
| **Throughput** | Unlimited | 60/min (estimated) |
| **Data Freshness** | Static | Real-time |
| **Cost** | Free | Per-query fee (TBD) |

---

## ✅ Verification Checklist

- [ ] FCA API key obtained
- [ ] Environment variable set (`FCA_API_KEY`)
- [ ] Connection test successful
- [ ] Tests passing with real API (12/12)
- [ ] Logging configured
- [ ] Monitoring alerts set up
- [ ] Fallback strategy tested
- [ ] Rate limiting configured
- [ ] Documentation updated

---

## 📞 Support Contacts

**FCA Registry Support:**
- Email: register@fca.org.uk
- Phone: +44 (0)20 7066 1000
- Portal: https://register.fca.org.uk/s/

**Internal Team:**
- DevOps: Configure environment variables
- Data Team: Validate data quality
- Compliance: Review API usage policy

---

**Status:** Ready for integration  
**Priority:** High  
**Estimated Time:** 2-4 hours  
**Dependencies:** FCA API credentials
