# Product Requirements Document (PRD)
## Intelligent Adaptive Trading Bot

**Version:** 1.1 - Battle-Tested Edition  
**Last Updated:** October 28, 2025  
**Status:** Updated with Production Requirements

---

## 🚨 Critical Updates (v1.1)

Based on production trading system experience, the following MANDATORY improvements have been added:

### Must-Have Before Live Trading:
1. **Server-Side Stops**: Every position must have reduce-only stop on exchange (survives bot crashes)
2. **Idempotent Orders**: All orders use `client_order_id` to prevent duplicates on retry
3. **Reconciliation Service**: Independent service verifying local state matches exchange every 10-30s
4. **PostgreSQL Database**: SQLite insufficient for concurrent writes and crash recovery
5. **NTP Time Sync**: All times in UTC, NTP configured, exchange time deltas logged
6. **Volatility Targeting**: Position sizing scaled by asset volatility (smoother returns)

### Quick Wins (Implement in Week 1):
- Add `client_order_id` to all order submissions
- Install server-side stops immediately after fills
- Configure NTP and enforce UTC timestamps
- Set up WAL mode if using SQLite (Phase 1 only)

---

## 1. Executive Summary

### 1.1 Product Vision
Build a sophisticated, profitable algorithmic trading bot that operates autonomously across crypto and stock markets, achieving consistent returns of 15-30% annually while maintaining robust risk controls suitable for solo developer operation.

### 1.2 Success Criteria
- **Performance**: Sharpe Ratio > 1.0, Maximum Drawdown < 25%
- **Reliability**: 99.5% uptime during market hours, zero catastrophic failures
- **Maintainability**: < 10 hours/week monitoring and maintenance required
- **Profitability**: Break-even within 9 months of live deployment, positive returns by month 12

### 1.3 Target User
Solo retail algorithmic trader (the developer) with:
- $1,000 initial capital (scalable to $5,000+ over 2 years)
- Python development skills
- Limited time for active monitoring (5-10 hours/week)
- Tolerance for 15-25% drawdowns

---

## 2. Product Overview

### 2.1 Core Value Proposition
**Unlike commercial trading bots (3Commas, Cryptohopper, TradeSanta):**
- Adaptive strategies that detect and respond to market regimes
- Institutional-grade risk management with multi-layered circuit breakers
- Complete control and security (no third-party API key exposure)
- Empirically validated strategies with continuous performance monitoring
- Zero subscription fees

**Unlike institutional frameworks (QuantConnect, WorldQuant):**
- Lightweight, tailored specifically to solo developer needs
- Lower infrastructure costs (~$10-20/month)
- Full customization without platform constraints
- Faster iteration cycles

### 2.2 Product Type
**Hybrid Single-Agent with Modular Strategy System**
- Monolithic core for simplicity and ease of debugging
- Modular strategy plugins for extensibility
- Emulates multi-agent benefits through well-structured software design
- Event-driven architecture for real-time responsiveness

---

## 3. Functional Requirements

### 3.1 Market Coverage
**MUST HAVE:**
- Crypto trading via centralized exchanges (Binance, Coinbase Pro)
- US stock trading via commission-free broker (Alpaca)

**SHOULD HAVE:**
- Multiple crypto exchanges for arbitrage opportunities
- Extended hours stock trading

**WON'T HAVE (V1):**
- Forex markets
- Options/derivatives
- Futures contracts
- High-frequency trading (< 1-second timeframes)

### 3.2 Trading Strategies

#### 3.2.1 Phase 1 (MVP) - Single Strategy
**Trend-Following Momentum Strategy**
- **Methodology**: Dual moving average crossover (50/200 for stocks, 1hr/6hr for crypto) with ATR-based trailing stops
- **Target Markets**: SPY (stocks), BTC/USDT (crypto)
- **Holding Period**: 3-7 days
- **Position Sizing**: 1-2% risk per trade
- **Expected Performance**: Sharpe 0.8-1.2, Max DD 15-20%, Win Rate 40-45%

#### 3.2.2 Phase 2 - Multi-Strategy
**Mean Reversion Strategy**
- **Methodology**: RSI-2 oversold/overbought with confirmation filters
- **Target Markets**: QQQ, high-volume crypto pairs
- **Holding Period**: 1-3 days
- **Expected Performance**: Sharpe 1.0-1.5, Max DD 10-15%, Win Rate 55-65%

**Funding Rate Arbitrage** (Crypto-specific)
- **Methodology**: Capture perpetual futures funding rate premiums via spot-futures pairs
- **Target Markets**: BTC, ETH perpetual futures
- **Expected Performance**: Sharpe 2.0+, Max DD < 10%, consistent 5-8% monthly

#### 3.2.3 Phase 3 - Advanced Strategies (Optional)
**Statistical Arbitrage** (Pairs Trading)
- **Methodology**: Cointegration-based pairs with z-score entry/exit
- **Target Markets**: Sector ETFs or correlated crypto pairs
- **Expected Performance**: Sharpe 1.5+, Max DD < 15%

**Adaptive Grid Trading** (Conditional)
- **Methodology**: Dynamic grid with trend detection to pause during strong trends
- **Target Markets**: Range-bound crypto pairs
- **Expected Performance**: Variable, regime-dependent

### 3.3 Risk Management (CRITICAL REQUIREMENTS)

#### 3.3.1 Position-Level Controls
- **MUST**: Per-trade risk limit of 1-2% of account equity
- **MUST**: Automatic stop-loss on every position (never override)
- **MUST**: Trailing stops for trend strategies (ATR-based)
- **MUST**: Position size calculator based on stop distance and account size

#### 3.3.2 Portfolio-Level Controls
- **MUST**: Maximum portfolio heat of 6% (sum of all position risks)
- **MUST**: Correlation checks to prevent over-concentration (limit correlated positions)
- **MUST**: Maximum leverage of 1.5x (crypto only, stocks 1x max)
- **MUST**: Single-asset exposure limit of 30% of account

#### 3.3.3 Circuit Breakers
- **MUST**: Daily loss circuit breaker (-5% account equity → halt all trading)
- **MUST**: Total drawdown circuit breaker (-15% from peak → halt all trading)
- **MUST**: Volatility circuit breaker (market volatility > 3x normal → pause new entries)
- **MUST**: Manual kill switch via dashboard and Telegram

#### 3.3.4 Failure Mode Protections
- **MUST**: Internet loss detection → cancel all open orders, close positions at market
- **MUST**: Exchange downtime detection → pause operations, attempt order cancellation
- **MUST**: Partial fill handling → reconciliation logic to prevent duplicate orders
- **MUST**: Order stuck detection → timeout and resubmit or manual alert

### 3.4 Execution Requirements

#### 3.4.0 Order Reconciliation Service (CRITICAL)
- **MUST**: Independent service continuously comparing local state vs exchange state
- **MUST**: Run every 10-30 seconds while bot active
- **MUST**: Auto-repair drift (re-install missing stops, cancel stale orders)
- **MUST**: Alert on unrecoverable discrepancies
- **MUST**: Verify all positions have server-side stops installed

**Reconciliation Checks:**
- Compare position quantity and side (local vs exchange)
- Verify all open positions have active stop orders on exchange
- Detect "ghost orders" (in local DB but not on exchange)
- Detect "orphan orders" (on exchange but not in local DB)
- Measure reconciliation lag (target < 2 seconds)

#### 3.4.1 Order Types
- **MUST**: Limit orders (primary for low slippage)
- **MUST**: Market orders (for stop-loss execution)
- **MUST**: OCO (One-Cancels-Other) or bracket orders with server-side stops
- **CRITICAL**: All stops must be reduce-only and installed on exchange/broker (survives bot crash)
- **SHOULD**: Iceberg orders (for large positions)

**Order Idempotency:**
- **MUST**: Every order submission uses deterministic `client_order_id`
- **MUST**: All retries use same `client_order_id` to prevent duplicates
- **MUST**: Echo check after submission to verify exchange has the order

#### 3.4.2 Execution Quality
- **Target latency**: < 500ms for order placement
- **Slippage budget**: < 0.1% for stocks, < 0.15% for crypto
- **Fill rate**: > 95% of intended trades executed
- **Error rate**: < 0.1% orders fail permanently

#### 3.4.3 Data Requirements
- **MUST**: Real-time price data (1-minute candles minimum)
- **MUST**: Order book depth data (crypto, for limit order placement)
- **MUST**: Account balance/position data (real-time sync)
- **SHOULD**: Historical data for backtesting (5 years stocks, 2 years crypto)

### 3.5 Monitoring & Alerting

#### 3.5.1 Real-Time Monitoring
- **MUST**: Live P&L tracking (account and per-strategy)
- **MUST**: Active position monitoring with current risk metrics
- **MUST**: System health checks (API connectivity, data freshness, execution latency)
- **MUST**: Daily summary report (automated, delivered at market close)

#### 3.5.2 Alerting Channels
- **MUST**: Telegram bot for critical alerts (circuit breaker triggered, system errors)
- **MUST**: SMS backup for critical failures (if Telegram down)
- **SHOULD**: Email for daily summaries and weekly reports

#### 3.5.3 Alert Categories
- **CRITICAL** (immediate action required): System crash, circuit breaker triggered, API key compromised
- **WARNING** (monitor closely): High slippage, repeated order failures, approaching risk limits
- **INFO** (FYI): Trade executed, daily summary, system restart

### 3.6 User Interface

#### 3.6.1 Dashboard (Web-based)
- **MUST**: Current account status (equity, positions, P&L)
- **MUST**: Strategy performance metrics (Sharpe, returns, drawdown, win rate)
- **MUST**: System controls (start/stop bot, enable/disable strategies, kill switch)
- **MUST**: Recent trade log (last 50 trades with entry/exit details)
- **SHOULD**: Performance charts (equity curve, drawdown plot, returns distribution)
- **SHOULD**: Risk metrics visualization (portfolio heat, exposure breakdown)

#### 3.6.2 Mobile Access
- **MUST**: Telegram bot interface for emergency controls
- **SHOULD**: Mobile-responsive web dashboard

### 3.7 Data Persistence & Logging

#### 3.7.1 Database Requirements
- **MUST**: PostgreSQL (not SQLite - needed for concurrent writes, transactions, crash recovery)
  - Use managed PostgreSQL (AWS RDS, Supabase free tier) for reliability
  - Alternative: SQLite with WAL mode + PRAGMA synchronous=FULL + daily verified backups (Phase 1 only)
- **MUST**: Store all trades with FSM state tracking (new → working → filled/partial → closed)
- **MUST**: Store all orders with client_order_id for idempotent retries
- **MUST**: Store daily account snapshots (equity, positions, risk metrics)
- **MUST**: Store strategy performance history (daily returns per strategy)
- **MUST**: Store position snapshots (real-time view of open positions)
- **MUST**: Store executions (individual fills, not just orders)
- **MUST**: Store risk snapshots (portfolio heat, VaR, correlations)
- **MUST**: Store config revisions with timestamps (audit trail)
- **SHOULD**: Store market data snapshots for post-trade analysis

#### 3.7.2 Logging Requirements
- **MUST**: Application logs (errors, warnings, info with timestamps)
- **MUST**: Trading decision logs (why each trade was taken or skipped)
- **MUST**: Risk management logs (circuit breaker triggers, position size calculations)
- **MUST**: Log retention of 1 year minimum

---

## 4. Non-Functional Requirements

### 4.1 Performance
- **System uptime**: 99.5% during market hours
- **Order latency**: < 500ms average, < 1000ms P99
- **Data refresh rate**: Every 1-60 seconds (strategy-dependent)
- **Dashboard load time**: < 2 seconds

### 4.2 Scalability
- **Account size**: Support $1,000 to $100,000 without architecture changes
- **Strategy count**: Support 3-5 concurrent strategies
- **Asset count**: Support 5-20 actively traded assets
- **Trade volume**: Handle up to 50 trades/day

### 4.3 Reliability
- **Zero data loss**: All trades and decisions persisted before execution
- **Graceful degradation**: Continue operating with partial service outages
- **Automatic recovery**: Self-restart after transient failures
- **Backup mechanisms**: Redundant API endpoints, failover data sources

### 4.4 Security
- **API key protection**: Encrypted storage, never logged in plaintext
- **Withdrawal protection**: API keys with trade-only permissions (no withdrawals)
- **Access control**: Dashboard requires authentication
- **Audit trail**: All manual interventions logged

### 4.5 Maintainability
- **Code documentation**: All modules documented with docstrings
- **Configuration management**: Separate config files for strategies and risk parameters
- **Modular design**: Easy to add/remove strategies without core changes
- **Testing**: Unit tests for risk management, integration tests for order flow

### 4.6 Cost Efficiency
- **Infrastructure**: $35-40/month total
  - VPS: AWS EC2 t3.small ($20/month) - Need more resources for multi-service
  - Database: AWS RDS PostgreSQL t3.micro ($15/month) or Supabase free tier
  - Redis: AWS ElastiCache t3.micro ($15/month) or self-hosted on VPS
  - Alternative: Self-host Redis on VPS to save $15/month
- **API fees**: $0 (using free tiers)
- **Trading costs**: Optimize for low-fee exchanges and maker rebates
- **Data costs**: $0 (using free market data APIs)
- **Monitoring**: CloudWatch logs ~$3/month

**Total: ~$35-40/month** (or ~$20/month if self-hosting Redis)

---

## 5. Technical Constraints

### 5.1 Platform & Tools
- **Language**: Python 3.9+ (for ecosystem and ease of maintenance)
- **Frameworks**: Freqtrade (crypto), Backtrader (backtesting), Alpaca SDK (stocks)
- **Database**: SQLite (sufficient for solo use, can migrate to PostgreSQL later)
- **Dashboard**: Streamlit (rapid development, Python-native)
- **Hosting**: AWS EC2 t3.micro or equivalent ($10/month)

### 5.2 Broker/Exchange Requirements
- **Stocks**: Alpaca (commission-free, API-first, paper trading support)
- **Crypto**: Binance or Coinbase Pro (high liquidity, reliable API, maker fee rebates)
- **Requirements**: RESTful API, WebSocket support, paper/sandbox environment

### 5.3 Regulatory Compliance
- **Pattern Day Trader (PDT)**: Avoid US stock intraday trading with < $25k account
- **Tax Reporting**: Log all trades with cost basis for tax filing
- **KYC/AML**: Use compliant exchanges only

---

## 6. User Stories

### 6.1 Core Trading Flow
**As a trader**, I want the bot to automatically identify and execute profitable trades across multiple markets, so that I earn consistent returns without active monitoring.

**Acceptance Criteria:**
- Bot scans configured markets every minute for strategy signals
- Executes trades within 500ms of signal generation
- Applies all risk management rules automatically
- Logs every decision and action for review

### 6.2 Risk Protection
**As a trader**, I want the bot to automatically stop trading if losses exceed safe limits, so that I never lose more than I can afford.

**Acceptance Criteria:**
- Daily loss of 5% triggers immediate halt
- Total drawdown of 15% triggers immediate halt
- All positions closed or protected with stops before halting
- Critical alert sent via Telegram within 10 seconds

### 6.3 Performance Monitoring
**As a trader**, I want to view real-time performance metrics and system health, so that I can make informed decisions about the bot's operation.

**Acceptance Criteria:**
- Dashboard shows current equity, positions, P&L updated every 30 seconds
- Strategy-level metrics (Sharpe, returns, drawdown) displayed
- System health indicators (API connectivity, last trade time) visible
- Access dashboard from any device with internet

### 6.4 Emergency Control
**As a trader**, I want to immediately stop the bot and close all positions if something goes wrong, so that I can prevent further losses.

**Acceptance Criteria:**
- "Kill Switch" button on dashboard stops all trading instantly
- Telegram command "/killswitch" achieves same result
- All open orders cancelled, all positions closed at market
- Confirmation of actions sent to all alert channels

### 6.5 Paper Trading Validation
**As a developer**, I want to thoroughly test strategies in paper trading mode before risking real money, so that I can validate profitability and risk controls.

**Acceptance Criteria:**
- Bot operates identically in paper and live modes (except order routing)
- Paper trades use realistic fills (market price + slippage estimate)
- All metrics and logs available in paper mode
- Minimum 6 months paper trading before live deployment

---

## 7. Success Metrics & KPIs

### 7.1 Performance Metrics (Primary)
| Metric | Target (Year 1) | Minimum Acceptable | Excellent |
|--------|-----------------|-------------------|-----------|
| Annual Return | 15-30% | > 10% | > 40% |
| Sharpe Ratio | > 1.0 | > 0.8 | > 1.5 |
| Maximum Drawdown | < 25% | < 30% | < 15% |
| Win Rate | 45-60% | > 40% | > 65% |
| Profit Factor | > 1.5 | > 1.3 | > 2.0 |

### 7.2 Operational Metrics
| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| System Uptime | 99.5% | > 99% |
| Order Fill Rate | > 95% | > 90% |
| Average Slippage | < 0.1% stocks, < 0.15% crypto | < 0.2% |
| False Alert Rate | < 5 per month | < 10 per month |
| Maintenance Time | < 10 hours/week | < 15 hours/week |

### 7.3 Risk Metrics
| Metric | Target | Hard Limit |
|--------|--------|-----------|
| Daily Loss | < 2% typically | 5% circuit breaker |
| Max Portfolio Heat | < 4% typically | 6% hard cap |
| Max Single Position | < 20% | 30% hard cap |
| Leverage Used | 1x stocks, 1-1.5x crypto | 1.5x absolute max |

### 7.4 Milestones
- **Month 3 (Paper)**: Infrastructure stable, zero execution errors for 2 weeks straight
- **Month 6 (Paper)**: Sharpe > 1.0, Max DD < 25%, ready for live
- **Month 9 (Live)**: Break-even or better on real capital
- **Month 12 (Live)**: Proven profitability, Sharpe > 0.8, scaling to larger capital

---

## 8. Assumptions & Dependencies

### 8.1 Assumptions
- Markets will have sufficient volatility and trends for momentum strategies
- Crypto funding rates will remain positive on average
- Broker APIs will maintain 99%+ uptime
- Solo developer can commit 5-10 hours/week for monitoring and iteration

### 8.2 Dependencies
- **External APIs**: Alpaca (stocks), Binance/Coinbase (crypto), CoinGecko (backup data)
- **Cloud Infrastructure**: AWS or equivalent VPS provider
- **Internet Connectivity**: Stable connection at hosting location
- **Market Access**: Continued availability of commission-free trading and crypto exchanges

### 8.3 Risks
- **Market Risk**: Strategy stops working due to regime change → *Mitigation: Adaptive learning, multiple strategies*
- **Technical Risk**: Critical bug causes losses → *Mitigation: Extensive paper trading, circuit breakers*
- **Operational Risk**: Solo developer unavailable during critical issue → *Mitigation: Automatic failsafes, kill switches*
- **Regulatory Risk**: New regulations restrict algo trading → *Mitigation: Monitor regulatory changes, ensure compliance*

---

## 9. Out of Scope (V1)

### 9.1 Explicitly Not Included
- High-frequency trading (< 1 second holding periods)
- Options, futures, or derivatives trading
- Social trading features or signal marketplace
- Mobile native app (only web + Telegram)
- Advanced ML models (deep learning, end-to-end RL)
- Multi-user or white-label deployment

### 9.2 Future Considerations (V2+)
- Advanced AI/ML integration (FreqAI for adaptive learning)
- Additional markets (Forex, commodities)
- Institutional features (FIX protocol, co-location)
- API for external strategy plugins
- Community edition for open-source release

---

## 10. Validation Plan

### 10.1 Paper Trading Validation (6 Months Minimum)
**Phase 1 (Months 1-2): Single Strategy Validation**
- Deploy trend-following strategy only
- Target: System runs without errors, executes trades correctly
- Success: 8 weeks with < 3 errors, basic profitability

**Phase 2 (Months 3-4): Multi-Strategy Validation**
- Add mean reversion and/or funding arbitrage
- Target: Strategies don't conflict, risk management scales
- Success: Sharpe > 0.8, strategies show decorrelation

**Phase 3 (Months 5-6): Stress Testing**
- Full feature set enabled
- Inject various failure scenarios (API outages, flash crashes)
- Target: All circuit breakers work, no runaway losses
- Success: System handles all edge cases gracefully

### 10.2 Live Deployment Criteria (Go/No-Go Checklist)
- [ ] Paper trading Sharpe > 1.0 over 6 months
- [ ] Maximum paper drawdown < 25%
- [ ] All circuit breakers tested and functional
- [ ] Zero critical bugs in last 4 weeks of paper trading
- [ ] Developer comfortable with system behavior and code quality
- [ ] Adequate monitoring and alerting in place
- [ ] Emergency procedures documented and tested

### 10.3 Post-Launch Monitoring
- **Daily**: Review P&L, check for errors, verify system health
- **Weekly**: Analyze strategy performance, adjust if needed
- **Monthly**: Full performance review, compare to backtest expectations
- **Quarterly**: Major strategy optimization and risk parameter tuning

---

## 11. Documentation Requirements

### 11.1 Developer Documentation
- System architecture diagram
- API integration guides (Alpaca, Binance, CCXT)
- Strategy implementation guides
- Risk management logic specification
- Database schema documentation

### 11.2 Operations Documentation
- Deployment guide (VPS setup, dependencies)
- Configuration guide (strategy parameters, API keys)
- Monitoring and alerting guide
- Troubleshooting guide (common errors and fixes)
- Emergency procedures (kill switch, manual intervention)

### 11.3 Analysis Documentation
- Backtesting methodology and results
- Paper trading performance reports
- Live trading post-mortems (monthly)
- Strategy research notes and rationale

---

## 12. Approval & Sign-Off

**Product Owner**: [Solo Developer/Trader]  
**Technical Lead**: [Solo Developer]  
**Approval Date**: [Upon review completion]

**Next Steps:**
1. Review and approve this PRD
2. Proceed to Technical Design Document
3. Begin Phase 1 MVP development

---

**Document Version History:**
- v1.0 (Oct 28, 2025): Initial PRD based on comprehensive market research
