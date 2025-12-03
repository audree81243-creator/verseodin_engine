from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from core.models import URL, InputState, Status, URLStatus

from .factory import FinderFactory
from .schemas import FindOptions

logger = logging.getLogger(__name__)

CLAIMABLE = (Status.PENDING,)


def _validate(state: InputState) -> Dict[str, Any]:
    """Validate required fields on the InputState before processing."""
    fields = {
        "tld": getattr(state, "base_url", None),
    }
    if not fields["tld"]:
        raise ValueError(
            "Missing/invalid: base_url|user_instruction|keyword_generator_llm|num_keywords"
        )
    return fields


@shared_task(
    bind=True,
    name="finder.url_finder",
    autoretry_for=(ObjectDoesNotExist, ValueError),
)
def url_finder(self, state_id: int) -> Dict[str, Any]:
    """Main URL finder Celery task: discovers URLs and inserts them in bulk."""
    logger.info("starting url_finder task", extra={"extra": {"state_id": state_id}})

    with transaction.atomic():
        claimed = InputState.objects.filter(pk=state_id, url_finder_status__in=CLAIMABLE).update(
            url_finder_status=Status.RUNNING, updated_at=timezone.now()
        )

    if claimed == 0:
        s = InputState.objects.get(pk=state_id)
        logger.info(
            "skipped url_finder task (already claimed or finished)",
            extra={"extra": {"state_id": state_id, "current_status": s.url_finder_status}},
        )
        return {"status": "skipped", "state_id": state_id, "current": s.url_finder_status}

    try:
        state = InputState.objects.get(pk=state_id)
        _validate(state)

        factory = FinderFactory()
        generator = factory.build()
        options = FindOptions(
            max_depth=state.url_finder_depth,
            max_urls=state.url_finder_limit,
            proxy=state.url_finder_proxy,
        )

        logger.info(
            "generating URLs",
            extra={"extra": {"state_id": state_id, "base_url": state.base_url}},
        )
        # top_level_domain and options
        finder_response = asyncio.run(generator.find_urls(state.base_url, options))
        urls = list(finder_response.urls)
        logger.info(
            "urls discovered",
            extra={"extra": {"state_id": state_id, "url_count": len(urls)}},
        )
    except Exception as e:
        logger.exception(
            "finder stage failed",
            extra={"extra": {"state_id": state_id}},
        )
        _mark_failed(state_id)
        return {"status": "failure", "state_id": state_id, "error": str(e)}

    # bulk insertion
    try:
        with transaction.atomic():
            URL.objects.bulk_create(
                [URL(state=state, url=u, status=URLStatus.NEW) for u in urls],
                ignore_conflicts=True,  # skip duplicates safely
                batch_size=500,
            )

            InputState.objects.filter(pk=state_id, url_finder_status=Status.RUNNING).update(
                url_finder_status=Status.FINISHED, updated_at=timezone.now()
            )

        logger.info(
            "url_finder task finished successfully",
            extra={"extra": {"state_id": state_id, "inserted_count": len(urls)}},
        )
        return {"status": "success", "state_id": state_id, "count": len(urls)}

    except Exception as e:
        logger.exception(
            "bulk insert or finalize failed",
            extra={"extra": {"state_id": state_id}},
        )
        dlq_handle.delay(
            {
                "module": "finder",
                "task": "finder.url_finder",
                "state_id": state_id,
                "error": str(e),
            }
        )
        _mark_failed(state_id)
        return {"status": "failure", "state_id": state_id, "error": "module_exception"}


def _mark_failed(state_id: int) -> None:
    """Mark the InputState as FAILED safely inside a transaction."""
    with transaction.atomic():
        InputState.objects.filter(pk=state_id, url_finder_status=Status.RUNNING).update(
            url_finder_status=Status.FAILED, updated_at=timezone.now()
        )
    logger.warning(
        "state marked as FAILED",
        extra={"extra": {"state_id": state_id}},
    )


@shared_task(name="dlq.handle", queue="dlq")
def dlq_handle(payload: Dict[str, Any]) -> None:
    """Simple dead-letter queue handler for task failures."""
    logger.error("[DLQ event]", extra={"extra": payload})
