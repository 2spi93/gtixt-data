# RUNBOOK — GPTI Data Bot

## Prefect schedules
Create schedules via Prefect UI or via `prefect.yaml` / `flow.serve`.

Suggested (UTC):
- daily monitor: 03:00
- weekly refresh: Sun 04:00
- monthly snapshot: 1st day 05:00

## MinIO
Default ports:
- API: 9000
- Console: 9001

Create buckets:
- gpti-raw
- gpti-snapshots

## Postgres
Container requires `POSTGRES_PASSWORD` (others optional).
