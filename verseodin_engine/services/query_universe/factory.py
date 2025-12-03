from enum import Enum
from typing import Dict, Optional, Type, Union

from services.crawler.factory import CrawlerFactory
from services.finder.factory import FinderFactory
from services.llm.factory import LLMFactory

from .base import QueryUniverseProcessor
from .errors import QueryUniverseError
from .query_universe_service import QueryUniverseService


class QueryUniverseType(str, Enum):
    DEFAULT = "default"
    QUERY_UNIVERSE_SERVICE = "query_universe_service"


class QueryUniverseFactory:
    """Stateful factory for creating query universe processor instances."""

    def __init__(
        self,
        finder_factory: Optional[FinderFactory] = None,
        crawler_factory: Optional[CrawlerFactory] = None,
        llm_factory: Optional[LLMFactory] = None,
    ):
        self.finder_factory = finder_factory or FinderFactory()
        self.crawler_factory = crawler_factory or CrawlerFactory()
        self.llm_factory = llm_factory or LLMFactory()
        
        self._registry: Dict[QueryUniverseType, Type[QueryUniverseProcessor]] = {
            QueryUniverseType.DEFAULT: QueryUniverseService,
            QueryUniverseType.QUERY_UNIVERSE_SERVICE: QueryUniverseService,
        }

    def register(self, kind: QueryUniverseType, impl: Type[QueryUniverseProcessor]) -> None:
        """Allow new query universe backends to be added dynamically."""
        self._registry[kind] = impl

    def build(
        self,
        kind: Union[QueryUniverseType, str] = QueryUniverseType.DEFAULT,
        finder_factory: Optional[FinderFactory] = None,
        crawler_factory: Optional[CrawlerFactory] = None,
        llm_factory: Optional[LLMFactory] = None,
    ) -> QueryUniverseProcessor:
        """Build a query universe processor instance of the specified type."""

        # normalize kind
        if isinstance(kind, str):
            kind = QueryUniverseType(kind.lower())
        cls = self._registry.get(kind)
        if cls is None:
            raise QueryUniverseError(f"No query universe processor registered for {kind}")

        # Use provided factories or defaults
        finder_fac = finder_factory or self.finder_factory
        crawler_fac = crawler_factory or self.crawler_factory
        llm_fac = llm_factory or self.llm_factory

        return cls(
            finder_factory=finder_fac,
            crawler_factory=crawler_fac,
            llm_factory=llm_fac,
        )
