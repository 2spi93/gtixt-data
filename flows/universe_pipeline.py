from __future__ import annotations

import os
from prefect import flow, task

from gpti_bot.crawlers.crawl import crawl_firms
from gpti_bot.snapshots.snapshot import make_snapshot

@task
def crawl_batch(limit: int = 50):
    crawl_firms(limit=limit, statuses=["watchlist","candidate","eligible"], llm_on=True)
    return "ok"

@task
def snapshot_all():
    return make_snapshot(model_type="ALL")

@flow(name="gpti-universe-v0")
def universe_v0(limit: int = 50):
    crawl_batch(limit)
    return snapshot_all()

if __name__ == "__main__":
    universe_v0()
