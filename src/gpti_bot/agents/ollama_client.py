from __future__ import annotations
import os
import requests

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if v not in (None, "") else default

def base_url() -> str:
    return (_env("OLLAMA_BASE_URL", "http://host.docker.internal:11434")).rstrip("/")

def generate(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    stream: bool = False,
    timeout: int = 180,
    format: str | dict | None = None,
    options: dict | None = None,
) -> dict:
    url = base_url() + "/api/generate"
    payload = {
        "model": model or _env("OLLAMA_MODEL_RULES", "llama3.1:latest"),
        "prompt": prompt,
        "stream": stream,
    }
    if system:
        payload["system"] = system
    if format is not None:
        payload["format"] = format
    if options:
        payload["options"] = options

    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()
