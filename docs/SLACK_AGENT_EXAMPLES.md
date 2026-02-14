# 💬 Slack Agent Interaction Examples

## 1. Questions de Base

### Agent A - Collecte de Données Réglementaires

```
User: @GPTI Agent A: Qui est Apple Inc?
Bot: 🤖 Agent A
     Question: Qui est Apple Inc?
     Réponse: Apple Inc. est une multinational technology company basée 
              à Cupertino, Californie. Elle est régulée par la SEC (Securities 
              and Exchange Commission). Dernière information FCA: Entreprise 
              de confiance avec historique clean.
     📊 Sources: FCA, SEC EDGAR, OFAC | ⏱️ 1.23s | 📦 Snapshots: ✅
```

### Agent RVI - Analyse Risque d'Investissement

```
User: Agent RVI: Quel est le profil de risque de Goldman Sachs?
Bot: 🤖 Agent RVI
     Question: Quel est le profil de risque de Goldman Sachs?
     Réponse: Goldman Sachs a un profil de risque modéré selon les données 
              SEC. Ratings: BBB+ par S&P. Ratios financiers stables. 
              Recommandation: HOLD.
     📊 Sources: SEC Filings, Bloomberg | ⏱️ 2.45s | 📦 Snapshots: ✅
```

### Agent SSS - Surveillance Sanctions

```
User: DM to bot: Vérifier si Deutsche Bank est en liste OFAC
Bot: 🤖 Agent SSS
     Question: Vérifier si Deutsche Bank est en liste OFAC
     Réponse: Deutsche Bank n'est PAS en liste OFAC ni sanction list. 
              Status: ✅ CLEAN. Dernier scan: Aujourd'hui.
     📊 Sources: OFAC Sanctions, Scam Database | ⏱️ 0.89s | 📦 Snapshots: ✅
```

## 2. Questions Complexes

### Multi-agent Investigation

```
User: @GPTI: Faire une analyse complète de JPMorgan Chase

Agent A Response:
- Employer count: 300,000+
- HQ: New York, USA
- SEC CIK: 0001018724
- Founded: 1871

Agent RVI Response:
- Market Cap: $400B
- PE Ratio: 12.5
- Risk Rating: Moderate
- 5-year Return: +8.5% annually

Agent SSS Response:
- OFAC Status: CLEAN ✅
- Fraud Reports: 0
- Sanctions: None
- Risk Level: LOW

Agent REM Response:
- FCA Registration: Approved ✅
- Regulatory Status: Full Compliance
- Last Audit: 2024-01-15
- Next Audit: 2025-01-15
```

### Monitoring Spécifique

```
User: @GPTI Agent B: Valider les données de Barclays Bank

Bot: 🤖 Agent B
     Question: Valider les données de Barclays Bank
     Réponse: 
     ✅ Sources validées: SEC (3 filings), FCA (regulatory), OFAC (clean)
     ✅ Data Quality: 98% complète
     ✅ Consistency check: PASSED
     ⚠️  Warning: Equity data 2 jours old, snapshot refresh recommended
     
     📊 Sources: Trustpilot, Reviews internes | ⏱️ 3.12s | 📦 Snapshots: ✅
```

## 3. Cas d'Usage Pratiques

### Due Diligence Rapide

```
User: @GPTI: Je dois investiguer NextBank Ltd rapidement
Bot:
  Agent MIS: Registered as NextBank Ltd, Company #12345678
  Agent A: SEC reporting status: Not found (probably non-US)
  Agent RVI: No public market data available
  Agent SSS: ✅ No sanctions, clean status
  Agent REM: No UK FCA registration found
  
  → Conclusion: Likely small/regional bank, not major regulatory concern
```

### Risk Alert Investigation

```
User: @GPTI Agent RVI: L'index de risque pour Morgan Stanley a augmenté, pourquoi?

Bot: 🤖 Agent RVI
     Question: Pourquoi le risque pour Morgan Stanley a augmenté?
     Réponse: 
     1. Debt-to-equity ratio augmenté de 0.8 → 0.92
     2. Interest rate exposure augmentée de 12% → 15%
     3. Recent SEC filing révèle investissements en tech volatiles
     4. Market sentiment: Mixed (3.2/5 stars sur Trustpilot)
     
     Recommandation: Monitor closely, potential regulatory review incoming
```

### Compliance Check

```
User: @GPTI Agent REM: Mon client, Société Générale, est-il en conformité réglementaire?

Bot: 🤖 Agent REM
     Réponse:
     ✅ FCA Registration: Approved (UK Branch)
     ✅ Latest PRA Notice: Compliant
     ✅ Capital Requirements: Met
     ✅ AML/KYC: Current
     ⚠️  Pending: Data Protection review (deadline: 2025-06-30)
     
     Overall Status: COMPLIANT with warnings
```

## 4. Shortcuts & Patterns

### Shorthand Commands

```
# Same as "Agent A:"
User: A: What's the status of XYZ Corp?

# Default to Agent A if not specified
User: @GPTI: Status update on my watch list

# Query by company ID
User: @GPTI: SEC CIK 0000051143

# Boolean queries
User: Agent SSS: Is Gazprom sanctioned?
```

### Thread Conversations

```
User (Thread): @GPTI: Tell me about Apple
Bot: [Long response with full details]

User (Thread Reply): Agent RVI: And what about the risk?
Bot: [Contextual follow-up in same thread]

User (Thread Reply): Any recent FCA notices?
Bot: [Related query, maintains context]
```

## 5. Error Handling

### Unknown Agent

```
User: Agent XYZ: Qui est Tesla?
Bot: ❌ Erreur
     Agent XYZ non reconnu. 
     Agents disponibles: A, B, RVI, SSS, REM, IRS, FRP, MIS
```

### Ollama Timeout

```
User: Agent A: Detailed analysis of Warren Buffett's portfolio
Bot: ❌ Erreur
     Le serveur d'IA (Ollama) est indisponible
     Essayez dans quelques secondes ou contactez l'administrateur
```

### No Snapshot Data

```
User: Agent A: Tell me about company "XXXYZZZ"
Bot: 🤖 Agent A
     Question: Tell me about company "XXXYZZZ"
     Réponse: Je n'ai pas trouvé d'information sur cette entreprise 
              dans les snapshots disponibles.
     
     ⚠️ Data context: Snapshots indisponibles
```

## 6. Response Format Examples

### Quick Response

```
Bot: 🤖 Agent B
     ✅ Validation réussie
     📊 Sources: Trustpilot | ⏱️ 0.45s
```

### Detailed Response

```
Bot: 🤖 Agent A
     Question: Complete profile of HSBC
     
     Réponse: 
     HSBC Holdings plc...
     [Full detailed response]
     
     Sources Used:
     - FCA Database: 2024-02-04
     - SEC EDGAR: JPM relationship disclosed
     - OFAC List: Negative match (clean)
     
     Confidence Level: High (multi-source confirmation)
     Data Age: 1 day old (current)
     
     ⏱️ 2.34s | 📊 Sources: FCA, SEC EDGAR, OFAC | 📦 Snapshots: ✅
```

## 7. Advanced Features (Future)

```
# Scheduled Reports
/schedule-agent-report Agent RVI DAILY MORNING

# Notifications
/alert Agent SSS IF any_major_bank_sanctioned

# Export
/export Agent A conversation XLSX

# Comparison
/compare Agent RVI risk "Apple vs Microsoft"

# Trend Analysis
/analyze Agent RVI JPMorgan_risk LAST_30_DAYS
```

---

## Tips & Tricks

✅ **Pour des réponses rapides**: DM au bot au lieu de mentionner dans un channel
✅ **Pour l'audit**: Utilisez les threads pour garder la conversation organisée
✅ **Pour le contexte**: Incluez autant de détails que possible dans la question
✅ **Pour la validation**: Demandez à Agent B de valider après Agent A
✅ **Pour les alertes**: Utilisez Agent SSS pour vérifications compliance urgentes

⚠️  **Limites**
- Pas d'accès à des données "futures" ou non-publiques
- Réponses basées sur Ollama LLM (peut avoir hallucinations)
- TimeOut si réponse > 30 secondes
- Rate limit: 60 questions/heure par utilisateur (future)
