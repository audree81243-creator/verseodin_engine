import asyncio
import json
import logging
import os
import time
import time as _time
from pathlib import Path
from typing import List, Optional, Dict, Tuple

from services.crawler.factory import CrawlerFactory, CrawlerType
from services.crawler.schemas import CrawlDoc, CrawlOptions
from services.finder.factory import FinderFactory, FinderType
from services.finder.schemas import FindDoc, FindOptions
from services.llm.factory import LLMFactory, LLMClientType
from services.llm.schemas import LLMOptions, LLMRequest, LLMResponse

from .base import QueryUniverseProcessor
from .config import (
    DEFAULT_LLM_PROMPT_TEMPLATE,
    DEFAULT_MAX_URLS_TO_CRAWL,
    MAX_PAGES_TO_CRAWLER,
    PRIORITY_PAGE_PATTERNS,
)
from .errors import QueryUniverseError
from .schemas import PipelineStage, QueryUniverseDoc, QueryUniverseOptions
from .utils import is_valid_url, normalize_url, select_urls_to_crawl


class QueryUniverseService(QueryUniverseProcessor):
    """Main service for processing queries through the entire pipeline."""

    def __init__(
        self,
        finder_factory: Optional[FinderFactory] = None,
        crawler_factory: Optional[CrawlerFactory] = None,
        llm_factory: Optional[LLMFactory] = None,
    ):
        self.finder_factory = finder_factory or FinderFactory()
        self.crawler_factory = crawler_factory or CrawlerFactory()
        self.llm_factory = llm_factory or LLMFactory()
        self.logger = logging.getLogger("query_universe_service")
        # Content limits
        self.max_chars_per_doc = 20000
        self.max_query_universe_context_chars = 400000
        self.default_llm_client = LLMClientType.GEMINI

        # Ensure LLM keys are loaded from project root .env if not already in env
        self._ensure_env_key("GEMINI_API_KEY")
        self._ensure_env_key("OPENAI_API_KEY")

    async def process(
        self,
        query: str,
        options: Optional[QueryUniverseOptions] = None,
    ) -> QueryUniverseDoc:
        """Process a query through finder -> crawler -> LLM pipeline."""
        
        start_time = time.time()
        
        if options is None:
            options = QueryUniverseOptions()

        self.logger.info("=" * 80)
        self.logger.info("QUERY UNIVERSE PROCESSOR")
        self.logger.info("=" * 80)
        self.logger.info(f"Query: {query}")

        # Initialize result document
        result = QueryUniverseDoc(query=query)

        try:
            # Step 1: Find URLs if query is a URL
            find_doc = None
            urls_to_crawl = []
            
            if is_valid_url(query):
                self.logger.info("\n[STEP 1] Finding URLs...")
                normalized_url = normalize_url(query)
                find_doc = await self._find_urls(normalized_url, options.find_options)
                result.find_doc = find_doc
                result.total_urls_found = find_doc.total_found if find_doc else 0
                
                if find_doc and find_doc.urls:
                    max_to_crawl = options.max_urls_to_crawl or MAX_PAGES_TO_CRAWLER
                    urls_to_crawl = select_urls_to_crawl(
                        urls=list(find_doc.urls),
                        max_urls=max_to_crawl,
                        homepage_url=find_doc.homepage_url,
                        priority_patterns=PRIORITY_PAGE_PATTERNS,
                    )
                    self.logger.info(f"Found {len(find_doc.urls)} URLs, selected {len(urls_to_crawl)} priority URLs to crawl")
            else:
                self.logger.info("\n[STEP 1] Query is not a URL, skipping finder step")
                # For non-URL queries, you might want to integrate with a search engine
                # For now, we'll just skip to LLM processing
                pass

            # Check if we should stop at finder stage
            if options.run_until_stage == PipelineStage.FINDER:
                result.completed_stage = "finder"
                result.processing_time = time.time() - start_time
                self.logger.info("\n" + "=" * 80)
                self.logger.info("STOPPED AT FINDER STAGE (as requested)")
                self.logger.info("=" * 80)
                return result

            # Step 2: Crawl selected URLs
            if urls_to_crawl:
                self.logger.info("\n[STEP 2] Crawling URLs...")
                crawl_docs = await self._crawl_urls(urls_to_crawl, options.crawl_options)
                result.crawl_docs = crawl_docs
                result.total_urls_crawled = len(crawl_docs)
                self.logger.info(f"Successfully crawled {len(crawl_docs)} URLs")
            else:
                self.logger.info("\n[STEP 2] No URLs to crawl")

            # Check if we should stop at crawler stage
            if options.run_until_stage == PipelineStage.CRAWLER:
                result.completed_stage = "crawler"
                result.processing_time = time.time() - start_time
                self.logger.info("\n" + "=" * 80)
                self.logger.info("STOPPED AT CRAWLER STAGE (as requested)")
                self.logger.info("=" * 80)
                return result

            # Step 3: Process with LLM if enabled
            if options.enable_llm_processing:
                self.logger.info("\n[STEP 3] Processing with LLM...")
                llm_responses, query_universe_prompts = await self._process_with_llm(
                    query=query,
                    crawl_docs=result.crawl_docs,
                    llm_options=options.llm_options,
                    prompt_template=options.llm_prompt_template,
                )
                result.llm_responses = llm_responses
                result.total_llm_calls = len(llm_responses)
                result.query_universe_prompts = query_universe_prompts
                self.logger.info(f"Generated {len(llm_responses)} LLM responses")
            else:
                self.logger.info("\n[STEP 3] LLM processing disabled")

            # Calculate processing time
            result.processing_time = time.time() - start_time
            result.completed_stage = "llm"

            self.logger.info("\n" + "=" * 80)
            self.logger.info("QUERY UNIVERSE PROCESSING COMPLETE")
            self.logger.info("=" * 80)
            self.logger.info(f"Total URLs found: {result.total_urls_found}")
            self.logger.info(f"Total URLs crawled: {result.total_urls_crawled}")
            self.logger.info(f"Total LLM calls: {result.total_llm_calls}")
            self.logger.info(f"Processing time: {result.processing_time:.2f}s")

            return result

        except Exception as e:
            self.logger.error(f"Error in query universe processing: {e}")
            raise QueryUniverseError(f"Failed to process query: {e}", query=query)

    async def _find_urls(
        self,
        url: str,
        find_options: Optional[FindOptions] = None,
    ) -> Optional[FindDoc]:
        """Find URLs using the finder service."""
        try:
            # Handle None values in find_options to prevent crashes
            if find_options is None:
                find_options = FindOptions()
            else:
                # Ensure max_depth and max_urls have valid values
                if find_options.max_depth is None:
                    find_options.max_depth = 12  # Default depth
                if find_options.max_urls is None:
                    find_options.max_urls = 50000  # Default max URLs
            
            finder = self.finder_factory.build(kind=FinderType.DEFAULT)
            find_doc = await finder.find_urls(url, options=find_options)
            
            # Close the finder's processor
            if hasattr(finder, 'processor') and hasattr(finder.processor, 'close'):
                await finder.processor.close()
            
            return find_doc
        except Exception as e:
            self.logger.error(f"Error finding URLs: {e}")
            return None

    async def _crawl_urls(
        self,
        urls: List[str],
        crawl_options: Optional[CrawlOptions] = None,
    ) -> List[CrawlDoc]:
        """Crawl multiple URLs using the crawler service."""
        crawl_docs = []
        
        # Build crawler
        crawler = self.crawler_factory.build(
            kind=CrawlerType.HTTPX,
            options=crawl_options,
        )
        
        # Crawl each URL
        for url in urls:
            try:
                self.logger.info(f"Crawling: {url}")
                crawl_doc = crawler.fetch(url, options=crawl_options)
                if crawl_doc and crawl_doc.status == 200:
                    crawl_docs.append(crawl_doc)
                    self.logger.info(f"✓ Success: {url}")
                else:
                    self.logger.warning(f"✗ Failed: {url} (status: {crawl_doc.status if crawl_doc else 'unknown'})")
            except Exception as e:
                self.logger.error(f"✗ Error crawling {url}: {e}")
        
        return crawl_docs

    async def _process_with_llm(
        self,
        query: str,
        crawl_docs: List[CrawlDoc],
        llm_options: Optional[LLMOptions] = None,
        prompt_template: Optional[str] = None,
    ) -> Tuple[List[LLMResponse], Optional[Dict[str, str]]]:
        """Process crawled content with LLM and build a query-universe prompt set."""
        llm_responses = []
        
        if not crawl_docs:
            self.logger.warning("No crawl docs to process with LLM")
            return llm_responses, None
        
        # Build LLM client
        if llm_options is None:
            llm_options = LLMOptions()
        
        try:
            llm_client = self.llm_factory.build(
                llm_client=self.default_llm_client,
                options=llm_options,
            )
        except Exception as e:
            self.logger.error(f"Error building LLM client: {e}")
            return llm_responses, None
        
        # Use default template if none provided
        template = prompt_template or DEFAULT_LLM_PROMPT_TEMPLATE
        
        # Build aggregated context from trimmed docs (first 20k chars each)
        trimmed_docs: List[str] = []
        for doc in crawl_docs:
            if not doc.md:
                continue
            snippet = doc.md[: self.max_chars_per_doc]
            if not snippet:
                continue
            trimmed_docs.append(f"URL: {doc.url}\nContent:\n{snippet}")

        if not trimmed_docs:
            return llm_responses, None

        context = "\n\n-----\n\n".join(trimmed_docs)
        if len(context) > self.max_query_universe_context_chars:
            context = context[: self.max_query_universe_context_chars]

        user_prompt = (
            "You are building a 'query universe' for this site to optimize GEO (Generative Engine Optimization). "
            "Use ONLY the context below. Return a JSON object with numeric string keys (\"1\", \"2\", ...). "
            "Each value must be a standalone, user-intent question the site should rank for. "
            "Do NOT use the brand name or vague pronouns (no \"this platform\", \"these tools\", \"their\"). "
            "Instead, restate the product/domain/sector explicitly in each question (e.g., "
            "\"an international payments platform for freelancers in India\", \"a B2B SaaS for cross-border FX\"), "
            "derived from the context. "
            "Focus on user intent, authority/credibility, entities/terminology, freshness, and fact-rich asks "
            "(stats, comparisons, how-to, risks, benefits, compliance, pricing, setup, performance). "
            "Produce 80-100 high-quality, non-duplicative questions. "
            "Return ONLY the JSON object—no prose, no markdown.\n\n"
            f"Context:\n{context}\n\n"
            "Now produce ONLY the JSON object with 80-100 questions."
        )

        llm_request = LLMRequest(
            user_prompt=user_prompt,
            system_prompt="You are a helpful assistant that produces ONLY the requested JSON object.",
        )

        try:
            llm_response = llm_client.generate(llm_request)
            llm_responses.append(llm_response)
            query_universe_prompts = self._parse_query_universe_response(llm_response)
        except Exception as e:
            # Retry once after 60s on quota/rate errors
            err_str = str(e).lower()
            if "quota" in err_str or "rate" in err_str or "429" in err_str:
                self.logger.error(f"Rate/quota error, retrying once after 60s: {e}")
                try:
                    _time.sleep(60)
                    llm_response = llm_client.generate(llm_request)
                    llm_responses.append(llm_response)
                    query_universe_prompts = self._parse_query_universe_response(llm_response)
                except Exception as e2:
                    self.logger.error(f"✗ Error generating query universe prompts after retry: {e2}")
                    query_universe_prompts = None
            else:
                self.logger.error(f"✗ Error generating query universe prompts: {e}")
                query_universe_prompts = None

        return llm_responses, query_universe_prompts

    def _parse_query_universe_response(self, llm_response) -> Optional[Dict[str, str]]:
        raw = getattr(llm_response, "raw", None) or llm_response
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}

        text = str(raw)
        # Strip code fences if present
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                candidate = parts[1]
                if candidate.strip().startswith("json"):
                    candidate = candidate.split("\n", 1)[1] if "\n" in candidate else candidate
                text = candidate
        text = text.strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            pass

        return {"raw": text}

    def _ensure_env_key(self, key: str) -> None:
        """Load a secret from the repo root .env into os.environ if not already set."""
        if os.getenv(key):
            return
        candidates = [
            Path(__file__).resolve().parents[2] / ".env",  # backend/.env
            Path(__file__).resolve().parents[3] / ".env",  # repo root /.env
        ]
        env_path = next((p for p in candidates if p.exists()), None)
        if not env_path:
            return
        try:
            from decouple import Config, RepositoryEnv
            cfg = Config(RepositoryEnv(str(env_path)))
            val = cfg(key, default=None)
            if val:
                os.environ[key] = val
        except Exception:
            return


async def process_query_universe(
    query: str,
    options: Optional[QueryUniverseOptions] = None,
) -> QueryUniverseDoc:
    """Convenience function to process a query through the query universe pipeline."""
    service = QueryUniverseService()
    return await service.process(query, options)
