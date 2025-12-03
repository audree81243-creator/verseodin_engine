# services/llm/gemini_client.py
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict

import google.generativeai as genai

from .base import LLMClient
from .errors import LLMConnectionError, LLMGenerationError
from .schemas import LLMOptions, LLMRequest, LLMResponse


@dataclass
class GeminiClient(LLMClient):
    model: Any
    options: LLMOptions

    def __init__(self, *, options: LLMOptions):
        # configure SDK
        try:
            if not options.api_key:
                raise LLMConnectionError("Missing API key for Gemini")
            genai.configure(api_key=options.api_key)
            model_name = options.model or "gemini-2.5-flash-lite"
            self.model = genai.GenerativeModel(model_name)
            self.options = options
        except Exception as e:
            raise LLMConnectionError(f"Failed to initialize Gemini model: {e}") from e

    def generate(self, request: LLMRequest) -> LLMResponse:
        cfg: Dict[str, Any] = {"temperature": 0.0, **(self.options.model_params or {})}
        # Gemini takes a list of strings; place system first if present
        messages = []
        if request.system_prompt:
            messages.append(request.system_prompt)
        messages.append(request.user_prompt)

        # Default to JSON output if caller didn't specify a mime type
        if "response_mime_type" not in cfg:
            cfg["response_mime_type"] = "application/json"

        try:
            resp = self.model.generate_content(messages, generation_config=cfg)
            text = (getattr(resp, "text", "") or "").strip()
        except Exception as e:
            raise LLMConnectionError(f"Gemini request failed: {e}") from e

        if not text:
            raise LLMGenerationError("Gemini returned empty response")

        parsed = None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            pass

        return LLMResponse(
            raw=parsed if parsed is not None else text,
            parsed=parsed,
            llm_client="gemini",
            model=self.options.model,
            meta={"model_params": self.options.model_params},
        )
