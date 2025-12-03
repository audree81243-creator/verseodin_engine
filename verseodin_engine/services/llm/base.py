from __future__ import annotations

from abc import ABC, abstractmethod

from services.llm.schemas import LLMRequest, LLMResponse


class LLMClient(ABC):
    """LLM interface so you can swap OpenAI, Gemini, etc."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate a response from the model.

        Args:
            user_prompt: The main user query.
            system_prompt: An optional system-level instruction.
            model_params: Optional model-specific config (temperature, top_p, etc.).

        Returns:
            Model response, either as text or parsed dict.
        """
        raise NotImplementedError
