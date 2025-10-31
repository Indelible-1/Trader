# Trader Bot Platform

This repository implements the **Intelligent Adaptive Trading Bot** described in the product and technical documentation under `docs/`. The goal is to provide a production-ready, multi-service architecture that can trade both crypto and equities while enforcing institutional-grade risk controls.

## Project Highlights
- Multi-service layout: data ingestion, strategy evaluation, risk gating, order execution, reconciliation, and monitoring are isolated processes coordinated via Redis Streams.
- Freqtrade upstream (`vendor/freqtrade`) vendored directly in the repo for backtesting, hyperopt, and FreqAI tooling referenced throughout the docs.
- PostgreSQL-first persistence layer with SQLAlchemy models supporting order, position, and account state tracking. SQLite with WAL mode is available for local development.
- Idempotent order pipeline with deterministic `client_order_id` generation and server-side stop installation for every open position.
- Reconciliation service verifying exchange reality against local state every 10–30 seconds, auto-installing missing stops, and alerting on discrepancies.
- Monitoring endpoints (FastAPI + Prometheus metrics) and Telegram-friendly alert hooks for health, circuit breakers, and risk events.

## Getting Started

1. **Create environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure services**
   - Copy `config/config.example.yaml` to `config/config.yaml`.
   - Fill out API keys, Redis/PostgreSQL URLs, and risk parameters.
   - Ensure the system clock is synchronized via NTP (`timedatectl status` should report `System clock synchronized: yes`).

3. **Run services (development)**
   In separate terminals:
   ```bash
   python scripts/run_data_service.py
   python scripts/run_strategy_service.py
   python scripts/run_risk_service.py
   python scripts/run_execution_service.py
   python scripts/run_reconciliation_service.py
   python scripts/run_monitor_service.py
   freqtrade trade --config path/to/config.json  # optional: run upstream engine in parallel
   ```

4. **Freqtrade quickstart (optional)**
   ```bash
   source .venv/bin/activate
   freqtrade create-userdir --userdir user_data
   cp vendor/freqtrade/config_examples/config_full.example.json user_data/config.json
   freqtrade show-config --config user_data/config.json
   ```
   These commands create a sandbox user directory, copy the full reference configuration, and validate it against the latest freqtrade build.

   The services communicate through Redis Streams; see `config` for stream names. All processes support `--dry-run` to exercise logic without placing live orders.

4. **Paper trade then go live**
   - Populate historical data using the data service bootstrap utilities.
   - Enable the reconciler and confirm 100% stop coverage.
   - Graduate from SQLite to PostgreSQL before connecting to live brokerage accounts.

Refer to the documentation under `docs/` for the detailed roadmap, risk specification, and architecture requirements.

## Directory Layout
- `docs/` — authoritative product, design, roadmap, risk, and critical updates documents.
- `src/trader/` — core Python package with configuration helpers, models, services, and utilities.
- `scripts/` — entrypoints for running individual services.
- `config/` — configuration templates and deployment manifests.
- `vendor/freqtrade/` — upstream freqtrade project (git-cloned) for strategy research/backtesting.

## Next Steps
- Implement secrets management suitable for your infrastructure (AWS Parameter Store, HashiCorp Vault, Doppler, etc.).
- Set up CI workflows for linting, unit tests, and integration smoke tests.
- Deploy each service with `systemd`, Docker, or Kubernetes following the roadmap schedule.

Trading is inherently risky. Backtest thoroughly, paper trade for multiple months, and never deploy without server-side stops and operational monitoring.
