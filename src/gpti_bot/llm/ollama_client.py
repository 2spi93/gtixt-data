from __future__ import annotations

import os
import json
import requests
from typing import Any, Dict, Optional


# ---------------------------------------------------------
# Environment
# ---------------------------------------------------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11435").rstrip("/")
OLLAMA_TIMEOUT_S = int(os.getenv("OLLAMA_TIMEOUT_S", "60"))
OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.1:latest")


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _normalize_model(model: str | None) -> str:
    """
    Normalise le nom du modèle :
    - ajoute :latest si absent
    - fallback sur OLLAMA_DEFAULT_MODEL
    """
    model = (model or "").strip()

    if not model:
        return OLLAMA_DEFAULT_MODEL

    if ":" not in model:
        model = f"{model}:latest"

    return model


def _ollama_url(path: str) -> str:
    return f"{OLLAMA_BASE_URL}{path}"


# ---------------------------------------------------------
# Ollama API
# ---------------------------------------------------------

def ollama_tags() -> dict[str, Any]:
    """
    Retourne la liste des modèles disponibles.
    """
    url = _ollama_url("/api/tags")

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise RuntimeError(f"Ollama /api/tags failed: {e}")


def generate(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
) -> str:
    """
    Appel institutionnel à /api/generate (non-stream).
    Retourne uniquement le texte généré.
    """

    url = _ollama_url("/api/generate")

    payload = {
        "model": _normalize_model(model),
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    try:
        r = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT_S)
        r.raise_for_status()
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Ollama timeout after {OLLAMA_TIMEOUT_S}s")
    except Exception as e:
        raise RuntimeError(f"Ollama /api/generate failed: {e}")

    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"Ollama returned invalid JSON: {r.text[:200]}")

    # Format attendu : {"response": "..."}
    resp = data.get("response")
    if resp is None:
        raise RuntimeError(f"Ollama response missing 'response' field: {data}")

    return str(resp).strip()