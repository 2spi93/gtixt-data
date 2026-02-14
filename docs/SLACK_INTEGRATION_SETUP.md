# 🤖 Integration Slack - Guide de Configuration

## Vue d'ensemble

Les agents GPTI peuvent maintenant répondre aux questions en direct via Slack.

### Fonctionnalités

- 💬 Interroger les agents en direct via Slack
- 📊 Réponses formatées avec sources et temps d'exécution
- 🔍 Routing automatique aux agents appropriés
- 📝 Audit trail complet des interactions
- ⚡ Réponses basées sur Ollama LLM + contexte MinIO

## Configuration Slack

### Étape 1: Créer une Slack App

1. Allez sur [api.slack.com/apps](https://api.slack.com/apps)
2. Cliquez sur "Create New App"
3. Sélectionnez "From scratch"
4. Nom: `GPTI Agents`
5. Workspace: Sélectionnez votre workspace

### Étape 2: Configurer les Permissions

Dans "OAuth & Permissions":

#### Bot Token Scopes
Ajoutez ces permissions:
```
app_mentions:read
chat:write
conversations:setTopic
users:read
reactions:write
```

#### Scopes pour User Token (optionnel)
```
chat:write
```

### Étape 3: Générer les Tokens

1. Dans "OAuth & Permissions", cliquez sur "Install to Workspace"
2. Copiez le **Bot User OAuth Token** (commence par `xoxb-`)
3. Allez dans "Basic Information"
4. Copiez le **Signing Secret**

### Étape 4: Configurer les Events

1. Allez dans "Event Subscriptions"
2. Activez "Enable Events"
3. **Request URL**: `https://your-domain.com/slack/events`
   - GPTI va générer un token de vérification, sauvegardez-le
4. Sous "Subscribe to bot events", ajoutez:
   ```
   app_mention
   message.channels
   message.im
   ```
5. Cliquez "Save Changes"

### Étape 5: Configuration Environnement

Mettez à jour `.env.local`:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-YOUR_BOT_TOKEN_HERE
SLACK_SIGNING_SECRET=YOUR_SIGNING_SECRET_HERE
SLACK_INTERACTION_PORT=5000

# Webhooks (remplacez par votre URL)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/CHANGE/ME
```

### Étape 6: Exposer le Serveur (Production)

Pour que Slack puisse envoyer des événements:

**Option A: Ngrok (local testing)**
```bash
ngrok http 5000
# Copier l'URL https://xxxx-xx-xxx-xxx.ngrok.io
# Dans Slack Event Subscriptions:
# Request URL = https://xxxx-xx-xxx-xxx.ngrok.io/slack/events
```

**Option B: Production**
- Déployer `slack_server.py` sur votre serveur
- Configurer HTTPS (Slack requiert HTTPS)
- Slack Event Subscriptions Request URL = `https://your-domain.com/slack/events`

## Utilisation

### Format des Messages

#### 1. Mention le bot directement
```
@GPTI Agent A: Qu'est-ce que la firme ABC Corp?
```

#### 2. DM au bot
```
Juste envoyer un DM avec votre question
```

#### 3. Spécifier l'agent
```
Agent RVI: Quel est le risque d'investissement de XYZ?
Agent SSS: Vérifier si ABC est en liste OFAC
```

#### 4. Agents disponibles
- **Agent A**: Collecte de données réglementaires (FCA, SEC, OFAC)
- **Agent B**: Validation des données
- **Agent RVI**: Analyse des risques d'investissement
- **Agent SSS**: Surveillance des sanctions et scams
- **Agent REM**: Monitoring réglementaire
- **Agent IRS**: Analyse du risque d'insolvabilité
- **Agent FRP**: Profil du risque financier
- **Agent MIS**: Information sur la structure

### Exemple de Conversation

```
User: @GPTI Agent A: Qui est Apple Inc?
Bot: 🤖 Agent A
     Question: Qui est Apple Inc?
     Réponse: Apple Inc. est une société technologique...
             [Sources détaillées avec liens]
     ⏱️ 2.34s | 📊 Snapshots: ✅
```

## Développement

### Démarrer le serveur Slack localement

```bash
cd /opt/gpti/gpti-data-bot

# Installer les dépendances
pip install slack-bolt slack-sdk flask aiohttp

# Démarrer le serveur
python slack_server.py
```

Le serveur écoute sur `http://localhost:5000/slack/events`

### Endpoints

- `POST /slack/events` - Webhook d'événements Slack
- `GET /slack/health` - Vérifier la santé du service
- `GET /slack/info` - Infos sur le bot et agents

## Architecture

```
Slack Channel/DM
    ↓
slack_server.py (Flask)
    ↓
SlackEventHandler (events.py)
    ├─ Parse message
    ├─ Identify agent
    └─ Route to agent
    ↓
AgentInterface (agent_interface.py)
    ├─ Fetch data context (MinIO)
    ├─ Query Ollama LLM
    └─ Format response
    ↓
ResponseHandler (response_handler.py)
    ├─ Format Slack blocks
    ├─ Send response
    └─ Log interaction
    ↓
Slack Response
```

## Logging et Monitoring

Les interactions sont loggées dans:
- `logs/slack_interactions.log` - Toutes les interactions
- Slack webhook - Alertes importantes
- Base de données (future) - Audit trail complet

### Vérifier les logs

```bash
tail -f logs/slack_interactions.log
```

## Dépannage

### "Erreur: Slack bot token missing"
- Vérifiez `SLACK_BOT_TOKEN` dans `.env.local`
- Le token doit commencer par `xoxb-`

### "Erreur: Request URL verification failed"
- Vérifiez que `/slack/events` répond avec le bon token
- Vérifiez le `SLACK_SIGNING_SECRET` dans `.env.local`

### "Bot ne répond pas aux messages"
- Vérifiez que l'app est installée dans le workspace
- Vérifiez que le bot a permissions app_mentions:read
- Vérifiez que `/slack/events` est accessible publiquement

### "Réponses très lentes"
- Vérifiez que Ollama tourne (http://localhost:11434)
- Vérifiez la connectivité MinIO (http://51.210.246.61:9000)
- Vérifiez les logs du serveur Flask

## Sécurité

✅ Tous les tokens Slack sont protégés dans `.env.local`
✅ Signing secret valide chaque request venant de Slack
✅ Audit trail complet des interactions utilisateurs
⚠️ En production: HTTPS OBLIGATOIRE pour Slack webhooks

## Prochaines Étapes

1. **Intégration MinIO**: Améliorer le contexte des données
2. **Contexte des snapshots**: Inclure les données réelles dans les réponses
3. **Base de données**: Sauvegarder l'historique des interactions
4. **Caching**: Cacher les réponses fréquentes
5. **Permissions**: Contrôler qui peut interroger quel agent
