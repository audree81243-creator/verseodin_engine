import asyncio
import logging

from services.crawler.schemas import CrawlOptions
from services.finder.schemas import FindOptions
from services.llm.schemas import LLMOptions

from .config import PROXY_URL
from .factory import QueryUniverseFactory, QueryUniverseType
from .schemas import QueryUniverseOptions


async def main():
    """Test the query universe service implementation."""

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("query_universe_run")

    # Test URL
    url = "https://www.city.chiyoda.lg.jp/"
    
    # Create factory
    factory = QueryUniverseFactory()

    logger.info("=" * 80)
    logger.info("TESTING QUERY UNIVERSE SERVICE")
    logger.info("=" * 80)

    # Build query universe processor
    processor = factory.build(kind=QueryUniverseType.DEFAULT)

    try:
        # Create options
        options = QueryUniverseOptions(
            find_options=FindOptions(
                max_depth=2,
                max_urls=100,
                proxy=PROXY_URL,
            ),
            crawl_options=CrawlOptions(
                proxy=PROXY_URL,
                timeout_ms=30000,
            ),
            llm_options=LLMOptions(
                model="gpt-4o-mini",
            ),
            max_urls_to_crawl=20,  # Maximum priority pages to crawl
            enable_llm_processing=True,
        )

        # Process query
        result = await processor.process(url, options)

        # Display results
        logger.info("\n" + "=" * 80)
        logger.info("RESULTS")
        logger.info("=" * 80)
        logger.info(f"Query: {result.query}")
        logger.info(f"Total URLs found: {result.total_urls_found}")
        logger.info(f"Total URLs crawled: {result.total_urls_crawled}")
        logger.info(f"Total LLM calls: {result.total_llm_calls}")
        logger.info(f"Processing time: {result.processing_time:.2f}s")

        if result.find_doc:
            logger.info(f"\nFinder Results:")
            logger.info(f"  - Homepage: {result.find_doc.homepage_url}")
            logger.info(f"  - Domain: {result.find_doc.domain}")
            logger.info(f"  - Max depth reached: {result.find_doc.max_depth_reached}")
            logger.info(f"  - Successful crawls: {result.find_doc.successful_crawls}")
            logger.info(f"  - Failed crawls: {result.find_doc.failed_crawls}")

        if result.crawl_docs:
            logger.info(f"\nCrawled URLs ({len(result.crawl_docs)}):")
            for i, doc in enumerate(result.crawl_docs[:5], 1):
                logger.info(f"  {i}. {doc.url} (status: {doc.status})")
            if len(result.crawl_docs) > 5:
                logger.info(f"  ... and {len(result.crawl_docs) - 5} more")

        if result.llm_responses:
            logger.info(f"\nLLM Responses ({len(result.llm_responses)}):")
            for i, response in enumerate(result.llm_responses[:3], 1):
                preview = str(response.raw)[:200] + "..." if len(str(response.raw)) > 200 else str(response.raw)
                logger.info(f"  {i}. {preview}")
            if len(result.llm_responses) > 3:
                logger.info(f"  ... and {len(result.llm_responses) - 3} more")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
