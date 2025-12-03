"""
Example: Run FINDER + CRAWLER stages (no LLM)
This will discover URLs and crawl them, but not process with LLM.

Usage:
    cd /home/saumya/verseodin/backend
    python3 -m services.query_universe.run_until_crawler
"""
import asyncio
import logging

from services.crawler.schemas import CrawlOptions
from services.finder.schemas import FindOptions
from services.llm.schemas import LLMOptions

from .config import PROXY_URL
from .factory import QueryUniverseFactory, QueryUniverseType
from .schemas import PipelineStage, QueryUniverseOptions


async def main():
    """Run finder and crawler stages only."""

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("run_until_crawler")

    # Test URL
    url = "https://www.merlinai.co/"
    
    # Create factory
    factory = QueryUniverseFactory()

    logger.info("=" * 80)
    logger.info("RUNNING FINDER + CRAWLER STAGES")
    logger.info("=" * 80)

    # Build query universe processor
    processor = factory.build(kind=QueryUniverseType.DEFAULT)

    try:
        # Create options - RUN UNTIL CRAWLER
        options = QueryUniverseOptions(
            find_options=FindOptions(
                max_depth=12,
                max_urls=50000,
                proxy=PROXY_URL,
            ),
            crawl_options=CrawlOptions(
                proxy=PROXY_URL,
                timeout_ms=3000000,
            ),
            max_urls_to_crawl=20,
            run_until_stage=PipelineStage.CRAWLER,  # ← STOP AT CRAWLER!
        )

        # Process query
        result = await processor.process(url, options)

        # Display results
        logger.info("\n" + "=" * 80)
        logger.info("FINDER + CRAWLER RESULTS")
        logger.info("=" * 80)
        logger.info(f"Query: {result.query}")
        logger.info(f"Completed Stage: {result.completed_stage}")
        logger.info(f"Total URLs found: {result.total_urls_found}")
        logger.info(f"Total URLs crawled: {result.total_urls_crawled}")
        logger.info(f"Processing time: {result.processing_time:.2f}s")

        if result.find_doc:
            logger.info(f"\nFinder Results:")
            logger.info(f"  - Domain: {result.find_doc.domain}")
            logger.info(f"  - URLs found: {len(result.find_doc.urls)}")

        if result.crawl_docs:
            logger.info(f"\nCrawled URLs ({len(result.crawl_docs)}):")
            for i, doc in enumerate(result.crawl_docs, 1):
                content_preview = doc.md[:100] + "..." if len(doc.md) > 100 else doc.md
                logger.info(f"  {i}. {doc.url}")
                logger.info(f"     Status: {doc.status}, Content length: {len(doc.md)} chars")
                logger.info(f"     Preview: {content_preview}")

        # Verify LLM didn't run
        logger.info(f"\nLLM ran: {len(result.llm_responses) > 0}")  # Should be False

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
