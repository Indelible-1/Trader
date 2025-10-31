# Technical Design Document
## Intelligent Adaptive Trading Bot

**Version:** 1.1 - Battle-Tested Architecture  
**Last Updated:** October 28, 2025  
**Status:** Production-Ready Design

---

## 🎯 Architecture Improvements (v1.1)

Critical changes based on production trading system experience:

### 1. Multi-Service Architecture (Not Monolithic)
- Separate services: Data, Strategy, Risk, Execution, Reconciler, Monitor
- Each service restarts independently
- Redis Streams for durable event bus
- systemd for process management

### 2. Order Idempotency Pattern
```python
# Every order gets deterministic client_order_id
coid = make_client_order_id(strategy, symbol, side, timestamp_ns, nonce)
order = exchange.create_order(..., params={'client_order_id': coid})

# All retries use SAME ID → No duplicates
```

### 3. Server-Side Stop Orders
```python
# Reduce-only stops installed on exchange
stop = exchange.create_order(
    ...,
    params={'reduce_only': True, 'stop_price': stop_price}
)
# Survives bot crashes and internet loss
```

### 4. Reconciliation Service
- Runs every 10-30 seconds
- Verifies all positions have active stops
- Auto-repairs drift (missing stops, stale orders)
- Independent process for reliability

### 5. PostgreSQL + Redis
- PostgreSQL for concurrent writes and ACID transactions
- Redis Streams for durable event queue with replay
- Phase 1: SQLite with WAL mode (development only)

---

## 1. System Architecture Overview

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE LAYER                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  Web Dashboard   │  │  Telegram Bot    │  │  SMS Alerts      │  │
│  │   (Streamlit)    │  │   (python-telegram-bot) │  │  (Twilio)  │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │
└───────────┼────────────────────┼────────────────────┼──────────────┘
            │                    │                    │
┌───────────┼────────────────────┼────────────────────┼──────────────┐
│           │         ORCHESTRATION LAYER            │               │
│           ▼                                        ▼               │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                  Bot Core Controller                         │  │
│  │  • System State Management                                   │  │
│  │  • Event Loop Coordinator                                    │  │
│  │  • Emergency Controls (Kill Switch)                          │  │
│  └───┬──────────────┬──────────────┬────────────────┬──────────┘  │
│      │              │              │                │             │
└──────┼──────────────┼──────────────┼────────────────┼─────────────┘
       │              │              │                │
┌──────┼──────────────┼──────────────┼────────────────┼─────────────┐
│  TRADING ENGINE LAYER                               │             │
│      │              │              │                │             │
│  ┌───▼────────┐ ┌──▼──────────┐ ┌─▼─────────────┐ ┌▼──────────┐  │
│  │  Data      │ │  Strategy   │ │ Risk Manager  │ │ Execution │  │
│  │  Manager   │ │  Engine     │ │               │ │  Engine   │  │
│  └─────┬──────┘ └──────┬──────┘ └───────┬───────┘ └─────┬─────┘  │
│        │               │                │               │         │
│  ┌─────▼───────────────▼────────────────▼───────────────▼──────┐  │
│  │              Event Bus (In-Memory Queue)                     │  │
│  └───────────────────────────┬──────────────────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────────┘
                                │
┌───────────────────────────────┼─────────────────────────────────────┐
│  DATA PERSISTENCE LAYER       │                                     │
│  ┌────────────────────┐  ┌───▼──────────────┐  ┌────────────────┐  │
│  │  SQLite Database   │  │  Log Files       │  │  Config Files  │  │
│  └────────────────────┘  └──────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────┼─────────────────────────────────────┐
│  EXTERNAL SERVICES            │                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                   │
│  │  Alpaca    │  │  Binance   │  │ Coinbase   │                   │
│  │  API       │  │  API       │  │  Pro API   │                   │
│  └────────────┘  └────────────┘  └────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Key Design Principles

- **Event-Driven**: Loose coupling via event bus
- **Fail-Safe**: Default to no position on any error
- **Modular**: Easy to add/remove strategies
- **Observable**: Comprehensive logging and monitoring

---

## 2. Core Components

### 2.1 Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Core** | Python 3.9+ | Primary language |
| **Crypto Trading** | Freqtrade + CCXT | Exchange integration |
| **Stock Trading** | Alpaca SDK | Brokerage API |
| **Backtesting** | Backtrader | Strategy validation |
| **Database** | PostgreSQL 14+ | Trade/performance storage (AWS RDS or Supabase) |
| **Event Bus** | Redis Streams | Durable event queue with replay |
| **Dashboard** | FastAPI + Streamlit | API backend + web UI |
| **Alerts** | Telegram Bot API | Real-time notifications |
| **Hosting** | AWS EC2 t3.small | VPS ($20/month) + RDS ($15/month) |
| **Process Management** | systemd | Multi-service orchestration |

**Phase 1 Alternative (Development Only):**
- SQLite with WAL mode instead of PostgreSQL
- In-memory queue instead of Redis
- Must migrate to production stack by Phase 2

### 2.2 Multi-Service Architecture

**Critical Improvement: Separate Services**

Instead of monolithic bot, deploy as independent services:

```
┌─────────────────────────────────────────────────────┐
│ Data Service (datamanager.service)                 │
│ - Fetches market data                              │
│ - Publishes to Redis: market_data stream          │
│ - Independent restart without affecting others     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Strategy Service (strategy.service)                │
│ - Subscribes to market_data                        │
│ - Generates signals                                 │
│ - Publishes to Redis: signals stream              │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Risk Service (risk.service)                        │
│ - Subscribes to signals                            │
│ - Validates against all risk rules                 │
│ - Publishes to Redis: approved_signals stream     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Execution Service (execution.service)              │
│ - Subscribes to approved_signals                   │
│ - Submits orders with client_order_id             │
│ - Installs server-side OCO/bracket orders         │
│ - Publishes to Redis: order_events stream         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Reconciliation Service (reconciler.service)        │
│ - Runs continuously every 10-30 seconds           │
│ - Compares local DB vs exchange state             │
│ - Auto-repairs drift (missing stops, stale orders)│
│ - Alerts on unrecoverable discrepancies           │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Monitor Service (monitor.service)                  │
│ - Exposes health endpoints (/live, /ready)        │
│ - Collects metrics (Prometheus format)            │
│ - Sends alerts (Telegram, SMS)                    │
└─────────────────────────────────────────────────────┘
```

**Benefits:**
- Each service can restart independently
- Easier to debug and test in isolation
- Can scale individual services if needed
- Better fault isolation

### 2.3 Critical: Idempotent Order Management

**The Problem:**
Network retries can cause duplicate orders, leading to unintended positions and losses.

**The Solution:**
Every order gets a deterministic `client_order_id`. All retries use the SAME ID. Exchange deduplicates.

```python
import hashlib
import time

def make_client_order_id(
    strategy: str,
    symbol: str,
    side: str,
    timestamp_ns: int,
    nonce: int = 0
) -> str:
    """
    Generate deterministic, collision-resistant order ID.
    
    CRITICAL: Same inputs → same ID → idempotent retries
    """
    base = f"{strategy}:{symbol}:{side}:{timestamp_ns}:{nonce}"
    # Blake2b for speed, 12 bytes = 24 hex chars
    return hashlib.blake2b(base.encode(), digest_size=12).hexdigest()

class ExecutionEngine:
    def submit_order_idempotent(self, signal: Signal) -> Order:
        """
        Submit order with idempotency guarantee.
        """
        # 1. Generate deterministic client_order_id
        coid = make_client_order_id(
            strategy=signal.strategy,
            symbol=signal.symbol,
            side=signal.side,
            timestamp_ns=time.time_ns(),
            nonce=0
        )
        
        # 2. Check if we already submitted this order
        existing = self.db.get_order_by_client_id(coid)
        if existing and existing.status in ['submitted', 'filled']:
            logger.info(f"Order {coid} already submitted, skipping")
            return existing
        
        # 3. Submit to exchange
        max_retries = 3
        for attempt in range(max_retries):
            try:
                order = self.exchange.create_order(
                    symbol=signal.symbol,
                    type='limit',
                    side=signal.side,
                    amount=signal.quantity,
                    price=signal.entry_price,
                    params={
                        'client_order_id': coid,  # CRITICAL
                        'time_in_force': 'gtc'
                    }
                )
                
                # 4. Echo check - verify exchange has it
                time.sleep(0.5)
                confirmed = self.exchange.fetch_order_by_client_id(coid)
                if not confirmed:
                    raise Exception("Order echo check failed")
                
                logger.info(f"Order {coid} confirmed on exchange")
                return order
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Order submit attempt {attempt+1} failed: {e}")
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise
```

### 2.4 Critical: Server-Side Stops

**The Problem:**
If bot crashes/loses internet, client-side stop monitoring fails. Position exposed.

**The Solution:**
Every position MUST have reduce-only stop order installed on the exchange/broker.

```python
def install_server_side_stop(
    self,
    position: Position,
    stop_price: float
) -> str:
    """
    Install reduce-only stop order on exchange.
    
    CRITICAL: This order survives bot crashes and internet loss.
    """
    # Generate client_order_id for stop (linked to parent)
    stop_coid = f"{position.order_id}:stop"
    
    # Submit reduce-only stop order
    stop_order = self.exchange.create_order(
        symbol=position.symbol,
        type='stop_market',
        side='sell' if position.side == 'long' else 'buy',
        amount=position.quantity,
        price=None,  # Market order when triggered
        params={
            'client_order_id': stop_coid,
            'stop_price': stop_price,
            'reduce_only': True,  # CRITICAL - won't open new position
            'trigger': 'mark',    # Use mark price (less manipulable)
        }
    )
    
    # Verify stop is resident on exchange
    time.sleep(0.5)
    confirmed = self.exchange.fetch_order(stop_order['id'])
    assert confirmed['status'] in ['open', 'untriggered'], \
        f"Stop order not active on exchange: {confirmed}"
    
    logger.info(f"Server-side stop installed: {stop_coid} @ {stop_price}")
    return stop_order['id']

def create_bracket_order(self, signal: Signal, quantity: float):
    """
    Best practice: Submit entry + stop + take-profit as one OCO/bracket.
    
    If exchange supports it, use bracket orders so all orders are
    atomically submitted and linked.
    """
    # Alpaca example (stocks)
    order = self.alpaca.submit_order(
        symbol=signal.symbol,
        qty=quantity,
        side='buy',
        type='limit',
        limit_price=signal.entry_price,
        order_class='bracket',  # Creates OCO group
        stop_loss={'stop_price': signal.stop_loss},
        take_profit={'limit_price': signal.take_profit} if signal.take_profit else None
    )
    
    # Binance example (crypto) - must submit separately
    # 1. Submit entry limit order
    entry_order = self.binance.create_limit_buy_order(...)
    
    # 2. When filled, immediately submit reduce-only stop
    stop_order = self.install_server_side_stop(...)
```

### 2.5 Data Flow

```
1. Market Data → DataManager
2. DataManager → MarketDataEvent → EventBus
3. StrategyEngine (subscribed) → Generates Signal
4. Signal → RiskManager → Validates
5. RiskManager → ApprovedSignal → ExecutionEngine
6. ExecutionEngine → Submits Order → Exchange
7. Exchange → Order Fill → OrderFilledEvent → EventBus
8. All components → Log to Database
```

### 2.6 Reconciliation Service (CRITICAL)

**Purpose**: Continuously verify local state matches exchange state and auto-repair drift.

**Key Functions:**
```python
class ReconciliationService:
    """Runs every 10-30 seconds to verify state consistency."""
    
    def reconcile_positions(self):
        """Compare positions: local DB vs exchange."""
        # Detect ghost positions (in DB, not on exchange)
        # Detect orphan positions (on exchange, not in DB)
        # Fix quantity mismatches
    
    def verify_stop_coverage(self):
        """CRITICAL: Every position must have active stop order."""
        for position in open_positions:
            if not has_active_stop_on_exchange(position):
                logger.critical(f"Position {position.symbol} missing stop!")
                emergency_install_stop(position)
    
    def reconcile_orders(self):
        """Verify all orders in DB match exchange state."""
        # Cancel stale orders
        # Update fill status
        # Detect missing orders
```

**Metrics:**
- Reconciliation lag < 2 seconds (alert if exceeded)
- Stop coverage: 100% at all times
- Auto-repairs logged and alerted

---

## 3. Module Specifications

### 3.1 Risk Manager (CRITICAL)

**Risk Controls:**
```yaml
Position Level:
  - Per-trade risk: 1-2% of equity
  - Stop-loss: Mandatory on every position
  - Position size: Calculated from stop distance

Portfolio Level:
  - Max portfolio heat: 6% (sum of all risks)
  - Max single position: 30% of equity
  - Correlation check: Limit correlated positions

Circuit Breakers:
  - Daily loss: -5% → HALT
  - Total drawdown: -15% from peak → HALT
  - Volatility spike: > 3x normal → PAUSE entries
```

**Position Sizing Formula:**
```python
risk_amount = account_equity * 0.02  # 2% risk
stop_distance = abs(entry_price - stop_loss)
position_size = risk_amount / stop_distance

# Apply max position value limit
max_value = account_equity * 0.30
max_size = max_value / entry_price
final_size = min(position_size, max_size)
```

### 3.2 Strategy Engine

**Phase 1: Trend Following**
```python
# Moving Average Crossover
fast_ma = 50  # stocks: 50-day, crypto: 1-hour
slow_ma = 200  # stocks: 200-day, crypto: 6-hour

# Signal: fast_ma crosses above slow_ma → LONG
# Exit: fast_ma crosses below slow_ma → CLOSE
# Stop: ATR(14) * 2.0 below entry
```

**Phase 2: Mean Reversion**
```python
# RSI-2 Oversold
rsi_period = 2
oversold = 10
overbought = 90

# Signal: RSI < 10 + price > 200-day MA → LONG
# Exit: RSI > 90 OR hold 3 days → CLOSE
# Stop: 2 ATR below entry
```

**Phase 3: Funding Arbitrage**
```python
# Capture funding rate premium
threshold_rate = 0.01%  # per 8 hours (0.0365% annual)

# Signal: funding_rate > threshold → LONG spot + SHORT perp
# Exit: funding_rate < 0 OR position P&L > target → CLOSE both
```

### 3.3 Execution Engine

**Order Types:**
- **Primary**: Limit orders (0.1% better than market)
- **Stops**: Stop-market orders
- **Emergency**: Market orders (kill switch)

**Slippage Budget:**
- Stocks: < 0.1%
- Crypto: < 0.15%

**Fill Logic:**
```python
1. Submit limit order at favorable price
2. Monitor for 5 minutes
3. If not filled:
   - If high urgency (stop loss): convert to market
   - If low urgency: cancel and retry next cycle
```

---

## 4. Database Schema (PostgreSQL)

### 4.1 Why PostgreSQL

**Critical Requirements:**
- Concurrent writes from multiple services
- ACID transactions across tables  
- Better crash recovery than SQLite
- Row-level locking
- Proven at scale

**Production Setup:**
- AWS RDS PostgreSQL (t3.micro, ~$15/month)
- Or Supabase (generous free tier, managed)
- Automated backups + point-in-time recovery

**Phase 1 Alternative:**
- SQLite with WAL mode (development only)
- Must migrate to PostgreSQL by Phase 2

### 4.2 Core Tables

```sql
-- positions: Real-time open positions
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    entry_price DECIMAL(20, 8) NOT NULL,
    stop_loss DECIMAL(20, 8),
    stop_order_id TEXT,  -- Server-side stop on exchange
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- orders: All orders with client_order_id
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    client_order_id TEXT NOT NULL UNIQUE,  -- For idempotency
    exchange_order_id TEXT UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    type TEXT NOT NULL,
    quantity DECIMAL(20, 8),
    price DECIMAL(20, 8),
    status TEXT NOT NULL,  -- 'new' → 'submitted' → 'filled'
    reduce_only BOOLEAN DEFAULT false,
    submitted_at TIMESTAMP,
    filled_at TIMESTAMP
);

-- executions: Individual fills
CREATE TABLE executions (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    quantity DECIMAL(20, 8),
    price DECIMAL(20, 8),
    fee DECIMAL(20, 8),
    is_maker BOOLEAN,
    executed_at TIMESTAMP
);

-- risk_snapshots: Portfolio risk at intervals
CREATE TABLE risk_snapshots (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    portfolio_heat DECIMAL(10, 6),
    leverage DECIMAL(10, 6),
    exposure_by_asset JSONB
);
```
-- Trades: One row per position
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    strategy TEXT,
    symbol TEXT,
    side TEXT,  -- 'long' | 'short'
    entry_price REAL,
    entry_time TIMESTAMP,
    exit_price REAL,
    exit_time TIMESTAMP,
    quantity REAL,
    stop_loss REAL,
    realized_pnl REAL,
    fees REAL,
    status TEXT  -- 'open' | 'closed'
);

-- Orders: Multiple orders per trade (entry, stop, exit)
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    trade_id INTEGER,
    symbol TEXT,
    side TEXT,  -- 'buy' | 'sell'
    type TEXT,  -- 'limit' | 'market' | 'stop'
    quantity REAL,
    price REAL,
    status TEXT,  -- 'submitted' | 'filled' | 'cancelled'
    filled_at TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES trades(id)
);

-- Account snapshots (daily)
CREATE TABLE account_snapshots (
    timestamp TIMESTAMP PRIMARY KEY,
    total_equity REAL,
    daily_pnl REAL,
    sharpe_ratio REAL,
    max_drawdown REAL
);

-- Strategy performance (daily per strategy)
CREATE TABLE strategy_performance (
    strategy TEXT,
    date DATE,
    trades_count INTEGER,
    wins INTEGER,
    losses INTEGER,
    total_pnl REAL,
    PRIMARY KEY (strategy, date)
);
```

---

## 5. API Integration

### 5.1 Alpaca (Stocks)

```python
import alpaca_trade_api as tradeapi

# Paper trading
api = tradeapi.REST(
    key_id='PKxxxxxxxxxx',
    secret_key='xxxxx',
    base_url='https://paper-api.alpaca.markets'
)

# Get account
account = api.get_account()

# Submit order
order = api.submit_order(
    symbol='SPY',
    qty=10,
    side='buy',
    type='limit',
    time_in_force='gtc',
    limit_price=450.00,
    order_class='bracket',  # With stop and take-profit
    stop_loss={'stop_price': 445.00}
)
```

### 5.2 Binance (Crypto)

```python
import ccxt

exchange = ccxt.binance({
    'apiKey': 'xxxxx',
    'secret': 'xxxxx',
    'enableRateLimit': True
})

# For testnet
exchange.set_sandbox_mode(True)

# Get balance
balance = exchange.fetch_balance()

# Create order
order = exchange.create_limit_buy_order(
    symbol='BTC/USDT',
    amount=0.001,
    price=40000
)

# Fetch OHLCV
ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=100)
```

---

## 6. Configuration Management

### 6.1 Main Config (config.yaml)

```yaml
bot:
  mode: paper  # paper | live
  log_level: INFO

markets:
  stocks:
    broker: alpaca
    symbols: [SPY, QQQ]
  crypto:
    exchange: binance
    symbols: [BTC/USDT, ETH/USDT]

strategies:
  - name: trend_following
    enabled: true
    config_file: strategies/trend_following.yaml
  - name: mean_reversion
    enabled: false
    config_file: strategies/mean_reversion.yaml

risk:
  position_risk_pct: 0.02
  max_portfolio_heat: 0.06
  daily_loss_limit: 0.05
  total_drawdown_limit: 0.15
  max_single_position: 0.30

execution:
  order_type: limit
  order_timeout: 300
  slippage_pct: 0.0015

monitoring:
  telegram_bot_token: ${TELEGRAM_BOT_TOKEN}
  telegram_chat_id: ${TELEGRAM_CHAT_ID}
  alert_email: ${ALERT_EMAIL}
```

### 6.2 Strategy Config (strategies/trend_following.yaml)

```yaml
strategy:
  name: Trend Following
  type: trend_following
  description: Dual MA crossover with trailing stops

parameters:
  fast_ma: 50
  slow_ma: 200
  atr_period: 14
  atr_stop_multiplier: 2.0
  trailing_stop: true

filters:
  min_volume: 1000000  # Minimum daily volume
  max_spread_pct: 0.5  # Maximum bid-ask spread

position:
  max_positions: 2
  position_risk_pct: 0.02
  min_hold_hours: 24
```

---

## 7. Monitoring & Alerting

### 7.1 Alert Severity

**CRITICAL** (SMS + Telegram + Email):
- Circuit breaker triggered
- System crash
- API keys compromised

**WARNING** (Telegram + Email):
- Approaching risk limits (> 80%)
- High slippage detected
- API errors increasing

**INFO** (Telegram):
- Trade executed
- Daily summary
- Strategy enabled/disabled

### 7.2 Dashboard Metrics

**Real-Time:**
- Current equity
- Open positions
- Portfolio heat
- Circuit breaker status
- API connectivity

**Historical:**
- Equity curve
- Drawdown plot
- Win rate by strategy
- Monthly returns table

---

## 8. Deployment

### 8.1 VPS Setup (AWS EC2 t3.micro)

```bash
# Install dependencies
sudo apt update
sudo apt install python3.9 python3-pip python3-venv

# Create app directory
sudo mkdir -p /opt/trading-bot
sudo chown ubuntu:ubuntu /opt/trading-bot

# Setup virtual environment
cd /opt/trading-bot
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt

# Configure systemd service
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
```

### 8.2 Systemd Service

```ini
# /etc/systemd/system/trading-bot.service
[Unit]
Description=Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/trading-bot
ExecStart=/opt/trading-bot/venv/bin/python src/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## 9. Security

### 9.1 API Key Protection

- Store in `.env` file (NEVER commit)
- Set file permissions to 600
- API keys: TRADE-ONLY (disable withdrawals)
- Enable IP whitelist on exchange
- Separate keys for paper vs live

### 9.2 VPS Hardening

- SSH key authentication only
- Firewall: allow only SSH (22) and HTTPS (443)
- Non-root user for bot
- Automatic security updates
- Fail2ban for SSH protection

---

## 10. Testing Strategy

### 10.1 Unit Tests (pytest)

```python
def test_position_size_calculation():
    """Verify position sizing with 2% risk"""
    rm = RiskManager(account_equity=10000)
    signal = Signal(entry_price=400, stop_loss=396)
    
    # 2% risk = $200, $4 stop = 50 shares
    size = rm.calculate_position_size(signal)
    assert size == 50

def test_circuit_breaker_daily_loss():
    """Verify circuit breaker triggers at 5% daily loss"""
    rm = RiskManager(
        account_equity=9500,
        daily_start_equity=10000
    )
    
    approved, reason = rm.validate_signal(signal)
    assert not approved
    assert rm.circuit_breaker_active
```

### 10.2 Backtesting

```python
# Using Backtrader
import backtrader as bt

class TrendStrategy(bt.Strategy):
    params = (('fast', 50), ('slow', 200))
    
    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.params.fast)
        self.slow_ma = bt.indicators.SMA(period=self.params.slow)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        
    def next(self):
        if self.crossover > 0:  # Golden cross
            self.buy()
        elif self.crossover < 0:  # Death cross
            self.close()

# Run backtest on SPY 2019-2024
cerebro = bt.Cerebro()
data = bt.feeds.YahooFinanceData(dataname='SPY', fromdate=..., todate=...)
cerebro.adddata(data)
cerebro.addstrategy(TrendStrategy)
cerebro.run()

# Analyze results
print(f"Final Portfolio Value: {cerebro.broker.getvalue()}")
```

### 10.3 Paper Trading (6 months minimum)

**Validation Criteria:**
- Sharpe ratio > 1.0
- Max drawdown < 25%
- Total trades > 100
- System uptime > 99.5%
- Error rate < 0.1%

**Go/No-Go Decision:**
- ALL criteria met → Proceed to live with $500
- ANY missed → Continue paper, investigate

---

## 11. Performance Optimization

### 11.1 Critical Path Latency

```
Target: < 500ms from signal to order submission

1. Market data arrives: 0ms
2. Strategy calculation: < 50ms
3. Risk validation: < 50ms
4. Order creation: < 50ms
5. API submission: < 350ms
-----------------------------------
Total: < 500ms
```

**Optimization Techniques:**
- Cache technical indicators (incremental updates)
- Pre-calculate risk limits
- Async API calls
- Connection pooling

---

## 12. Failure Modes & Recovery

### 12.1 Internet Loss

**Detection:** API calls timeout (5 seconds)

**Action:**
1. Cancel all open orders
2. Close positions at market
3. Set state to ERROR
4. Log event
5. Send critical alert

### 12.2 Exchange Downtime

**Detection:** API returns 503 or connection refused

**Action:**
1. Pause all trading
2. Monitor exchange status endpoint
3. Do NOT cancel orders (they're on exchange)
4. Resume when exchange back online

### 12.3 Circuit Breaker Triggered

**Recovery Process:**
1. Developer reviews logs and positions
2. Analyze root cause
3. Fix issue (adjust parameters, patch code)
4. Manual reset required:
   ```python
   bot.risk_manager.reset_circuit_breaker()
   ```
5. Resume operations

---

## 13. Maintenance Schedule

### 13.1 Daily (< 15 min)
- Review overnight performance
- Check alerts/errors
- Verify system health

### 13.2 Weekly (< 2 hours)
- Analyze strategy performance
- Review risk metrics
- Check log files
- Backup database

### 13.3 Monthly (< 5 hours)
- Full performance review
- Strategy optimization
- Update strategy parameters
- Security updates

### 13.4 Quarterly (1-2 days)
- Major strategy review
- System audit
- Backtest on recent data
- Tax preparation

---

## 14. Development Roadmap

### Phase 1: MVP (Months 1-2)
- Single strategy (trend following)
- Basic risk management
- Paper trading on Alpaca
- Console logging
- **Goal**: Stable execution, no errors

### Phase 2: Multi-Strategy (Months 3-4)
- Add mean reversion
- Crypto integration (Binance)
- Web dashboard (Streamlit)
- Telegram alerts
- **Goal**: Multiple strategies running in parallel

### Phase 3: Advanced Features (Months 5-6)
- Funding rate arbitrage
- Adaptive learning (optional)
- Advanced analytics
- Performance optimization
- **Goal**: Ready for live deployment

### Phase 4: Live Trading (Months 7-12)
- Deploy with $500
- Monitor closely
- Scale capital gradually
- Iterate based on results
- **Goal**: Proven profitability

---

## 15. LLM-Assisted Research Architecture

Reference: `docs/LLM_Trading_Systems_Alpha_Generation_Reality_Check.md`

### 15.1 Goals & Constraints
- **Goal:** Use LLMs to accelerate research, transcript review, and sentiment factor generation with a documented 60-80% analyst time saving.
- **Constraint:** Autonomous alpha discovery is unreliable; peer-reviewed evaluations (e.g., FINSABER) show Sharpe collapse when strategies are tested over full regimes. LLM outputs must remain advisory and pass existing risk controls.
- **Guardrails:** Human-in-the-loop approvals, circuit breaker enforcement, server-side stops, and reconciliation service remain non-negotiable.

### 15.2 Data & Feature Pipeline
1. **Sources:** Earnings call transcripts (EDGAR), news (Finnhub/Alpha Vantage), social channels (Reddit/Twitter), funding rates.
2. **ETL:** Bytewax or custom asyncio ingestors push normalized documents into PostgreSQL/TimescaleDB with metadata (timestamp, source reliability).
3. **Model Stack:**
   - Base sentiment classifier: FinGPT v3.3 or Llama 3 7B with LoRA fine-tuning.
   - Optional specialized heads: volatility regime classifier, controversy detector.
4. **Inference Service:** Async FastAPI worker exposes `/score` endpoint, returns sentiment score, confidence, rationale text. Batches requests, targets <$0.05 inference cost per document.
5. **Feature Store:** Sentiment time series stored alongside price/volume factors; Redis Stream `trader.market_data.sentiment` publishes deltas for strategy consumption.

### 15.3 Multi-Agent Oversight
- **Research Agent:** Summarizes events, extracts trade hypotheses, tags confidence.
- **Skeptic Agent:** Challenges hypotheses against historical precedents and risk policy.
- **Decision Log:** Structured JSON (analysis, counterpoints, final verdict) stored for audit and surfaced in dashboard.
- **Integration:** Only hypotheses with `verdict="approved"` are emitted to strategy service via `trader.signals.llm`. Risk service applies existing checks before any order leaves the system.

### 15.4 Evaluation & Deployment
- **Benchmarking:** Maintain rolling suite of labeled datasets (FinanceBench, company-specific validation sets) to track accuracy and hallucination rates (<15% target).
- **Backtesting:** Combine sentiment factors with momentum/value filters; require out-of-sample Sharpe ≥1.2 and drawdown <20% before paper trading.
- **Paper Trading:** Minimum 3 months paper or shadow trading with full reconciliation; log incremental P&L.
- **Cost Management:** Budget envelope $2-5K setup, $500-1K monthly cloud/GPU spend. Auto-shutdown idle workloads; alert if projected monthly burn > budget.

### 15.5 Live Operations
- Manual approval toggle and kill-switch specific to LLM strategies.
- Quarterly model review, dataset refresh, and fairness checks.
- Incident response: on hallucination or drift detection, disable `llm` strategy namespace, purge pending signals, investigate root cause before re-enabling.

## 16. Success Criteria

### Technical Success:
- [ ] All unit tests passing
- [ ] System uptime > 99.5%
- [ ] Order fill rate > 95%
- [ ] Average latency < 500ms
- [ ] Zero critical bugs for 4 weeks

### Trading Success:
- [ ] Sharpe ratio > 1.0
- [ ] Max drawdown < 25%
- [ ] Win rate > 45%
- [ ] Profit factor > 1.5
- [ ] Annual return > 15%

### Operational Success:
- [ ] Maintenance < 10 hours/week
- [ ] False alerts < 5/month
- [ ] Infrastructure cost < $20/month
- [ ] Developer confidence high

---

## Appendices

### A. Tech Stack Versions

```
Python: 3.9+
Freqtrade: 2024.10+
ccxt: 4.0+
alpaca-py: 0.20+
Backtrader: 1.9+
pandas: 2.0+
numpy: 1.24+
SQLite: 3.40+
Streamlit: 1.28+
python-telegram-bot: 20.6+
```

### B. Infrastructure Costs

| Item | Provider | Monthly Cost |
|------|----------|--------------|
| VPS | AWS EC2 t3.micro | $10 |
| Monitoring | CloudWatch | $3 |
| SMS Alerts | Twilio | $5 (pay-as-go) |
| **Total** | | **~$18/month** |

### C. Useful Resources

- Freqtrade Docs: https://freqtrade.io
- Alpaca Docs: https://docs.alpaca.markets
- CCXT Docs: https://docs.ccxt.com
- Backtrader Docs: https://www.backtrader.com

---

**Document Status**: Ready for Development  
**Next Step**: Implement Phase 1 MVP based on this design
