#!/usr/bin/env python3
"""Idempotent: add Gemini provider support to lib/intelligence/ai/config.py."""
from pathlib import Path

p = Path("lib/intelligence/ai/config.py")
src = p.read_text(encoding="utf-8")
if "GEMINI_PROVIDER" in src:
    print("Gemini already wired")
    raise SystemExit(0)

needle = 'AI_HTTP_USER_AGENT = "NorthlineFamilyDesk/1.0"'
if needle not in src:
    raise SystemExit("AI_HTTP_USER_AGENT marker missing")
src = src.replace(
    needle,
    needle
    + "\n\nGEMINI_PROVIDER = \"gemini\"\n"
    + "GEMINI_BASE_URL = \"https://generativelanguage.googleapis.com/v1beta/openai/\"\n"
    + 'GEMINI_MODEL = "gemini-2.0-flash"\n',
    1,
)

old_fb = '''_FALLBACK_PROVIDER: dict[str, str] = {
    "groq": OLLAMA_LOCAL_PROVIDER,
    "openai_compat": OLLAMA_LOCAL_PROVIDER,
}'''
new_fb = '''_FALLBACK_PROVIDER: dict[str, str] = {
    "groq": "gemini",
    "gemini": "groq",
    "openai_compat": OLLAMA_LOCAL_PROVIDER,
}'''
if old_fb in src:
    src = src.replace(old_fb, new_fb, 1)

old_paths = '''            ("groq", "api_key"),
            (ENV_AI_API_KEY,),
            ("GROQ_API_KEY",),
        )'''
new_paths = '''            ("groq", "api_key"),
            ("ai", "GEMINI_API_KEY"),
            ("gemini", "API_KEY"),
            ("gemini", "GEMINI_API_KEY"),
            ("gemini", "api_key"),
            (ENV_AI_API_KEY,),
            ("GROQ_API_KEY",),
            ("GEMINI_API_KEY",),
        )'''
if old_paths in src:
    src = src.replace(old_paths, new_paths, 1)

src = src.replace(
    'env.get(ENV_AI_API_KEY, "") or env.get("GROQ_API_KEY", "") or ""',
    'env.get(ENV_AI_API_KEY, "") or env.get("GROQ_API_KEY", "") or env.get("GEMINI_API_KEY", "") or ""',
    1,
)

old_prov = '''    if provider == GROQ_PROVIDER:
        base_url = explicit_base or GROQ_BASE_URL
        model = explicit_model or GROQ_MODEL
        default_timeout = 60.0
        default_max_tokens = 2048
    elif provider == OLLAMA_LOCAL_PROVIDER:'''
new_prov = '''    if provider == GROQ_PROVIDER:
        base_url = explicit_base or GROQ_BASE_URL
        model = explicit_model or GROQ_MODEL
        default_timeout = 60.0
        default_max_tokens = 2048
    elif provider in (GEMINI_PROVIDER, "google", "google_gemini"):
        provider = GEMINI_PROVIDER
        base_url = explicit_base or GEMINI_BASE_URL
        model = explicit_model or GEMINI_MODEL
        default_timeout = 60.0
        default_max_tokens = 2048
        gem_key = str(env.get("GEMINI_API_KEY", "") or "").strip()
        if gem_key:
            api_key = gem_key
    elif provider == OLLAMA_LOCAL_PROVIDER:'''
if old_prov in src:
    src = src.replace(old_prov, new_prov, 1)

p.write_text(src, encoding="utf-8")
print("Gemini provider wired into AI config")
