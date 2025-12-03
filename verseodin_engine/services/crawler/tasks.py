from __future__ import annotations

from typing import Any, Dict, List, Tuple

from celery import chord, current_app, group, shared_task
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from core.models import URL, InputState, Status, URLStatus
from services.crawler import CrawlerFactory, CrawlerType, CrawlOptions

CLAIMABLE: Tuple[str, ...] = (Status.PENDING,)


def _validate(state: InputState) -> Dict[str, Any]:
    strategy = (state.url_crawler_strategy or "HTTPX").strip().upper()
    proxy = (state.url_crawler_proxy or "").strip()
    if not proxy:
        raise ValueError("Missing url_crawler_proxy on InputState (proxy is required)")
    if strategy not in {"HTTPX", "CRAWL4AI"}:
        strategy = "HTTPX"
    return {"strategy": strategy, "proxy": proxy}


def _to_crawler_type(strategy: str) -> CrawlerType:
    return CrawlerType.CRAWL4AI if strategy == "CRAWL4AI" else CrawlerType.HTTPX


def _build_factory(proxy: str) -> CrawlerFactory:
    return CrawlerFactory(default_options=CrawlOptions(proxy=proxy))


def _crawl_and_update(crawler, u: URL) -> bool:
    try:
        doc = crawler.fetch(u.url)
        status_code = int(doc.status or 0)
        success = bool(doc.meta.get("success")) and 200 <= status_code < 400
        URL.objects.filter(pk=u.pk).update(
            status=URLStatus.CRAWLED if success else URLStatus.FAILED,
            data={"md": doc.md, "html": doc.html, "meta": doc.meta},
            updated_at=timezone.now(),
        )
        if not success:
            current_app.send_task(
                "dlq.handle",
                args=[
                    {
                        "module": "crawler",
                        "task": "crawler.url_crawler",
                        "state_id": u.state_id,
                        "url_id": u.id,
                        "url": u.url,
                        "error": doc.meta.get("error") or f"status={status_code}",
                        "meta": doc.meta,
                    }
                ],
            )
        return success
    except Exception as e:
        URL.objects.filter(pk=u.pk).update(
            status=URLStatus.FAILED,
            data={"md": "", "html": "", "meta": {"success": False, "error": str(e)}},
            updated_at=timezone.now(),
        )
        current_app.send_task(
            "dlq.handle",
            args=[
                {
                    "module": "crawler",
                    "task": "crawler.url_crawler",
                    "state_id": u.state_id,
                    "url_id": u.id,
                    "url": u.url,
                    "error": str(e),
                }
            ],
        )
        return False


# ---------------
# Batch subtasks
# ---------------
@shared_task(
    bind=True,
    name="crawler.crawl_batch",
    autoretry_for=(ObjectDoesNotExist,),
    retry_backoff=True,
    retry_jitter=True,
    acks_late=True,
)
def crawl_batch(
    self, state_id: int, url_ids: List[int], strategy: str, proxy: str
) -> Dict[str, Any]:
    factory = _build_factory(proxy)
    crawler = factory.build(kind=_to_crawler_type(strategy))

    ok, fail = 0, 0
    for url_id in url_ids:
        try:
            u = URL.objects.get(pk=url_id, state_id=state_id)
        except ObjectDoesNotExist:
            fail += 1
            continue

        # Safety: if something reset status, ensure we’re in progress
        if u.status == URLStatus.NEW:
            URL.objects.filter(pk=u.pk, status=URLStatus.NEW).update(status=URLStatus.IN_PROGRESS)

        if _crawl_and_update(crawler, u):
            ok += 1
        else:
            fail += 1

    return {"claimed": len(url_ids), "crawled": ok, "failed": fail}


# -------------------------------
# chord callback to aggregate all batch results
# -------------------------------
@shared_task(
    bind=True,
    name="crawler.finalize_batches",
)
def finalize_batches(self, batch_results: List[Dict[str, Any]], state_id: int) -> Dict[str, Any]:
    total_claimed = sum(r.get("claimed", 0) for r in batch_results)
    total_ok = sum(r.get("crawled", 0) for r in batch_results)
    total_fail = sum(r.get("failed", 0) for r in batch_results)

    state = InputState.objects.get(pk=state_id)
    more_new = URL.objects.filter(state_id=state.id, status=URLStatus.NEW).exists()

    new_status = Status.RUNNING if more_new else Status.FINISHED
    with transaction.atomic():
        InputState.objects.filter(pk=state_id, url_crawler_status=Status.RUNNING).update(
            url_crawler_status=new_status, updated_at=timezone.now()
        )

    return {
        "status": "batches_done",
        "state_id": state_id,
        "claimed": total_claimed,
        "crawled": total_ok,
        "failed": total_fail,
        "remaining_new": bool(more_new),
    }


@shared_task(
    bind=True,
    name="crawler.url_crawler",
    autoretry_for=(ObjectDoesNotExist, ValueError),
)
def url_crawler(self, state_id: int) -> Dict[str, Any]:
    # Claim state (first run protection)
    with transaction.atomic():
        claimed = InputState.objects.filter(pk=state_id, url_crawler_status__in=CLAIMABLE).update(
            url_crawler_status=Status.RUNNING, updated_at=timezone.now()
        )
    if claimed == 0:
        s = InputState.objects.get(pk=state_id)
        return {"status": "skipped", "state_id": state_id, "current": s.url_crawler_status}

    try:
        state = InputState.objects.get(pk=state_id)
        fields = _validate(state)
        strategy, proxy = fields["strategy"], fields["proxy"]

        batch_size = 25
        max_per_run = getattr(settings, "CRAWLER_MAX_URLS_PER_RUN", None)

        # Determine how many to claim for this run
        if max_per_run is None:
            # Claim everything available in this wave
            max_to_claim = 10_000  # arbitrary high cap for a single “wave”
        else:
            max_to_claim = int(max_per_run)

        # Single atomic claim of up to max_to_claim NEW URLs -> IN_PROGRESS
        to_process: List[URL] = URL.objects.claim_batch(
            filter_by={"state_id": state.id, "status": URLStatus.NEW},
            order_by=("id",),
            limit=max_to_claim,
            claim_updates={"status": URLStatus.IN_PROGRESS},
        )

        if not to_process:
            # Nothing to do; we’re finished for this state
            with transaction.atomic():
                InputState.objects.filter(pk=state_id, url_crawler_status=Status.RUNNING).update(
                    url_crawler_status=Status.FINISHED, updated_at=timezone.now()
                )
            return {
                "status": "success",
                "state_id": state_id,
                "claimed": 0,
                "crawled": 0,
                "failed": 0,
                "remaining_new": False,
            }

        # Partition into batches of up to 25
        ids = [u.id for u in to_process]
        chunks = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]

        # Launch all batch subtasks in parallel
        g = group(crawl_batch.s(state.id, chunk, strategy, proxy) for chunk in chunks)

        # Aggregate with a callback
        cb = finalize_batches.s(state_id=state_id)
        chord(g, cb).apply_async()

        return {
            "status": "launched_batches",
            "state_id": state_id,
            "batches": len(chunks),
            "claimed": len(ids),
            "batch_size": batch_size,
            "remaining_new": URL.objects.filter(state_id=state.id, status=URLStatus.NEW).exists(),
        }

    except Exception as e:
        current_app.send_task(
            "dlq.handle",
            args=[
                {
                    "module": "crawler",
                    "task": "crawler.url_crawler",
                    "state_id": state_id,
                    "error": str(e),
                }
            ],
        )
        with transaction.atomic():
            InputState.objects.filter(pk=state_id, url_crawler_status=Status.RUNNING).update(
                url_crawler_status=Status.FAILED, updated_at=timezone.now()
            )
        return {"status": "failure", "state_id": state_id, "error": "module_exception"}
