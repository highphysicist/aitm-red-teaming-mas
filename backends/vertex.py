"""
backends/vertex.py
──────────────────
Thin ADC wrapper: token refresh + OpenAI-compatible client for Vertex AI MaaS.

google-auth caches the token internally and tracks expiry via .expiry.
Calling refresh() is a no-op when the token is still valid, so it is safe
to call get_token() before every LLM request without performance penalty.
"""

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
    """Return an OpenAI client pointing at Vertex AI MaaS with a fresh token."""
    return OpenAI(base_url=BASE_URL, api_key=get_token())
