# services/llm/errors.py
class LLMError(RuntimeError):
    """Base class for all LLM-related errors."""


class LLMConnectionError(LLMError):
    """Raised when connection to the LLM provider fails."""


class LLMAuthError(LLMError):
    """Raised when authentication (API key) is missing or invalid."""


class LLMGenerationError(LLMError):
    """Raised when the LLM fails to generate a valid response."""

    def __init__(self, message="LLM generation failed", details=None):
        super().__init__(message)
        self.details = details
