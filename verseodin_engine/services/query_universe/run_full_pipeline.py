"""
Example: Run FULL pipeline (FINDER + CRAWLER + LLM)
This is the default behavior - runs all stages.

python3 -m services.query_universe.run_full_pipeline
"""
import asyncio
import logging
import json
import os

from decouple import config
from services.crawler.schemas import CrawlOptions
from services.finder.schemas import FindOptions
from services.llm.schemas import LLMOptions

from .config import PROXY_URL
from .factory import QueryUniverseFactory, QueryUniverseType
from .schemas import PipelineStage, QueryUniverseOptions


async def main():
    """Run all stages: finder, crawler, and LLM."""

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("run_full_pipeline")

    # Test URL
    url = "https://www.infinityapp.in/"
    
    # Load LLM key explicitly to avoid resolution issues
    gemini_key = os.getenv("GEMINI_API_KEY") or config("GEMINI_API_KEY", default=None)

    # Create factory
    factory = QueryUniverseFactory()

    logger.info("=" * 80)
    logger.info("RUNNING FULL PIPELINE (ALL STAGES)")
    logger.info("=" * 80)

    # Build query universe processor
    processor = factory.build(kind=QueryUniverseType.DEFAULT)

    try:
        # Create options - RUN ALL STAGES
        options = QueryUniverseOptions(
            find_options=FindOptions(
                max_depth=6,
                max_urls=1000,
                proxy=PROXY_URL,
            ),
            crawl_options=CrawlOptions(
                proxy=PROXY_URL,
                timeout_ms=30000,
            ),
            llm_options=LLMOptions(
                model="gemini-2.0-flash",
                api_key=gemini_key,
            ),
            max_urls_to_crawl=20,
            enable_llm_processing=True,
            run_until_stage=PipelineStage.LLM,  # ← RUN ALL STAGES (default)
        )

        # Process query
        result = await processor.process(url, options)

        # Display results
        logger.info("\n" + "=" * 80)
        logger.info("COMPLETE RESULTS (ALL STAGES)")
        logger.info("=" * 80)
        logger.info(f"Query: {result.query}")
        logger.info(f"Completed Stage: {result.completed_stage}")
        logger.info(f"Total URLs found: {result.total_urls_found}")
        logger.info(f"Total URLs crawled: {result.total_urls_crawled}")
        logger.info(f"Total LLM calls: {result.total_llm_calls}")
        logger.info(f"Processing time: {result.processing_time:.2f}s")

        if result.find_doc:
            logger.info(f"\nFinder Results:")
            logger.info(f"  - Homepage: {result.find_doc.homepage_url}")
            logger.info(f"  - Domain: {result.find_doc.domain}")

        if result.crawl_docs:
            logger.info(f"\nCrawled URLs ({len(result.crawl_docs)}):")
            for i, doc in enumerate(result.crawl_docs[:3], 1):
                logger.info(f"  {i}. {doc.url} (status: {doc.status})")

        if result.llm_responses:
            logger.info(f"\nLLM Responses ({len(result.llm_responses)}):")
            for i, response in enumerate(result.llm_responses[:3], 1):
                preview = str(response.raw)[:200] + "..." if len(str(response.raw)) > 200 else str(response.raw)
                logger.info(f"  {i}. {preview}")
            if len(result.llm_responses) > 3:
                logger.info(f"  ... and {len(result.llm_responses) - 3} more")

        if result.query_universe_prompts:
            logger.info("\nQuery Universe Prompts (full JSON):")
            logger.info(json.dumps(result.query_universe_prompts, indent=2))
        else:
            logger.info("\nQuery Universe Prompts: None")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
