from __future__ import annotations

import json
import os
from time import perf_counter
import urllib.error
import urllib.request
from datetime import UTC, datetime

from .env_config import load_local_env
from .models import OllamaHealthStatus, OllamaModelInfo, OllamaPreferredModelStatus, OllamaRunningModelInfo


load_local_env()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_OLLAMA_MODEL = os.getenv("ROCMPORTER_OLLAMA_MODEL", "qwen2.5-coder")
OLLAMA_REQUEST_TIMEOUT_SECONDS = max(60, int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "240")))


def generate_structured(
    model: str,
    prompt: str,
    schema: dict,
    *,
    system: str | None = None,
    options: dict | None = None,
) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": schema,
        "keep_alive": "10m",
    }
    if system:
        payload["system"] = system
    if options:
        payload["options"] = options

    response = _post_json("/api/generate", payload)
    body = response.get("response", "")
    if not body:
        raise RuntimeError("Ollama returned an empty response")

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON for the requested patch format") from exc


def list_models() -> list[OllamaModelInfo]:
    data = _get_json("/api/tags")
    try:
        running_by_name = {item.name: item for item in list_running_models()}
    except RuntimeError:
        running_by_name = {}
    return _build_model_inventory(data.get("models", []), running_by_name)


def list_running_models() -> list[OllamaRunningModelInfo]:
    data = _get_json("/api/ps")
    return _parse_running_models(data.get("models", []))


def resolve_model_name(requested_name: str) -> str:
    models = list_models()
    preferred = _resolve_preferred_model(requested_name, models)
    if preferred.resolvedName:
        return preferred.resolvedName
    raise ValueError(
        f"Local Ollama model '{requested_name}' is not installed. Pull it locally or choose one of the installed models."
    )


def get_health_status(requested_name: str | None = None) -> OllamaHealthStatus:
    requested = requested_name or DEFAULT_OLLAMA_MODEL
    checked_at = datetime.now(UTC)
    started_at = perf_counter()

    try:
        version_data = _get_json("/api/version")
        tags_data = _get_json("/api/tags")
        try:
            ps_data = _get_json("/api/ps")
        except RuntimeError:
            ps_data = {"models": []}
    except RuntimeError as exc:
        return OllamaHealthStatus(
            host=OLLAMA_HOST,
            reachable=False,
            checkedAt=checked_at,
            responseTimeMs=_elapsed_ms(started_at),
            preferredModel=OllamaPreferredModelStatus(requestedName=requested),
            summary="Ollama is not reachable locally.",
            error=str(exc),
        )

    running_models = _parse_running_models(ps_data.get("models", []))
    running_by_name = {item.name: item for item in running_models}
    models = _build_model_inventory(tags_data.get("models", []), running_by_name)
    preferred = _resolve_preferred_model(requested, models)
    summary = _build_health_summary(preferred, models)

    return OllamaHealthStatus(
        host=OLLAMA_HOST,
        reachable=True,
        checkedAt=checked_at,
        version=version_data.get("version"),
        responseTimeMs=_elapsed_ms(started_at),
        preferredModel=preferred,
        modelCount=len(models),
        loadedModelCount=sum(1 for model in models if model.loaded),
        models=models,
        runningModels=running_models,
        summary=summary,
    )


def warm_model(requested_name: str | None = None) -> OllamaHealthStatus:
    resolved_name = resolve_model_name(requested_name or DEFAULT_OLLAMA_MODEL)
    _post_json(
        "/api/generate",
        {
            "model": resolved_name,
            "prompt": "Reply with READY.",
            "stream": False,
            "keep_alive": "15m",
            "options": {
                "temperature": 0,
                "num_predict": 8,
            },
        },
    )
    return get_health_status(resolved_name)


def _get_json(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}{path}", timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError("Unable to reach Ollama. Make sure the Ollama app is running locally.") from exc


def _post_json(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{OLLAMA_HOST}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc)).lower()
        if "timed out" in reason:
            raise RuntimeError(
                f"Ollama did not finish the request within {OLLAMA_REQUEST_TIMEOUT_SECONDS} seconds."
            ) from exc
        raise RuntimeError("Unable to reach Ollama. Make sure the Ollama app is running locally.") from exc


def _build_model_inventory(
    entries: list[dict],
    running_by_name: dict[str, OllamaRunningModelInfo],
) -> list[OllamaModelInfo]:
    models: list[OllamaModelInfo] = []
    for entry in entries:
        name = entry.get("name", "unknown")
        running = running_by_name.get(name)
        details = entry.get("details") or {}
        models.append(
            OllamaModelInfo(
                name=name,
                size=entry.get("size"),
                modifiedAt=_parse_datetime(entry.get("modified_at")),
                digest=entry.get("digest"),
                capabilities=_string_list(entry.get("capabilities")),
                available=True,
                loaded=running is not None,
                sizeVram=running.sizeVram if running is not None else _coerce_int(entry.get("size_vram")),
                expiresAt=running.expiresAt if running is not None else _parse_datetime(entry.get("expires_at")),
                details={
                    "format": _coerce_str(details.get("format")),
                    "family": _coerce_str(details.get("family")),
                    "families": _string_list(details.get("families")),
                    "parameterSize": _coerce_str(details.get("parameter_size")),
                    "quantizationLevel": _coerce_str(details.get("quantization_level")),
                    "contextLength": _coerce_int(details.get("context_length")),
                    "embeddingLength": _coerce_int(details.get("embedding_length")),
                },
            )
        )
    return models


def _parse_running_models(entries: list[dict]) -> list[OllamaRunningModelInfo]:
    models: list[OllamaRunningModelInfo] = []
    for entry in entries:
        details = entry.get("details") or {}
        models.append(
            OllamaRunningModelInfo(
                name=entry.get("name", "unknown"),
                size=entry.get("size"),
                processor=_coerce_str(entry.get("processor")),
                context=_coerce_int(details.get("context_length") or entry.get("context")),
                sizeVram=_coerce_int(entry.get("size_vram")),
                expiresAt=_parse_datetime(entry.get("expires_at") or entry.get("until")),
            )
        )
    return models


def _resolve_preferred_model(
    requested_name: str,
    models: list[OllamaModelInfo],
) -> OllamaPreferredModelStatus:
    requested_base = _base_model_name(requested_name)
    exact = next((model for model in models if model.name == requested_name), None)
    if exact is not None:
        return OllamaPreferredModelStatus(
            requestedName=requested_name,
            resolvedName=exact.name,
            available=True,
            loaded=exact.loaded,
        )

    compatible = next((model for model in models if _base_model_name(model.name) == requested_base), None)
    if compatible is not None:
        return OllamaPreferredModelStatus(
            requestedName=requested_name,
            resolvedName=compatible.name,
            available=True,
            loaded=compatible.loaded,
        )

    return OllamaPreferredModelStatus(requestedName=requested_name)


def _build_health_summary(
    preferred: OllamaPreferredModelStatus,
    models: list[OllamaModelInfo],
) -> str:
    if not models:
        return "Ollama is reachable, but no local models are installed yet."
    if not preferred.available:
        return f"{preferred.requestedName} is not installed locally."
    if preferred.loaded:
        return f"{preferred.resolvedName} is ready for single-file patch generation."
    return f"{preferred.resolvedName} is installed locally, but it is not warm yet."


def _elapsed_ms(started_at: float) -> int:
    return max(1, int((perf_counter() - started_at) * 1000))


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _base_model_name(name: str) -> str:
    return name.split(":", 1)[0].strip().lower()
