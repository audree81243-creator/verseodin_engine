"""
Tasks module for query universe service.

This module can contain Celery tasks or other background job definitions
for asynchronous query universe processing.
"""

import logging
from typing import Optional

from .factory import QueryUniverseFactory, QueryUniverseType
from .schemas import QueryUniverseDoc, QueryUniverseOptions

logger = logging.getLogger("query_universe_tasks")


async def async_process_query_universe(
    query: str,
    options: Optional[QueryUniverseOptions] = None,
) -> QueryUniverseDoc:
    """
    Asynchronous task to process a query through the query universe pipeline.
    
    Args:
        query: The search query or URL to process
        options: Configuration options for the query universe processing
        
    Returns:
        QueryUniverseDoc containing all results
    """
    factory = QueryUniverseFactory()
    processor = factory.build(kind=QueryUniverseType.DEFAULT)
    
    try:
        result = await processor.process(query, options)
        return result
    except Exception as e:
        logger.error(f"Error in async_process_query_universe: {e}")
        raise


# Placeholder for Celery task
# Uncomment and configure when Celery is set up
# 
# from celery import shared_task
# 
# @shared_task
# def celery_process_query_universe(query: str, options_dict: dict = None):
#     """Celery task wrapper for query universe processing."""
#     import asyncio
#     
#     options = None
#     if options_dict:
#         options = QueryUniverseOptions(**options_dict)
#     
#     result = asyncio.run(async_process_query_universe(query, options))
#     return result
