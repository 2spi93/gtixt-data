"""Agent interface for Slack queries."""

import os
import json
import logging
import aiohttp
import psycopg2
from minio import Minio
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentInterface:
    """Interface between Slack and GPTI agents."""

    AGENT_DESCRIPTIONS = {
        "A": "Agent de collecte de données réglementaires (FCA, SEC)",
        "B": "Agent de validation des données",
        "RVI": "Agent d'analyse des risques d'investissement",
        "SSS": "Agent de surveillance des sanctions et scams",
        "REM": "Agent de monitoring réglementaire",
        "IRS": "Agent d'analyse du risque d'insolvabilité",
        "FRP": "Agent de profil du risque financier",
        "MIS": "Agent d'information sur la structure",
    }

    AGENT_SOURCES = {
        "A": ["FCA", "SEC EDGAR", "OFAC"],
        "B": ["Trustpilot", "Reviews internes"],
        "RVI": ["SEC Filings", "Bloomberg"],
        "SSS": ["OFAC Sanctions", "Scam Database"],
        "REM": ["FCA Rulebooks", "PRA Notices"],
        "IRS": ["Financial Ratios", "Credit Ratings"],
        "FRP": ["Market Data", "Financial Statements"],
        "MIS": ["Company Registry", "LinkedIn"],
    }

    def __init__(self):
        """Initialize agent interface."""
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self.minio_endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        
        # Initialize MinIO client
        minio_endpoint = self.minio_endpoint.replace("http://", "").replace("https://", "")
        self.minio_client = Minio(
            minio_endpoint,
            access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            secure=os.getenv("MINIO_USE_SSL", "false").lower() == "true"
        )
        
        # Database connection
        self.db_url = os.getenv("DATABASE_URL")

    async def query_agent(
        self, agent_name: str, query: str, user_id: str
    ) -> Dict[str, Any]:
        """
        Query an agent for information.
        Returns formatted response with sources and reasoning.
        """
        start_time = datetime.now()

        try:
            agent_name = agent_name.upper()
            if agent_name not in self.AGENT_DESCRIPTIONS:
                return self._error_response(
                    f"Agent {agent_name} non reconnu. Agents disponibles: A, B, RVI, SSS, REM, IRS, FRP, MIS"
                )

            # Step 1: Fetch relevant data from MinIO snapshots
            data_context = await self._fetch_data_context(query)

            # Step 2: Prepare agent-specific prompt
            system_prompt = self._build_system_prompt(agent_name)
            user_prompt = self._build_user_prompt(agent_name, query, data_context)

            # Step 3: Query Ollama LLM
            llm_response = await self._query_ollama(system_prompt, user_prompt)

            # Step 4: Format and augment response with sources
            response = self._format_agent_response(
                agent_name, query, llm_response, data_context, user_id, start_time
            )

            return response

        except Exception as e:
            logger.error(f"Error querying agent {agent_name}: {e}")
            return self._error_response(str(e))

    async def _fetch_data_context(self, query: str) -> Dict[str, Any]:
        """
        Fetch relevant data from MinIO snapshots and PostgreSQL.
        """
        try:
            context = {
                "snapshots_available": False,
                "search_query": query,
                "firms": [],
                "latest_snapshot": None
            }
            
            # Fetch latest snapshot from MinIO
            bucket = os.getenv("MINIO_BUCKET_SNAPSHOTS", "gpti-snapshots")
            try:
                objects = self.minio_client.list_objects(
                    bucket, 
                    prefix="universe_v0.1_public/_public/",
                    recursive=True
                )
                
                # Get latest.json
                for obj in objects:
                    if obj.object_name.endswith("latest.json"):
                        response = self.minio_client.get_object(bucket, obj.object_name)
                        snapshot_data = json.loads(response.read())
                        context["latest_snapshot"] = snapshot_data
                        context["snapshots_available"] = True
                        
                        # Extract firms from snapshot
                        if "firms" in snapshot_data:
                            context["firms"] = snapshot_data["firms"][:10]  # Top 10
                        break
                        
            except Exception as e:
                logger.warning(f"MinIO fetch error: {e}")
            
            # Search PostgreSQL for specific firms if query mentions a name
            if self.db_url:
                try:
                    conn = psycopg2.connect(self.db_url)
                    cursor = conn.cursor()
                    
                    # Simple search for firm names in query
                    cursor.execute("""
                        SELECT name, fca_reference, status 
                        FROM firms 
                        WHERE LOWER(name) LIKE %s 
                        LIMIT 5
                    """, (f"%{query.lower()}%",))
                    
                    db_firms = cursor.fetchall()
                    if db_firms:
                        context["db_firms"] = [
                            {"name": f[0], "fca_ref": f[1], "status": f[2]} 
                            for f in db_firms
                        ]
                    
                    cursor.close()
                    conn.close()
                except Exception as e:
                    logger.warning(f"PostgreSQL fetch error: {e}")
            
            return context
            
        except Exception as e:
            logger.warning(f"Could not fetch data context: {e}")
            return {"snapshots_available": False}

    async def _query_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Query Ollama LLM for agent response."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.ollama_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "temperature": 0.3,  # Lower temp for factual responses
                }

                async with session.post(
                    f"{self.ollama_url}/api/chat", json=payload, timeout=30
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("message", {}).get("content", "Pas de réponse")
                    else:
                        raise Exception(f"Ollama error: {resp.status}")
        except Exception as e:
            logger.error(f"Error querying Ollama: {e}")
            raise

    def _build_system_prompt(self, agent_name: str) -> str:
        """Build system prompt for agent."""
        description = self.AGENT_DESCRIPTIONS.get(agent_name, "Unknown agent")
        sources = ", ".join(self.AGENT_SOURCES.get(agent_name, []))

        return f"""Tu es l'Agent {agent_name} - {description}

Tes sources d'information principales sont: {sources}

RÈGLES IMPORTANTES:
1. Utilise UNIQUEMENT les données fournies dans le contexte
2. Si des données MinIO/PostgreSQL sont disponibles, cite-les directement
3. Ne réponds PAS avec des informations génériques ou inventées
4. Si le contexte ne contient pas l'information demandée, dis "Je n'ai pas cette information dans mes données actuelles"
5. Cite toujours tes sources (ex: "Selon le snapshot du [date]..." ou "D'après PostgreSQL...")

Réponds en français, sois concis et factuel."""

    def _build_user_prompt(
        self, agent_name: str, query: str, data_context: Dict[str, Any]
    ) -> str:
        """Build user prompt for agent."""
        
        # Format context with clear structure
        context_parts = []
        
        if data_context.get("snapshots_available"):
            context_parts.append("=== DONNÉES MINIO (SNAPSHOT ACTUEL) ===")
            if data_context.get("firms"):
                context_parts.append(f"Nombre de firmes: {len(data_context['firms'])}")
                context_parts.append("Top firmes:")
                for firm in data_context["firms"][:5]:
                    context_parts.append(f"  - {firm}")
            if data_context.get("latest_snapshot"):
                snap = data_context["latest_snapshot"]
                if "metadata" in snap:
                    context_parts.append(f"Metadata: {snap['metadata']}")
        else:
            context_parts.append("⚠️ Snapshots MinIO non disponibles")
        
        if data_context.get("db_firms"):
            context_parts.append("\n=== DONNÉES POSTGRESQL ===")
            context_parts.append("Firmes trouvées en base:")
            for firm in data_context["db_firms"]:
                context_parts.append(f"  - {firm['name']} (FCA: {firm['fca_ref']}, Status: {firm['status']})")
        else:
            context_parts.append("\n⚠️ Aucune firme trouvée en PostgreSQL pour cette recherche")
        
        context_str = "\n".join(context_parts)
        
        return f"""{context_str}

=== QUESTION ===
{query}

IMPORTANT: Réponds UNIQUEMENT avec les données ci-dessus. N'invente rien."""

    def _format_agent_response(
        self,
        agent_name: str,
        query: str,
        llm_response: str,
        data_context: Dict[str, Any],
        user_id: str,
        start_time: datetime,
    ) -> Dict[str, Any]:
        """Format agent response with metadata."""
        elapsed = (datetime.now() - start_time).total_seconds()

        return {
            "success": True,
            "agent": agent_name,
            "query": query,
            "response": llm_response,
            "sources": self.AGENT_SOURCES.get(agent_name, []),
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "execution_time": f"{elapsed:.2f}s",
            "data_context_available": data_context.get("snapshots_available", False),
        }

    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """Format error response."""
        return {
            "success": False,
            "response": error_msg,
            "timestamp": datetime.now().isoformat(),
        }
