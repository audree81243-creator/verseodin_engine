import asyncio
import json
import os
import time
from typing import Optional

import boto3
import psycopg  # Requires psycopg/psycopg2 installed
from decouple import config

from services.query_universe.query_universe_service import QueryUniverseService
from services.query_universe.schemas import QueryUniverseOptions, PipelineStage
from services.finder.schemas import FindOptions
from services.crawler.schemas import CrawlOptions
from services.llm.schemas import LLMOptions


DB_URL = config("DATABASE_URL", default=os.getenv("DATABASE_URL"))
SQS_QUEUE_URL = config("SQS_QUEUE_URL", default=os.getenv("SQS_QUEUE_URL"))
AWS_REGION = config("AWS_REGION", default=os.getenv("AWS_REGION", "us-east-1"))

# LLM defaults
DEFAULT_LLM_MODEL = config("LLM_MODEL", default="gemini-2.5-flash")


def get_db_conn():
  if not DB_URL:
    raise RuntimeError("DATABASE_URL not set")
  return psycopg.connect(DB_URL, autocommit=True)


def sqs_client():
  return boto3.client("sqs", region_name=AWS_REGION)


def fetch_job(conn, job_id: str) -> Optional[dict]:
  with conn.cursor() as cur:
    cur.execute(
      """
      SELECT id, status, user_id, user_name, email, universe_name, website, result_json, final_universe
      FROM query_universe
      WHERE id = %s
      """,
      (job_id,),
    )
    row = cur.fetchone()
    if not row:
      return None
    keys = [desc[0] for desc in cur.description]
    return dict(zip(keys, row))


def mark_running(conn, job_id: str) -> bool:
  with conn.cursor() as cur:
    cur.execute(
      """
      UPDATE query_universe
      SET status = 'running', started_at = now()
      WHERE id = %s AND status = 'queued'
      """,
      (job_id,),
    )
    return cur.rowcount == 1


def mark_finished(conn, job_id: str, status: str, result_json=None, error_text: Optional[str] = None):
  with conn.cursor() as cur:
    cur.execute(
      """
      UPDATE query_universe
      SET status = %s,
          result_json = %s,
          error_text = %s,
          finished_at = now()
      WHERE id = %s
      """,
      (status, json.dumps(result_json) if result_json is not None else None, error_text, job_id),
    )


def process_job(conn, job_id: str, job_type: str, website: str):
  if not mark_running(conn, job_id):
    print(f"[query-universe-worker] job {job_id} not in queued state; skipping")
    return

  job = fetch_job(conn, job_id)
  if not job:
    print(f"[query-universe-worker] job {job_id} not found after mark_running")
    return

  try:
    service = QueryUniverseService()
    options = QueryUniverseOptions(
      find_options=FindOptions(),
      crawl_options=CrawlOptions(),
      llm_options=LLMOptions(model=DEFAULT_LLM_MODEL),
      max_urls_to_crawl=20,
      enable_llm_processing=True,
      run_until_stage=PipelineStage.LLM,
    )
    # service.process is async; run it in a fresh event loop for each job
    result = asyncio.run(service.process(website, options=options))
    payload = {
      "meta": {
        "website": website,
        "universe_name": job.get("universe_name"),
        "user_name": job.get("user_name"),
        "email": job.get("email"),
      },
      "prompts": result.query_universe_prompts,
      "llm_responses": [getattr(r, "raw", str(r)) for r in result.llm_responses],
      "totals": {
        "found": result.total_urls_found,
        "crawled": result.total_urls_crawled,
        "llm_calls": result.total_llm_calls,
      },
    }
    mark_finished(conn, job_id, "succeeded", payload, None)
    print(f"[query-universe-worker] job {job_id} succeeded")
  except Exception as e:
    mark_finished(conn, job_id, "failed", None, str(e))
    print(f"[query-universe-worker] job {job_id} failed: {e}")


def main_loop():
  if not SQS_QUEUE_URL:
    raise RuntimeError("SQS_QUEUE_URL not set")

  conn = get_db_conn()
  sqs = sqs_client()

  while True:
    resp = sqs.receive_message(
      QueueUrl=SQS_QUEUE_URL,
      MaxNumberOfMessages=1,
      WaitTimeSeconds=10,
      VisibilityTimeout=300,
    )
    messages = resp.get("Messages", [])
    if not messages:
      time.sleep(1)
      continue

    for msg in messages:
      receipt = msg["ReceiptHandle"]
      try:
        body = json.loads(msg.get("Body", "{}"))
        job_id = body.get("job_id")
        job_type = body.get("job_type", "universe")
        website = body.get("website")
        if not job_id or not website:
          print(f"[query-universe-worker] invalid message body: {body}")
          sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt)
          continue
        process_job(conn, job_id, job_type, website)
        sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt)
      except Exception as e:
        print(f"[query-universe-worker] error processing message: {e}")
        # leave the message for visibility timeout; will be retried
        continue


if __name__ == "__main__":
  main_loop()
