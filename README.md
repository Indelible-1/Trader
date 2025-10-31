# Trader Bot Platform

This repository implements the **Intelligent Adaptive Trading Bot** described in the product, design, and risk documents under `docs/`. The goal is to deliver a production-ready, multi-service architecture capable of trading both crypto and equities while enforcing institutional-grade safeguards.

## Project Highlights
- Multi-service layout: data ingestion, strategy evaluation, risk gating, execution, reconciliation, and monitoring all run as isolated processes communicating via Redis Streams.
- Vendored Freqtrade (`vendor/freqtrade`) for deep backtesting, hyperopt, and FreqAI workflows aligned with the documentation.
- PostgreSQL-first persistence with SQLAlchemy models for orders, positions, and account state. SQLite (WAL) remains available for local development.
- Deterministic `client_order_id` pattern and mandatory server-side stops on every position.
- Reconciliation loop verifying exchange state every 10–30 seconds and auto-repairing missing stops.
- Monitoring endpoints (FastAPI + Prometheus) plus Telegram-ready alert hooks.

## Prerequisites
- Python 3.12 (or newer within the 3.x line supported by freqtrade).
- Redis 6+ (local Docker container works for development).
- PostgreSQL 15+ for production deployment (SQLite supported for local prototyping).
- NTP-synchronised host clock (`timedatectl status` should report `System clock synchronized: yes`).

## Installation
1. **Clone and enter the repository**
   ```bash
   git clone https://github.com/Indelible-1/Trader.git
   cd Trader
   ```

2. **Create and activate a virtual environment**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up local environment variables**
   ```bash
   cp .env.example .env
   # edit .env with your exchange keys, redis/postgres URLs, notification tokens, etc.
   ```
   The application automatically loads `.env` values via `python-dotenv`.

5. **Configure application settings**
   ```bash
   cp config/config.example.yaml config/config.yaml
   # customise risk settings, Redis/PostgreSQL connections, enabled strategies, etc.
   ```

## Running the Services
Each microservice can be launched from its own terminal using the shared helper script:

```bash
source .venv/bin/activate
python scripts/run_service.py data
python scripts/run_service.py strategy
python scripts/run_service.py risk
python scripts/run_service.py execution
python scripts/run_service.py reconciliation
python scripts/run_service.py monitor
```

Services read configuration from `config/config.yaml` (or the file provided via the `TRADER_CONFIG` environment variable) and share environment variables defined in `.env`. For dry-run development the default config ships with Redis enabled and database access pointing to SQLite—swap to PostgreSQL by updating `config.yaml` or the `DATABASE_URL` variable.

## Freqtrade Research Toolkit (Optional)
Freqtrade is vendored for strategy research and backtesting. Basic bootstrap:

```bash
source .venv/bin/activate
freqtrade create-userdir --userdir user_data
cp vendor/freqtrade/config_examples/config_full.example.json user_data/config.json
freqtrade show-config --config user_data/config.json
```

Use the generated `user_data` directory for backtests, hyperopt runs, and FreqAI experiments while the custom services handle live orchestration and risk enforcement.

## Directory Layout
- `docs/` — product requirements, technical design, roadmap, risk spec, and critical updates.
- `src/trader/` — application package (configuration helpers, models, services, utilities).
- `scripts/` — service launch helpers and operational tooling.
- `config/` — configuration templates.
- `vendor/freqtrade/` — full freqtrade project vendored for research workflows.

## Continuous Integration

GitHub Actions (`.github/workflows/ci.yml`) installs project requirements, compiles the `src/` tree, and runs a `freqtrade --version` smoke test on every push and pull request targeting `main`.

## Next Steps
- Integrate secrets management (AWS Parameter Store, HashiCorp Vault, Doppler, etc.) for production deployments.
- Extend the CI pipeline with linting, unit tests, integration tests, and paper-trading smoke suites.
- Containerise or provision the services with `systemd`, Docker, or Kubernetes following the roadmap timeline.

Trading remains inherently risky. Backtest thoroughly, run extended paper trading, and never operate without server-side stops and live monitoring.
