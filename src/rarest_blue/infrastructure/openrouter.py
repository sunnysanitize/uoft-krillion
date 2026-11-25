"""OpenRouter adapter: the PromptWriter port backed by an LLM."""

from __future__ import annotations

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter's search tool: the model picks its own queries and may search more than once. Native search for models
# that have it, Exa otherwise; billed per search on top of tokens.
WEB_SEARCH_TOOL = {"type": "openrouter:web_search", "parameters": {"max_results": 5}}
REQUEST_TIMEOUT_SECONDS = 420


class OpenRouterWriter:
    def __init__(self, api_key: str, url: str = OPENROUTER_URL, timeout: float = REQUEST_TIMEOUT_SECONDS):
        self._api_key = api_key
        self._url = url
        self._timeout = timeout

    def write(
        self, request: str, model: str, response_schema: dict, temperature: float, web_search: bool = False
    ) -> str:
        # Checked per call, not at startup, so a run that finds the day already stored needs no key.
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        body = {
            "model": model,
            "messages": [{"role": "user", "content": request}],
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "reply", "strict": True, "schema": response_schema},
            },
        }
        if web_search:
            body["tools"] = [WEB_SEARCH_TOOL]
        response = httpx.post(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}", "X-Title": "UofT Krillion"},
            json=body,
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise ValueError(f"OpenRouter error: {body['error']}")
        return body["choices"][0]["message"]["content"] or ""
