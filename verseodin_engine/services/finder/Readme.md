This service implements a focused URL-discovery. Its job is to find candidate URLs from a starting site, apply filtering and deduplication, and hand results back to the rest of the system (or insert them into the DB via Celery tasks).

- NOTE: The service is async-first

What it does 

- Start from a single address (homepage or any URL) and explore linked pages up to a configured depth and limit.
- Collect links, drop duplicates.
- Filter out irrelevant file types (common examples): images (.jpg, .jpeg, .png, .gif, .svg, .webp, .bmp), audio/video (.mp3, .wav, .mp4, .avi, .mov, .mkv), documents (.pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx), archives (.zip, .tar, .gz, .rar, .7z), styles/scripts (.css, .js), fonts (.woff, .woff2, .ttf). The exact list is configurable in config.py.
- Return a compact result with the discovered URLs and basic stats, or enqueue the results for downstream processing.

Inputs and their expected Outputs

- Required Fields
1. Top level domain/ Base URL

- Optional Fields
1. Max Depth (default=1)
2. Max URLs  (default=200) 
3. Proxy 

After successful run, the URL Status is set to NEW, else FAILED

How it works 

1. Normalize the input and determine the site root (see [`extract_homepage_from_url`](backend/services/finder/utils.py)).  
2. Initialize the URL processor and crawler pieces (wired by [`FinderFactory`](backend/services/finder/factory.py)).  
3. Run a breadth-by-depth discovery loop implemented by [`finder.finder_service.FinderService`](backend/services/finder/finder_service.py): fetch pages, extract links, dedupe and filter, repeat up to the configured depth and limit.  
4. Finalize and return a compact document describing the outcome (`FindDoc`) and configuration used (`FindOptions`) — see [`finder.schemas.FindOptions`](backend/services/finder/schemas.py) and [`finder.schemas.FindDoc`](backend/services/finder/schemas.py).  
5. In production, the Celery task [`url_finder`](backend/services/finder/tasks.py) is the entrypoint used by management commands and the API.

