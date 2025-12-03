from abc import ABC, abstractmethod
from typing import Optional

from .schemas import QueryUniverseDoc, QueryUniverseOptions


class QueryUniverseProcessor(ABC):
    @abstractmethod
    async def process(
        self,
        query: str,
        options: Optional[QueryUniverseOptions] = None,
    ) -> QueryUniverseDoc:
        """Process a query to find URLs, crawl them, and generate LLM responses.
        
        Args:
            query: The search query or URL to process
            options: Configuration options for the query universe processing
            
        Returns:
            QueryUniverseDoc containing all results
        """
        ...
