# Query Universe Service

The Query Universe Service provides a unified pipeline for processing queries through multiple stages: URL finding, web crawling, and LLM-based content analysis.

## Architecture

The service follows the same architectural pattern as the `finder` module:

- **Base Classes**: Abstract interfaces defining the contract (`QueryUniverseProcessor`)
- **Schemas**: Data models for options and results (`QueryUniverseOptions`, `QueryUniverseDoc`)
- **Factory**: Factory pattern for creating service instances (`QueryUniverseFactory`)
- **Service**: Concrete implementation (`QueryUniverseService`)
- **Errors**: Custom exception types (`QueryUniverseError`)
- **Utils**: Helper functions
- **Config**: Configuration constants

## Features

- **URL Finding**: Uses the `finder` module to discover URLs from a given domain
- **Web Crawling**: Uses the `crawler` module to fetch content from discovered URLs
- **LLM Processing**: Uses the `llm` module to generate responses based on crawled content
- **Flexible Configuration**: All stages are configurable via `QueryUniverseOptions`
- **Modular Design**: Can enable/disable individual stages as needed

## Usage

### Basic Usage

```python
import asyncio
from services.query_universe import process_query_universe, QueryUniverseOptions

async def main():
    # Simple usage with defaults
    result = await process_query_universe("https://example.com")
    
    print(f"Found {result.total_urls_found} URLs")
    print(f"Crawled {result.total_urls_crawled} pages")
    print(f"Generated {result.total_llm_calls} LLM responses")

asyncio.run(main())
```

### Advanced Usage with Custom Options

```python
from services.query_universe import (
    QueryUniverseFactory,
    QueryUniverseType,
    QueryUniverseOptions,
)
from services.finder.schemas import FindOptions
from services.crawler.schemas import CrawlOptions
from services.llm.schemas import LLMOptions

async def main():
    # Create custom options
    options = QueryUniverseOptions(
        find_options=FindOptions(
            max_depth=3,
            max_urls=100,
        ),
        crawl_options=CrawlOptions(
            timeout_ms=30000,
        ),
        llm_options=LLMOptions(
            model="gpt-4o-mini",
        ),
        max_urls_to_crawl=5,
        enable_llm_processing=True,
        llm_prompt_template="Custom prompt: {query}\nContent: {content}",
    )
    
    # Create processor via factory
    factory = QueryUniverseFactory()
    processor = factory.build(kind=QueryUniverseType.DEFAULT)
    
    # Process query
    result = await processor.process("https://example.com", options)
    
    # Access results
    if result.find_doc:
        print(f"Domain: {result.find_doc.domain}")
        print(f"URLs: {len(result.find_doc.urls)}")
    
    for crawl_doc in result.crawl_docs:
        print(f"Crawled: {crawl_doc.url} (status: {crawl_doc.status})")
    
    for llm_response in result.llm_responses:
        print(f"LLM Response: {llm_response.raw[:100]}...")

asyncio.run(main())
```

### Using with Custom Factories

```python
from services.query_universe import QueryUniverseFactory
from services.finder.factory import FinderFactory
from services.crawler.factory import CrawlerFactory
from services.llm.factory import LLMFactory

# Create custom factories with specific configurations
finder_factory = FinderFactory()
crawler_factory = CrawlerFactory()
llm_factory = LLMFactory(default_model_openai="gpt-4")

# Create query universe factory with custom factories
factory = QueryUniverseFactory(
    finder_factory=finder_factory,
    crawler_factory=crawler_factory,
    llm_factory=llm_factory,
)

processor = factory.build()
result = await processor.process("https://example.com")
```

## Configuration

### Default Values Protection

The service automatically ensures safe default values:
- If `max_depth` is `None`, it defaults to `12`
- If `max_urls` is `None`, it defaults to `50000`

This prevents crashes when options are not fully specified.

The service can be configured via environment variables:

```bash
# Query Universe specific
QUERY_UNIVERSE_MAX_URLS=10
QUERY_UNIVERSE_ENABLE_LLM=True
QUERY_UNIVERSE_DEBUG=True

# Finder configuration (inherited)
REQUIRE_PROXY=False
PROXY_DEBUG=True

# Crawler configuration (inherited)
PROXY_URL=http://user:pass@proxy:port

# LLM configuration (inherited)
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key
```

## Pipeline Stages

### 1. URL Finding (Optional)

If the input query is a valid URL, the service uses the `finder` module to discover related URLs:

- Crawls the domain to find all accessible pages
- Respects depth and URL limits
- Returns a `FindDoc` with all discovered URLs

### 2. URL Selection

From the discovered URLs (or provided URLs), the service selects a subset to crawl:

- Configurable via `max_urls_to_crawl`
- Currently uses simple first-N selection
- Future: Could implement smarter prioritization

### 3. Web Crawling

Selected URLs are crawled using the `crawler` module:

- Fetches HTML content
- Converts to Markdown
- Handles errors gracefully
- Returns `CrawlDoc` objects

### 4. LLM Processing (Optional)

If enabled, crawled content is processed with an LLM:

- Configurable via `enable_llm_processing`
- Uses customizable prompt templates
- Supports multiple LLM providers (OpenAI, Gemini)
- Returns `LLMResponse` objects

## Error Handling

The service includes comprehensive error handling:

- `QueryUniverseError`: Main exception type
- Individual stage errors are logged but don't stop the pipeline
- Partial results are returned even if some stages fail

## Testing

Run the test script:

```bash
cd /home/saumya/verseodin/backend
python -m services.query_universe.run
```

## Integration with Other Services

The Query Universe Service integrates with:

- **Finder Service**: URL discovery and site mapping
- **Crawler Service**: Content fetching and parsing
- **LLM Service**: AI-powered content analysis

All services are used via their respective factories, ensuring loose coupling and easy testing.

## Future Enhancements

- Search engine integration for non-URL queries
- Smarter URL selection algorithms
- Batch processing for multiple queries
- Result caching
- Support for custom processing stages
- Integration with vector databases for semantic search
