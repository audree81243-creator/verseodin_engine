"""
Lightweight SQS worker to run the QueryUniverse pipeline.

- Polls an input SQS queue for jobs containing a "website" (and optional "job_id").
- Runs the finder -> crawler -> LLM pipeline from services.query_universe.
- Deletes the message on success and optionally publishes results to an output queue.
- Honors a work window (default 7 minutes) and stops fetching early to avoid mid-task shutdowns.
"""

import argparse
import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from decouple import config

from services.crawler.schemas import CrawlOptions
from services.finder.schemas import FindOptions
from services.llm.schemas import LLMOptions
from services.query_universe.config import PROXY_URL, DEFAULT_LLM_PROMPT_TEMPLATE, DEFAULT_MAX_URLS_TO_CRAWL
from services.query_universe.query_universe_service import QueryUniverseService
from services.query_universe.schemas import PipelineStage, QueryUniverseOptions

logger = logging.getLogger("verseodin_engine")


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VerseOdin SQS worker for QueryUniverse.")
    parser.add_argument("--work-seconds", type=int, default=420, help="Seconds to actively pull tasks (default 7m).")
    parser.add_argument("--total-seconds", type=int, default=600, help="Total lifetime before exit (default 10m).")
    parser.add_argument("--poll-seconds", type=int, default=3, help="Sleep between empty polls (default 3s).")
    parser.add_argument("--task-timeout", type=int, default=240, help="Max seconds to allow per task (default 4m).")
    parser.add_argument("--wait-time-seconds", type=int, default=2, help="SQS long-poll seconds (<=20).")
    parser.add_argument("--max-messages", type=int, default=1, help="Max messages to pull per ReceiveMessage.")
    parser.add_argument("--output-queue", type=str, default=None, help="Optional SQS queue URL to publish results.")
    return parser.parse_args()


def sqs_client():
    region = config("AWS_REGION", default=os.getenv("AWS_REGION", "us-east-1"))
    return boto3.client("sqs", region_name=region)


def receive_message(
    client,
    queue_url: str,
    max_messages: int,
    wait_time_seconds: int,
    visibility_timeout: int,
) -> Optional[Dict[str, Any]]:
    try:
        resp = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_time_seconds,
            VisibilityTimeout=visibility_timeout,
        )
        messages = resp.get("Messages", [])
        return messages[0] if messages else None
    except (BotoCoreError, ClientError) as e:
        logger.error(f"Error receiving message: {e}")
        return None


def delete_message(client, queue_url: str, receipt_handle: str) -> None:
    try:
        client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
    except (BotoCoreError, ClientError) as e:
        logger.error(f"Error deleting message: {e}")


def send_result(client, queue_url: str, payload: Dict[str, Any]) -> None:
    try:
        client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
    except (BotoCoreError, ClientError) as e:
        logger.error(f"Error sending result message: {e}")


def parse_body(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    body = message.get("Body")
    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        logger.error(f"Message body is not valid JSON: {body!r}")
        return None


def build_options() -> QueryUniverseOptions:
    # Defaults aligned with run_full_pipeline.py but driven by env when available.
    gemini_key = os.getenv("GEMINI_API_KEY") or config("GEMINI_API_KEY", default=None)
    llm_model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    return QueryUniverseOptions(
        find_options=FindOptions(
            max_depth=6,
            max_urls=1000,
            proxy=PROXY_URL,
        ),
        crawl_options=CrawlOptions(
            proxy=PROXY_URL,
            timeout_ms=30_000,
        ),
        llm_options=LLMOptions(
            model=llm_model,
            api_key=gemini_key,
        ),
        max_urls_to_crawl=DEFAULT_MAX_URLS_TO_CRAWL,
        enable_llm_processing=True,
        llm_prompt_template=DEFAULT_LLM_PROMPT_TEMPLATE,
        run_until_stage=PipelineStage.LLM,
    )


async def process_task(website: str, options: QueryUniverseOptions) -> Dict[str, Any]:
    service = QueryUniverseService()
    result = await service.process(website, options=options)
    return {
        "website": website,
        "prompts": result.query_universe_prompts,
        "llm_responses": [getattr(r, "raw", str(r)) for r in result.llm_responses],
        "totals": {
            "found": result.total_urls_found,
            "crawled": result.total_urls_crawled,
            "llm_calls": result.total_llm_calls,
            "processing_seconds": result.processing_time,
        },
        "completed_stage": result.completed_stage,
    }


def main():
    args = build_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    queue_url = config("SQS_QUEUE_URL", default=os.getenv("SQS_QUEUE_URL"))
    if not queue_url:
        raise RuntimeError("SQS_QUEUE_URL is required")

    output_queue = args.output_queue or os.getenv("OUTPUT_SQS_QUEUE_URL")

    client = sqs_client()
    opts = build_options()

    start = time.monotonic()
    work_deadline = start + args.work_seconds
    hard_deadline = start + args.total_seconds
    visibility_timeout = max(args.task_timeout + 60, 60)

    logger.info(
        "verseodin_engine started",
        extra={
            "extra": {
                "work_seconds": args.work_seconds,
                "total_seconds": args.total_seconds,
                "poll_seconds": args.poll_seconds,
                "wait_time_seconds": args.wait_time_seconds,
                "visibility_timeout": visibility_timeout,
            }
        },
    )

    processed = 0
    while True:
        now = time.monotonic()
        if now >= work_deadline:
            logger.info("Work window elapsed; entering idle period.")
            break
        if now >= hard_deadline:
            logger.info("Hard deadline reached; exiting.")
            return

        time_left_for_task = work_deadline - now
        if time_left_for_task < args.task_timeout:
            logger.info(
                f"Skipping fetch; only {time_left_for_task:.1f}s left which is below task timeout {args.task_timeout}s."
            )
            break

        msg = receive_message(
            client,
            queue_url=queue_url,
            max_messages=args.max_messages,
            wait_time_seconds=args.wait_time_seconds,
            visibility_timeout=visibility_timeout,
        )
        if not msg:
            time.sleep(args.poll_seconds)
            continue

        body = parse_body(msg)
        if not body:
            delete_message(client, queue_url, msg["ReceiptHandle"])
            continue

        website = body.get("website")
        job_id = body.get("job_id") or msg.get("MessageId")
        if not website:
            logger.warning(f"Message missing 'website', dropping. job_id={job_id}")
            delete_message(client, queue_url, msg["ReceiptHandle"])
            continue

        logger.info(f"Processing job_id={job_id} website={website}")
        try:
            payload = asyncio.run(process_task(website, opts))
            payload["job_id"] = job_id
            payload["source_queue"] = queue_url
            for k in ("user_id", "user_email", "user_name"):
                if k in body:
                    payload[k] = body[k]
            processed += 1
            llm_responses = payload.get("llm_responses") or []
            if llm_responses:
                preview = str(llm_responses[0])
                logger.info(
                    f"job_id={job_id} llm_response_preview={preview[:10000]}"
                )
            logger.info(
                f"Completed job_id={job_id} website={website} totals={payload.get('totals')}"
            )
            if output_queue:
                send_result(client, output_queue, payload)
            else:
                print(json.dumps(payload))
            delete_message(client, queue_url, msg["ReceiptHandle"])
        except Exception as e:
            logger.error(f"Error processing job_id={job_id}: {e}")
            # Leave message invisible until visibility timeout expires; it will be retried.

    # Idle phase to ensure we don't pick new work near shutdown
    remaining = hard_deadline - time.monotonic()
    if remaining > 0:
        logger.info(f"Idling for {remaining:.1f}s before exit (no new work).")
        time.sleep(remaining)

    logger.info(f"verseodin_engine exiting after processing {processed} task(s).")


if __name__ == "__main__":
    main()
