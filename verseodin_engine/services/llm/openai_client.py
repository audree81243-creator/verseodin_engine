# services/llm/openai_client.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from openai import OpenAI

from .base import LLMClient
from .errors import LLMConnectionError, LLMGenerationError
from .schemas import LLMOptions, LLMRequest, LLMResponse


@dataclass
class OpenAIClient(LLMClient):
    client: Any
    options: LLMOptions

    def __init__(self, *, options: LLMOptions):
        if not options.api_key:
            raise LLMConnectionError("Missing API key for OpenAI")
        try:
            self.client = OpenAI(api_key=options.api_key)
            self.options = options
        except Exception as e:
            raise LLMConnectionError(f"Failed to initialize OpenAI client: {e}") from e

    def generate(self, request: LLMRequest) -> LLMResponse:
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        params: Dict[str, Any] = {"temperature": 0.0, **(self.options.model_params or {})}

        try:
            resp = self.client.chat.completions.create(
                model=self.options.model or "gpt-4o-mini",
                messages=messages,
                response_format={"type": "json_object"},
                **params,
            )
            text = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            raise LLMConnectionError(f"OpenAI request failed: {e}") from e

        if not text:
            raise LLMGenerationError("OpenAI returned empty response")

        parsed = None
        try:
            import json

            parsed = json.loads(text)
        except Exception:
            pass

        return LLMResponse(
            raw=parsed if parsed is not None else text,
            parsed=parsed,
            llm_client="openai",
            model=self.options.model,
            meta={"model_params": self.options.model_params},
        )
