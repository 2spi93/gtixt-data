# GPTI — gpti-data-bot (Production Data Pipeline)

This repo is the **data backbone** of GTIXT:
- Discover prop firms (CFD/FX + Futures), separated by `model_type`
- Crawl official pages (pricing, rules, payouts, ToS)
- Extract fields into the **Universe v0 data dictionary**
- Score firms using 8 specialized agents (RVI, REM, FRP, IRS, IIP, SSS, SS, MIS)
- Validate data quality with Oversight Gate
- Store **evidence** (URL + timestamp + hash + excerpt)
- Produce **versioned snapshots** (`universe_YYYY-MM-DD.json` + CSV + hash)
- Publish to MinIO for frontend consumption

**Architecture & Roles**: See [docs/BOT_ARCHITECTURE.md](docs/BOT_ARCHITECTURE.md) for complete system design, agent specifications, and separation of concerns with the frontend.

**Frontend Separation**: This bot produces production data only. The frontend (gpti-site) displays data but never implements scoring logic. For development, the frontend uses a separate test data generator documented in `/opt/gpti/gpti-site/docs/TEST_DATA_GENERATOR.md`.

## MVP stack
- Docker Compose stack: Postgres + MinIO + Prefect Server + Prefect Worker + Bot container
- SQL schema (Universe / datapoints / evidence / snapshots)
- Prefect flows skeleton (daily monitor / weekly refresh / monthly snapshot)
- Minimal bot CLI (`python -m gpti_data ...`) with placeholders for site-specific extractors

## Quick start (VPS)
1. Install Docker Engine + Compose plugin (official docs).
2. Copy `.env.example` → `.env` and set secrets.
3. Run:
   ```bash
   cd infra
   docker compose up -d
   ```
4. Prefect UI: `http://YOUR_SERVER_IP:4200`
5. MinIO Console: `http://YOUR_SERVER_IP:9001`

## Outputs
- MinIO bucket: `gpti-raw` for raw HTML
- MinIO bucket: `gpti-snapshots` for versioned snapshots
- Postgres tables hold normalized points + evidence pointers
