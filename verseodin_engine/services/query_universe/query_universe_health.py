import os
from typing import List

import psycopg
from decouple import config
from fastapi import FastAPI
from fastapi.responses import JSONResponse

DB_URL = config("DATABASE_URL", default=os.getenv("DATABASE_URL"))

app = FastAPI(title="Query Universe Worker Health")


def get_conn():
  if not DB_URL:
    raise RuntimeError("DATABASE_URL not set")
  return psycopg.connect(DB_URL, autocommit=True)


@app.get("/health")
def health():
  try:
    with get_conn() as conn:
      with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
    return {"status": "ok"}
  except Exception as e:
    return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/jobs")
def list_jobs():
  try:
    with get_conn() as conn:
      with conn.cursor() as cur:
        cur.execute(
      """
          SELECT id, status, universe_name, website, user_name, email, created_at, started_at, finished_at
          FROM query_universe
          ORDER BY created_at DESC
          LIMIT 20
          """
        )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        jobs: List[dict] = [dict(zip(cols, r)) for r in rows]
    return {"jobs": jobs}
  except Exception as e:
    return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


if __name__ == "__main__":
  import uvicorn

  uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
