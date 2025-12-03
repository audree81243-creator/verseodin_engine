"""
Example: Run only the FINDER stage
This will discover URLs but not crawl or process with LLM.

Usage:
    cd /home/saumya/verseodin/backend
    python3 -m services.query_universe.run_finder_only
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
    """Run only the finder stage."""

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("run_finder_only")

    # Test URL
    url = "https://www.hollisterco.com/shop/am"
    
    # Create factory
    factory = QueryUniverseFactory()

    logger.info("=" * 80)
    logger.info("RUNNING FINDER STAGE ONLY")
    logger.info("=" * 80)

    # Build query universe processor
    processor = factory.build(kind=QueryUniverseType.DEFAULT)

    try:
        # Create options - ONLY RUN FINDER
        options = QueryUniverseOptions(
            find_options=FindOptions(
                max_depth=12,
                max_urls=50000,
                proxy="http://account-indigodata-pipeline-nimbleip-country-JP:9S6p318zUks3@ip.nimbleway.com:7000",
            ),
            run_until_stage=PipelineStage.FINDER,  # ← STOP AT FINDER!
        )

        # Process query
        result = await processor.process(url, options)

        # Display results
        logger.info("\n" + "=" * 80)
        logger.info("FINDER RESULTS")
        logger.info("=" * 80)
        logger.info(f"Query: {result.query}")
        logger.info(f"Completed Stage: {result.completed_stage}")
        logger.info(f"Total URLs found: {result.total_urls_found}")
        logger.info(f"Processing time: {result.processing_time:.2f}s")

        if result.find_doc:
            logger.info(f"\nFinder Details:")
            logger.info(f"  - Homepage: {result.find_doc.homepage_url}")
            logger.info(f"  - Domain: {result.find_doc.domain}")
            logger.info(f"  - Max depth reached: {result.find_doc.max_depth_reached}")
            logger.info(f"  - Successful crawls: {result.find_doc.successful_crawls}")
            logger.info(f"  - Failed crawls: {result.find_doc.failed_crawls}")
            
            logger.info(f"\n  Found URLs (first 10):")
            for i, url in enumerate(sorted(result.find_doc.urls)[:10], 1):
                logger.info(f"    {i:2d}. {url}")
            if len(result.find_doc.urls) > 10:
                logger.info(f"    ... and {len(result.find_doc.urls) - 10} more")

        # Verify crawler and LLM didn't run
        logger.info(f"\nCrawler ran: {len(result.crawl_docs) > 0}")  # Should be False
        logger.info(f"LLM ran: {len(result.llm_responses) > 0}")      # Should be False

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
