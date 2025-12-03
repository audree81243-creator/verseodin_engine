from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from services.crawler.schemas import CrawlDoc, CrawlOptions
from services.finder.schemas import FindDoc, FindOptions
from services.llm.schemas import LLMOptions, LLMResponse


class PipelineStage(str, Enum):
    """Enum for pipeline stages."""
    FINDER = "finder"
    CRAWLER = "crawler"
    LLM = "llm"


@dataclass
class QueryUniverseOptions:
    """Configuration options for query universe processing."""

    # Finder options
    find_options: Optional[FindOptions] = None
    
    # Crawler options
    crawl_options: Optional[CrawlOptions] = None
    
    # LLM options
    llm_options: Optional[LLMOptions] = None
    
    # Query universe specific options
    max_urls_to_crawl: Optional[int] = 20
    enable_llm_processing: Optional[bool] = True
    llm_prompt_template: Optional[str] = None
    
    # Pipeline control - NEW!
    run_until_stage: Optional[PipelineStage] = PipelineStage.LLM  # Run all stages by default
    
    # Additional options
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryUniverseDoc:
    """Result document from query universe processing."""
    
    query: str
    find_doc: Optional[FindDoc] = None
    crawl_docs: List[CrawlDoc] = field(default_factory=list)
    llm_responses: List[LLMResponse] = field(default_factory=list)
    query_universe_prompts: Optional[Dict[str, str]] = None
    total_urls_found: int = 0
    total_urls_crawled: int = 0
    total_llm_calls: int = 0
    processing_time: float = 0.0
    completed_stage: Optional[str] = None  # NEW - tracks which stage was completed
    meta: Dict[str, Any] = field(default_factory=dict)
