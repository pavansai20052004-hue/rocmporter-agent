"""Unified LLM provider layer.

This module is the single entry point the rest of the app uses to talk to a
language model. It lets the product run in two very different environments:

* Local development / self-hosted: a machine running Ollama (default).
* Cloud deployment (Render, etc.): a hosted, API-key based model. Ollama can
  never run on a serverless / small cloud host, so the deployed product points
  at a hosted API instead.

The provider is chosen with the ``LLM_PROVIDER`` environment variable:

    LLM_PROVIDER=ollama        # local, default
    LLM_PROVIDER=openai        # OpenAI or any OpenAI-compatible endpoint
    LLM_PROVIDER=groq          # Groq (OpenAI-compatible)
    LLM_PROVIDER=openrouter    # OpenRouter (OpenAI-compatible)
    LLM_PROVIDER=together      # Together AI (OpenAI-compatible)
    LLM_PROVIDER=deepseek      # DeepSeek (OpenAI-compatible)
    LLM_PROVIDER=anthropic     # Anthropic Claude

For any hosted provider you set:

    LLM_API_KEY=...            # required, kept in the host's secret store
    LLM_MODEL=...              # optional, a sensible default is used otherwise
    LLM_BASE_URL=...           # optional, override the provider base URL
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime

from . import ollama_service
from .env_config import load_local_env
from .models import (
    OllamaHealthStatus,
    OllamaModelInfo,
    OllamaPreferredModelStatus,
)

load_local_env()


# provider -> (default base url, default model)
_OPENAI_COMPATIBLE: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct"),
    "together": ("https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
}
_ANTHROPIC_DEFAULT = ("https://api.anthropic.com/v1", "claude-sonnet-5")

REQUEST_TIMEOUT_SECONDS = max(30, int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "120")))


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "ollama").strip().lower()


def _is_hosted(name: str | None = None) -> bool:
    name = name or provider()
    return name in _OPENAI_COMPATIBLE or name == "anthropic"


def _api_key() -> str:
    for key in ("LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        value = os.getenv(key)
        if value:
            return value.strip()
    return ""


def _base_url(name: str) -> str:
    override = os.getenv("LLM_BASE_URL")
    if override:
        return override.rstrip("/")
    if name == "anthropic":
        return _ANTHROPIC_DEFAULT[0]
    return _OPENAI_COMPATIBLE.get(name, _OPENAI_COMPATIBLE["openai"])[0]


def default_model() -> str:
    name = provider()
    override = os.getenv("LLM_MODEL")
    if override:
        return override.strip()
    if name == "anthropic":
        return _ANTHROPIC_DEFAULT[1]
    if name in _OPENAI_COMPATIBLE:
        return _OPENAI_COMPATIBLE[name][1]
    return ollama_service.DEFAULT_OLLAMA_MODEL


def resolve_model_name(requested_name: str | None) -> str:
    """Validate/resolve the model to use.

    For Ollama we make sure the model is actually installed (delegated). For a
    hosted API we simply trust the configured model name.
    """
    if not _is_hosted():
        return ollama_service.resolve_model_name(requested_name or ollama_service.DEFAULT_OLLAMA_MODEL)
    return (requested_name or "").strip() or default_model()


def generate_structured(
    model: str,
    prompt: str,
    schema: dict,
    *,
    system: str | None = None,
    options: dict | None = None,
) -> dict:
    name = provider()
    if not _is_hosted(name):
        return ollama_service.generate_structured(model, prompt, schema, system=system, options=options)

    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "No LLM API key is configured. Set LLM_API_KEY in the server environment "
            "(for example in the Render dashboard) to enable AI patch generation."
        )

    options = options or {}
    temperature = float(options.get("temperature", 0.1))
    max_tokens = int(options.get("num_predict", 1800))
    json_system = _augment_system_for_json(system, schema)

    if name == "anthropic":
        text = _call_anthropic(api_key, model or default_model(), prompt, json_system, temperature, max_tokens)
    else:
        text = _call_openai_compatible(name, api_key, model or default_model(), prompt, json_system, temperature, max_tokens)

    return _extract_json(text)


# --------------------------------------------------------------------------- #
# Health / model listing so the UI status panel works for hosted providers too
# --------------------------------------------------------------------------- #

def list_models() -> list[OllamaModelInfo]:
    if not _is_hosted():
        return ollama_service.list_models()
    model = default_model()
    return [OllamaModelInfo(name=model, available=True, loaded=bool(_api_key()))]


def warm_model(requested_name: str | None = None) -> OllamaHealthStatus:
    if not _is_hosted():
        return ollama_service.warm_model(requested_name)
    return get_health_status(requested_name)


def get_health_status(requested_name: str | None = None) -> OllamaHealthStatus:
    name = provider()
    if not _is_hosted(name):
        return ollama_service.get_health_status(requested_name)

    model = (requested_name or "").strip() or default_model()
    has_key = bool(_api_key())
    preferred = OllamaPreferredModelStatus(
        requestedName=model,
        resolvedName=model if has_key else None,
        available=has_key,
        loaded=has_key,
    )
    if has_key:
        summary = f"Hosted model {model} ({name}) is ready for patch generation."
    else:
        summary = f"Provider {name} is selected, but LLM_API_KEY is not set on the server yet."

    return OllamaHealthStatus(
        host=_base_url(name),
        reachable=has_key,
        checkedAt=datetime.now(UTC),
        version=f"{name} (hosted)",
        responseTimeMs=1,
        preferredModel=preferred,
        modelCount=1 if has_key else 0,
        loadedModelCount=1 if has_key else 0,
        models=list_models() if has_key else [],
        runningModels=[],
        summary=summary,
        error=None if has_key else "LLM_API_KEY is not configured on the server.",
    )


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #

def _augment_system_for_json(system: str | None, schema: dict) -> str:
    keys = list((schema or {}).get("properties", {}).keys())
    shape = ", ".join(keys) if keys else "the requested fields"
    instruction = (
        "Respond with a single valid JSON object and nothing else. "
        f"The JSON object must contain these keys: {shape}. "
        "Do not wrap the JSON in markdown code fences or add commentary."
    )
    return f"{system}\n\n{instruction}" if system else instruction


def _post(url: str, payload: dict, headers: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        # A real User-Agent matters: Cloudflare (in front of Groq and others)
        # rejects Python-urllib's default UA with 403 error code 1010.
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ROCmPorter/1.0 (+https://rocmporter-agent.vercel.app)",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")
        except Exception:  # pragma: no cover - best effort error surfacing
            detail = ""
        raise RuntimeError(f"LLM provider returned HTTP {exc.code}: {detail[:400] or exc.reason}") from exc
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        raise RuntimeError(f"Could not reach the LLM provider: {reason}") from exc


def _call_openai_compatible(
    name: str,
    api_key: str,
    model: str,
    prompt: str,
    system: str,
    temperature: float,
    max_tokens: int,
) -> str:
    url = f"{_base_url(name)}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if os.getenv("LLM_JSON_MODE", "true").strip().lower() != "false":
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {api_key}"}
    if name == "openrouter":
        headers["HTTP-Referer"] = os.getenv("LLM_APP_URL", "https://rocmporter.app")
        headers["X-Title"] = "ROCmPorter Agent"

    try:
        data = _post(url, payload, headers)
    except RuntimeError as exc:
        # Some OpenAI-compatible providers reject response_format json_object.
        if "response_format" in str(exc) or "json_object" in str(exc):
            payload.pop("response_format", None)
            data = _post(url, payload, headers)
        else:
            raise

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM provider returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):  # some providers return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not content:
        raise RuntimeError("LLM provider returned an empty message.")
    return content


def _call_anthropic(
    api_key: str,
    model: str,
    prompt: str,
    system: str,
    temperature: float,
    max_tokens: int,
) -> str:
    url = f"{_base_url('anthropic')}/messages"
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    data = _post(url, payload, headers)
    parts = data.get("content") or []
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not text:
        raise RuntimeError("Anthropic returned an empty response.")
    return text


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown fences if the model added them anyway.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise RuntimeError("The LLM returned text that was not valid JSON for the patch.") from exc
        raise RuntimeError("The LLM returned text that was not valid JSON for the patch.")
