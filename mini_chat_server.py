"""Mini chat autonome pour interroger les agents GPTI."""

import os
import asyncio
import logging
from flask import Flask, request, jsonify, render_template_string

from src.slack_integration.agent_interface import AgentInterface

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

HTML_PAGE = """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GPTI Mini‑Chat</title>
  <style>
    body { font-family: Inter, system-ui, sans-serif; background:#0b1020; color:#e6e9f2; margin:0; }
    .container { max-width: 900px; margin: 40px auto; padding: 24px; }
    .card { background:#121a33; border:1px solid #1e2a52; border-radius:12px; padding:24px; }
    h1 { margin:0 0 12px; font-size:24px; }
    label { display:block; margin:12px 0 6px; font-weight:600; }
    input, select, textarea { width:100%; padding:10px; border-radius:8px; border:1px solid #2b3a6e; background:#0f1630; color:#e6e9f2; }
    textarea { min-height:120px; }
    button { margin-top:12px; padding:10px 16px; border:none; border-radius:8px; background:#4c7dff; color:white; font-weight:600; cursor:pointer; }
    button:disabled { opacity:0.6; cursor:not-allowed; }
    .resp { margin-top:18px; padding:14px; border-radius:8px; background:#0f1630; border:1px solid #2b3a6e; white-space:pre-wrap; }
    .row { display:flex; gap:12px; }
    .col { flex:1; }
    .muted { color:#a8b3d6; font-size:12px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>GPTI Mini‑Chat (Autonome)</h1>
      <div class="muted">Pose une question à un agent. Réponse en direct.</div>

      <div class="row">
        <div class="col">
          <label>Agent</label>
          <select id="agent">
            <option value="A">Agent A</option>
            <option value="B">Agent B</option>
            <option value="RVI">Agent RVI</option>
            <option value="SSS">Agent SSS</option>
            <option value="REM">Agent REM</option>
            <option value="IRS">Agent IRS</option>
            <option value="FRP">Agent FRP</option>
            <option value="MIS">Agent MIS</option>
          </select>
        </div>
        <div class="col">
          <label>Mot de passe (optionnel)</label>
          <input id="pwd" type="password" placeholder="Si activé" />
        </div>
      </div>

      <label>Question</label>
      <textarea id="query" placeholder="Ex: Agent A, qui est Apple Inc?" ></textarea>

      <button id="send">Envoyer</button>

      <div class="resp" id="resp">En attente...</div>
    </div>
  </div>

<script>
const btn = document.getElementById('send');
const resp = document.getElementById('resp');
const agent = document.getElementById('agent');
const query = document.getElementById('query');
const pwd = document.getElementById('pwd');

btn.addEventListener('click', async () => {
  resp.textContent = '⏳ Envoi...';
  btn.disabled = true;
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Chat-Password': pwd.value || '' },
      body: JSON.stringify({ agent: agent.value, query: query.value })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Erreur');
    resp.textContent = data.response || 'Pas de réponse';
  } catch (e) {
    resp.textContent = '❌ ' + e.message;
  } finally {
    btn.disabled = false;
  }
});
</script>
</body>
</html>
"""


def _check_password(req) -> bool:
    required = os.getenv("CHAT_UI_PASSWORD")
    if not required:
        return True
    provided = req.headers.get("X-Chat-Password", "") or (req.json or {}).get("password", "")
    return provided == required


@app.route("/chat", methods=["GET"])
def chat_page():
    return render_template_string(HTML_PAGE)


@app.route("/api/chat", methods=["POST"])
def chat_api():
    if not _check_password(request):
        return jsonify({"error": "Accès refusé"}), 401

    payload = request.get_json(silent=True) or {}
    agent = (payload.get("agent") or "A").upper()
    query = (payload.get("query") or "").strip()

    if not query:
        return jsonify({"error": "Question vide"}), 400

    interface = AgentInterface()

    async def _run():
        return await interface.query_agent(agent, query, user_id="web")

    try:
        result = asyncio.run(_run())
    except RuntimeError:
        # If an event loop is already running
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(_run())

    if not result.get("success"):
        return jsonify({"error": result.get("response", "Erreur")}), 500

    return jsonify({"response": result.get("response")})


if __name__ == "__main__":
    port = int(os.getenv("CHAT_PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
