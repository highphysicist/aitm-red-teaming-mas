"""
backends/vertex.py
──────────────────
Thin ADC wrapper: token refresh + OpenAI-compatible client for Vertex AI MaaS.

google-auth caches the token internally and tracks expiry via .expiry.
Calling refresh() is a no-op when the token is still valid, so it is safe
to call get_token() before every LLM request without performance penalty.
"""

import random
import time

import google.auth
import google.auth.transport.requests
from openai import OpenAI

PROJECT  = "aitm-red-teaming-493507"
LOCATION = "global"
MODEL    = "google/gemma-4-26b-a4b-it-maas"
BASE_URL = (
    f"https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT}"
    f"/locations/{LOCATION}/endpoints/openapi"
)

# Truncated exponential backoff config
_RETRY_BASE    = 2.0   # seconds
_RETRY_CAP     = 60.0  # max wait per attempt
_RETRY_MAX     = 8     # max attempts before giving up

# Module-level singleton — shared across all callers
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
_auth_req = google.auth.transport.requests.Request()


def get_token() -> str:
    """Return a valid Bearer token, refreshing via ADC only when expired."""
    _creds.refresh(_auth_req)
    return _creds.token


def make_client() -> OpenAI:
    """Return an OpenAI client pointing at Vertex AI MaaS with a fresh token.

    max_retries=8 activates the OpenAI SDK's built-in exponential backoff for
    429 / 503 / 5xx responses (covers adversary and judge call sites).
    """
    return OpenAI(
        base_url=BASE_URL,
        api_key=get_token(),
        max_retries=_RETRY_MAX,
        timeout=120.0,
    )


def call_with_retry(fn, *args, **kwargs):
    """Truncated exponential backoff wrapper for any callable that may raise
    openai.APIStatusError with code 429 or 503.

    delay = min(base * 2^attempt, cap) + uniform jitter in [0, 1)
    """
    from openai import APIStatusError

    for attempt in range(_RETRY_MAX):
        try:
            return fn(*args, **kwargs)
        except APIStatusError as e:
            if e.status_code not in (429, 503) or attempt == _RETRY_MAX - 1:
                raise
            delay = min(_RETRY_BASE * (2 ** attempt), _RETRY_CAP) + random.random()
            print(f"[vertex] HTTP {e.status_code} — retry {attempt+1}/{_RETRY_MAX} in {delay:.1f}s")
            time.sleep(delay)
    raise RuntimeError("call_with_retry exhausted — should not reach here")
