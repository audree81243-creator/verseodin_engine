# services/llm/schemas.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union


@dataclass
class LLMOptions:
    """Config for generation calls."""

    model: Optional[str] = None
    api_key: Optional[str] = None
    model_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMRequest:
    user_prompt: str = None
    system_prompt: Optional[str] = None


@dataclass
class LLMResponse:
    """Normalized LLM response."""

    raw: Union[str, Dict[str, Any]]
    parsed: Optional[Dict[str, Any]] = None
    llm_client: Optional[str] = None
    model: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
