import asyncio
import logging

from logger.config import init_logging
from logger.context import new_request_id

from .factory import FinderFactory, FinderType
from .schemas import FindOptions


async def main():
    """Test the finder service implementations."""

    # Initialize logging
    init_logging()
    new_request_id()
    logger = logging.getLogger("finder_run")

    url = "https://www.city.chiyoda.lg.jp/"
    factory = FinderFactory()

    logger.info("=" * 80)
    logger.info("TESTING CHIYODA CRAWLER - HIGH PERFORMANCE")
    logger.info("=" * 80)

    # Test finder service
    finder = factory.build(kind=FinderType.DEFAULT)

    try:
        # Create FindOptions for the new interface (uses defaults from dataclass)
        options = FindOptions(
            proxy=None,
        )

        find_doc = await finder.find_urls(url, options)

        logger.info(f"Final Result: Found {len(find_doc.urls)} URLs")
        logger.info("First 10 URLs:")
        urls_list = sorted(list(find_doc.urls))
        for i, sample_url in enumerate(urls_list[:10], 1):
            logger.info(f"  {i}. {sample_url}")

        if len(urls_list) > 10:
            logger.info(f"  ... and {len(urls_list) - 10} more URLs")

    finally:
        await finder.processor.close()


if __name__ == "__main__":
    asyncio.run(main())
