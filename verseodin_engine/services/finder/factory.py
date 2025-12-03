from enum import Enum
from typing import Dict, Optional, Type, Union

from .base import Finder
from .errors import FindError
from .finder_service import FinderService
from .url_processor import URLProcessorService


class FinderType(str, Enum):
    DEFAULT = "default"
    FINDER_SERVICE = "finder_service"


class FinderFactory:
    """Stateful factory for creating finder instances."""

    def __init__(self, processor: Optional[URLProcessorService] = None):
        self.processor = processor or URLProcessorService()
        self._registry: Dict[FinderType, Type[Finder]] = {
            FinderType.DEFAULT: FinderService,
            FinderType.FINDER_SERVICE: FinderService,
        }

    def register(self, kind: FinderType, impl: Type[Finder]) -> None:
        """Allow new finder backends to be added dynamically."""
        self._registry[kind] = impl

    def build(
        self,
        kind: Union[FinderType, str] = FinderType.DEFAULT,
        processor: Optional[URLProcessorService] = None,
    ) -> Finder:
        """Build a finder instance of the specified type."""

        # normalize kind
        if isinstance(kind, str):
            kind = FinderType(kind.lower())
        cls = self._registry.get(kind)
        if cls is None:
            raise FindError(f"No finder registered for {kind}")

        # Use provided processor or default
        proc = processor or self.processor

        return cls(processor=proc)
