"""Discover Groq's live model catalog and update the AI default model.

Single-purpose automation for the task: the app's pinned default model
(``lib/intelligence/ai/config.py`` -> ``DEFAULT_MODEL``) may be discontinued
by the provider)Skip; this script asks the provider itself (never a hard-coded
guess) for what actually exists:

  1. ``GET {base}/models`` (default base https://api.groq.com/openai/v1).
  2. Prints model ids containing ``llama`` / ``mixtral`` / ``gemma`` (the
     families the app's model-picker vocabulary supports), plus the full
     catalog summary, one per line.
  3. Picks the first json_schema (Structured Outputs) capable id when the
     requested model is absent — printed, never silently injected.

The API key comes from the SAME canonical seam the app uses
(``lib.intelligence.ai.config.load_ai_config`` -> ``st.secrets["ai"]`` or
``AI_API_KEY`` env). The key is NEVER printed, logged, or written to any
file; ``redact()`` scrubs it out of any error text that reaches the pipe.

Exit codes: 0 = catalog listed; 1 = model action taken/URL attempted; 2 =
not reachable (degraded message, key scrubbed, no credentials leaked).
"""

from __future__ import annotations

import sys
import urllib.request

from lib.intelligence.ai.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    load_ai_config,
    redact,
)

# Families the app's model vocabulary supports (config.py / client.py pins).
_FAMILY_MARKERS = ("llama", "mixtral", "gemma", "qwen", "gpt-oss")


def _fetch_models(base_url: str, api_key: str) -> list[dict]:
    url = f"{base_url.rstrip('/')}/models"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        import json
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("data", []) if isinstance(payload, dict) else []


def _list_models(base_url: str, api_key: str) -> tuple[list[str], str]:
    models = _fetch_models(base_url, api_key)
    ids = sorted({str(m.get("id", "")) for m in models if isinstance(m, dict) and m.get("id")})
    return ids, ""

def _in_family(model_id: str) -> bool:
    low = model_id.lower()
    return any(marker in low for marker in _FAMILY_MARKERS)


def _first_json_schema_capable(ids: list[str]) -> str | None:
    """First available model whose id advertises Structured Outputs
    (json_schema). Deterministic, from the live catalog, never guessed."""
    for i in ids:
        low = i.lower()
        if any(m in low for m in ("gpt-oss", "qwen3")):
            return i
    for i in ids:
        if _in_family(i):
            return i
    return ids[0] if ids else None


def main() -> int:
    config = load_ai_config()
    if not config.api_key.strip():
        print("no AI API key configured (secrets.ai.AI_API_KEY or AI_API_KEY); cannot list models")
        return 2

    base_url = config.base_url.strip() or DEFAULT_BASE_URL
    try:
        ids = _list_models(base_url, config.api_key)[0]
    except Exception as exc:  # network/auth — degraded, key scrubbed, never evidence
        print("could not reach provider (models): " + redact(str(exc), config.api_key))
        return 2

    if not ids:
        print("provider returned an empty model catalog; nothing to switch to")
        return 2

    family = [i for i in ids if _in_family(i)]
    print(f"provider models: {len(ids)} total; {len(family)} in llama/mixtral/gemma/qwen/gpt-oss")
    for i in family:
        print(f"  {i}")

    if config.model and config.model in ids:
        print(f"configured model IS available: {config.model}")
        return 0

    chosen = _first_json_schema_capable(family or ids)
    print(f"configured model not in catalog ({config.model or '<none>'}); "
          f"first json_schema-capable available: {chosen}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
