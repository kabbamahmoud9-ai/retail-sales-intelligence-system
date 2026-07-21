"""
core/ai_engine.py

Centralized AI provider abstraction. ALL LLM API calls in this project
go through generate() below — no app should import openai/anthropic,
or call Gemini's API directly. This keeps every AI-powered feature
provider-agnostic: switching AI_PROVIDER in .env changes which backend
answers, without touching any calling code's business logic.

Contract every caller relies on:
  - generate() returns a string on success, or None on ANY failure
    (missing key, network error, malformed response, rate limit, etc).
  - Callers MUST treat None as "fall back to existing rule-based logic"
    — never crash, never show a raw error to the end user.
  - When AI_PROVIDER == 'rule_based' (the default), generate() returns
    None immediately, no network call, no import, no API key lookup —
    the system is fully offline-capable by construction.
  - The LLM is NEVER the source of truth. Every caller builds its
    prompt from ALREADY-COMPUTED structured data (existing services/
    models) and asks the provider only to phrase/explain that data —
    never to invent figures.

Provider status (honest, as of this writing):
  - rule_based : no-op, always returns None. Default. Always available.
  - gemini     : fully implemented AND personally tested (Step 17).
  - openai     : implemented per OpenAI's current chat completions
                 pattern. NOT personally live-tested with a real key.
  - anthropic  : implemented per Anthropic's current Messages API
                 pattern. NOT personally live-tested with a real key.
    Both are ready for live testing whenever a real key is supplied —
    verify against current provider docs before first live use, since
    SDK/API details can shift over time.
"""
import json
import requests
from django.conf import settings

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"


def generate(prompt, context=None, system_instruction=None):
    """
    Single public entry point for every AI-powered module in this
    project. Returns generated text, or None if the provider is
    rule_based, unconfigured, or fails for any reason.
    """
    provider = getattr(settings, 'AI_PROVIDER', 'rule_based')

    if provider == 'gemini':
        return _call_gemini(prompt, system_instruction)
    elif provider == 'openai':
        return _call_openai(prompt, system_instruction)
    elif provider == 'anthropic':
        return _call_anthropic(prompt, system_instruction)

    return None  # rule_based, or any unrecognized value — fail safe to offline mode


def _call_gemini(prompt, system_instruction=None):
    """Fully implemented and personally tested (Step 17)."""
    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return None

    full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={api_key}",
            headers={'Content-Type': 'application/json'},
            json={"contents": [{"parts": [{"text": full_prompt}]}]},
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
        return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError):
        return None


def _call_openai(prompt, system_instruction=None):
    """
    Implemented per OpenAI's current chat completions API pattern.
    NOT personally live-tested with a real API key as of this writing
    — implemented and documented for supervisor demonstration.
    """
    api_key = getattr(settings, 'OPENAI_API_KEY', '')
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            timeout=25,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        # Deliberately broad: an untested provider must never crash the
        # calling feature — same fail-safe contract as every provider
        # here. Narrow this once live-tested with a real key.
        return None


def _call_anthropic(prompt, system_instruction=None):
    """
    Implemented per Anthropic's current Messages API pattern. NOT
    personally live-tested with a real API key as of this writing —
    implemented and documented for supervisor demonstration.
    """
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_instruction or "",
            messages=[{"role": "user", "content": prompt}],
            timeout=25,
        )
        return response.content[0].text.strip()
    except Exception:
        return None