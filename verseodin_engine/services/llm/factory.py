from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from decouple import config

from .base import LLMClient
from .errors import LLMAuthError, LLMError
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient
from .schemas import LLMOptions


class LLMClientType(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"


class LLMFactory:
    """Factory for creating concrete LLM clients."""

    def __init__(
        self,
        default_llm_client: LLMClientType = LLMClientType.OPENAI,
        default_model_openai: str = "gpt-4o-mini",
        default_model_gemini: str = "gemini-2.5-flash",
    ) -> None:
        self.default_llm_client = default_llm_client
        self.default_model_openai = default_model_openai
        self.default_model_gemini = default_model_gemini

    def build(
        self,
        llm_client: Union[LLMClientType, str, None] = None,
        *,
        options: Optional[LLMOptions] = None,
    ) -> LLMClient:
        """
        Build an LLM client.

        Args:
            llm_client: LLMClientType (or "openai" | "gemini").
              Defaults to factory.default_llm_client.
            model: Optional model name. If omitted, provider-specific defaults are used.
            api_key: Optional API key. If omitted, env vars are used:
                     - OPENAI  -> OPENAI_API_KEY
                     - GEMINI  -> GEMINI_API_KEY
            **kwargs: Passed through to the underlying client constructor.

        Returns:
            An initialized LLMClient instance.
        """
        # Normalize llm_client
        if llm_client is None:
            llm_client = self.default_llm_client
        if isinstance(llm_client, str):
            llm_client = LLMClientType(llm_client.lower())

        # OpenAI
        if llm_client is LLMClientType.OPENAI:
            model_name = options.model or self.default_model_openai
            key = (
                options.api_key
                if options.api_key is not None
                else config("OPENAI_API_KEY", default=None)
            )
            if not key:
                raise LLMAuthError("OPENAI_API_KEY is missing (pass api_key= or set env var).")
            return OpenAIClient(
                options=LLMOptions(api_key=key, model=model_name, model_params=options.model_params)
            )

        # Gemini
        if llm_client is LLMClientType.GEMINI:
            model_name = options.model or self.default_model_gemini
            key = (
                options.api_key
                if options.api_key is not None
                else config("GEMINI_API_KEY", default=None)
            )
            if not key:
                raise LLMAuthError("GEMINI_API_KEY is missing (pass api_key= or set env var).")
            return GeminiClient(
                options=LLMOptions(api_key=key, model=model_name, model_params=options.model_params)
            )

        # Should never happen
        raise LLMError(f"Unsupported llm_client: {llm_client!r}")
