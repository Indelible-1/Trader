# Risk Management Specification
## Intelligent Adaptive Trading Bot

**Version:** 1.0  
**Last Updated:** October 28, 2025  
**Status:** Implementation Reference

---

## 1. Overview

This document specifies all risk management rules, circuit breakers, position sizing formulas, and failure mode handling for the trading bot. **These rules are MANDATORY and must never be overridden** except through careful manual intervention with full understanding of consequences.

**Guiding Philosophy:**  
*"Survive first, profit second. It's better to miss opportunities than to risk catastrophic losses."*

---

## 2. Position-Level Risk Controls

### 2.1 Position Sizing Formula

**Primary Formula with Volatility Targeting:**

Volatility targeting produces smoother returns by scaling position size inversely to asset volatility.

```python
def calculate_position_size_vol_targeted(
    account_equity: float,
    entry_price: float,
    stop_loss: float,
    target_portfolio_vol: float = 0.10,  # 10% annualized
    asset_vol: float = None,  # Annualized volatility of asset
    position_risk_pct: float = 0.02  # 2% fallback if no vol data
) -> float:
    """
    Calculate position size with volatility targeting.
    
    Two-stage approach:
    1. Vol-targeting: Scale by target_vol / asset_vol
    2. Risk limit: Cap at fixed risk percentage
    
    Args:
        account_equity: Current account balance
        entry_price: Intended entry price
        stop_loss: Stop loss price
        target_portfolio_vol: Target annualized volatility (0.10 = 10%)
        asset_vol: Asset's annualized volatility (from EWMA or rolling std)
        position_risk_pct: Maximum risk per trade (0.02 = 2%)
    
    Returns:
        Position size in base currency units
    
    Example:
        equity = $10,000
        target_vol = 10% annually
        asset_vol = 50% annually (volatile crypto)
        
        # Vol-targeted gross position
        gross = 10000 * (0.10 / 0.50) = $2,000
        
        # Convert to shares based on stop distance
        stop_distance = abs(entry - stop) = $4
        position_size = 2000 / 4 = 500 units
        
        # Then apply risk cap (2% = $200 risk max)
        # If 500 units * $4 stop = $2000 risk (exceeds cap)
        # Cap at: 200 / 4 = 50 units
    """
    
    # Method 1: Volatility targeting (if vol data available)
    if asset_vol and asset_vol > 1e-8:
        # Scale position inversely to volatility
        vol_scalar = target_portfolio_vol / asset_vol
        gross_target_value = account_equity * vol_scalar
        
        # Convert to position size
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance == 0:
            raise ValueError("Stop loss cannot equal entry price")
        
        vol_targeted_size = gross_target_value / entry_price
        
    else:
        # Fallback: use traditional fixed-risk sizing
        vol_targeted_size = float('inf')  # No vol-based cap
    
    # Method 2: Fixed risk percentage (risk cap)
    risk_amount = account_equity * position_risk_pct
    stop_distance = abs(entry_price - stop_loss)
    risk_capped_size = risk_amount / stop_distance
    
    # Use the MORE CONSERVATIVE of the two methods
    position_size = min(vol_targeted_size, risk_capped_size)
    
    return position_size

def calculate_asset_volatility(prices: pd.Series, halflife_days: int = 30) -> float:
    """
    Calculate annualized volatility using EWMA.
    
    EWMA (Exponentially Weighted Moving Average) gives more weight
    to recent volatility, adapting faster to regime changes.
    
    Args:
        prices: Series of daily closing prices
        halflife_days: Halflife for exponential decay (30 days typical)
    
    Returns:
        Annualized volatility as decimal (0.50 = 50%)
    """
    # Calculate daily returns
    returns = prices.pct_change().dropna()
    
    # EWMA of squared returns
    ewma_var = returns.pow(2).ewm(halflife=halflife_days).mean().iloc[-1]
    
    # Annualize (sqrt for variance → std, multiply by sqrt(252) for daily → annual)
    annual_vol = np.sqrt(ewma_var * 252)
    
    return annual_vol
```

**When to Use Volatility Targeting:**
- ✅ Multi-asset portfolios (different assets have different vols)
- ✅ Assets with regime changes (crypto especially)
- ✅ When seeking consistent Sharpe ratio across markets
- ❌ Single-asset trading (less beneficial)
- ❌ When vol data unreliable or insufficient history

**Implementation Priority: HIGH**
This single addition can improve risk-adjusted returns by 20-40% by preventing over-sizing in calm markets → crash scenarios.

---

### 2.1 (Legacy) Fixed Risk Position Sizing

**For reference - use vol-targeting above in production:**

```python
def calculate_position_size(
    account_equity: float,
    entry_price: float,
    stop_loss: float,
    position_risk_pct: float = 0.02  # 2%
) -> float:
    """
    Calculate position size based on fixed risk per trade.
    
    Args:
        account_equity: Current account balance in USD
        entry_price: Intended entry price
        stop_loss: Stop loss price
        position_risk_pct: Percentage of equity to risk (0.02 = 2%)
    
    Returns:
        Position size in base currency units
    
    Example:
        equity = $10,000
        entry = $400
        stop = $396
        risk_pct = 0.02
        
        risk_amount = 10000 * 0.02 = $200
        stop_distance = 400 - 396 = $4
        position_size = 200 / 4 = 50 shares
    """
    risk_amount = account_equity * position_risk_pct
    stop_distance = abs(entry_price - stop_loss)
    
    if stop_distance == 0:
        raise ValueError("Stop loss cannot equal entry price")
    
    position_size = risk_amount / stop_distance
    
    return position_size
```

**Maximum Position Value Limit:**
```python
def apply_max_position_limit(
    position_size: float,
    entry_price: float,
    account_equity: float,
    max_position_pct: float = 0.30  # 30%
) -> float:
    """
    Cap position size at maximum percentage of account.
    
    This prevents any single position from dominating the portfolio,
    even if the stop loss is very tight.
    """
    max_position_value = account_equity * max_position_pct
    max_size = max_position_value / entry_price
    
    return min(position_size, max_size)
```

**Combined Position Sizing:**
```python
def final_position_size(
    account_equity: float,
    entry_price: float,
    stop_loss: float,
    position_risk_pct: float = 0.02,
    max_position_pct: float = 0.30
) -> float:
    """
    Calculate final position size applying both risk and value limits.
    """
    # Calculate based on risk
    size = calculate_position_size(
        account_equity, entry_price, stop_loss, position_risk_pct
    )
    
    # Apply max position value limit
    size = apply_max_position_limit(
        size, entry_price, account_equity, max_position_pct
    )
    
    # Round to appropriate precision
    if entry_price < 1:  # Crypto typically
        size = round(size, 6)
    else:  # Stocks typically
        size = int(size)  # Whole shares only
    
    return size
```

### 2.2 Stop Loss Requirements

**CRITICAL RULE: Every position MUST have a REDUCE-ONLY stop order installed ON THE EXCHANGE/BROKER. No exceptions.**

**Why Server-Side Stops Are Mandatory:**
- Bot crashes/loses internet → Client-side monitoring fails → Position exposed
- Exchange stops survive all local failures
- Reduce-only stops can't accidentally open new positions

**Stop Loss Types:**

1. **Server-Side Stop Loss** (MANDATORY - Primary Protection)
   ```python
   def install_server_side_stop(
       exchange,
       position: Position,
       stop_price: float
   ) -> str:
       """
       Install reduce-only stop order on exchange.
       
       CRITICAL: This order lives on the exchange, survives bot crashes.
       """
       stop_order = exchange.create_order(
           symbol=position.symbol,
           type='stop_market',
           side='sell' if position.side == 'long' else 'buy',
           amount=position.quantity,
           params={
               'stop_price': stop_price,
               'reduce_only': True,  # CRITICAL - won't flip position
               'trigger': 'mark',     # Use mark price (less manipulable)
               'client_order_id': f"{position.id}:stop"
           }
       )
       
       # VERIFY stop is on exchange
       time.sleep(0.5)
       confirmed = exchange.fetch_order(stop_order['id'])
       if confirmed['status'] not in ['open', 'untriggered']:
           raise Exception(f"Stop order not active on exchange: {confirmed}")
       
       return stop_order['id']
   ```

2. **Trailing Stop Loss** (Trend following, after server-side stop installed)
   ```python
   stop_loss = entry_price - (atr * multiplier)
   # Example: entry=$400, ATR=$5, multiplier=2.0
   # stop_loss = 400 - (5 * 2) = $390
   ```

2. **Trailing Stop Loss** (Trend following)
   ```python
   def update_trailing_stop(
       current_price: float,
       current_stop: float,
       entry_price: float,
       atr: float,
       multiplier: float = 2.0
   ) -> float:
       """
       Update trailing stop to lock in profits.
       Stop only moves up, never down.
       """
       new_stop = current_price - (atr * multiplier)
       
       # Stop can only move up (for long positions)
       if new_stop > current_stop:
           return new_stop
       else:
           return current_stop
   ```

3. **Time-Based Stop** (Mean reversion)
   ```python
   # If position held > max_hold_days, close at market
   if (current_time - entry_time).days > max_hold_days:
       close_position_at_market()
   ```

**Stop Loss Placement Rules:**
- **Minimum distance**: Stop must be at least 1 ATR away (prevents whipsaws)
- **Maximum distance**: Stop must be within 5 ATR (prevents huge losses)
- **Stock-specific**: Respect support/resistance levels if using technical stops
- **Crypto-specific**: Account for higher volatility (wider stops may be needed)

### 2.3 Position Monitoring

**Continuous Checks** (every minute while position open):
```python
def monitor_position(position: Position) -> List[Action]:
    """
    Check position against all exit conditions.
    Returns list of actions to take (empty if none).
    """
    actions = []
    
    # 1. Check stop loss
    if position.current_price <= position.stop_loss:
        actions.append(Action.CLOSE_AT_MARKET)
        log_exit_reason("Stop loss hit", position)
    
    # 2. Check take profit (if set)
    if position.take_profit and position.current_price >= position.take_profit:
        actions.append(Action.CLOSE_AT_LIMIT)
        log_exit_reason("Take profit reached", position)
    
    # 3. Check time-based exit
    if should_exit_on_time(position):
        actions.append(Action.CLOSE_AT_MARKET)
        log_exit_reason("Max hold time exceeded", position)
    
    # 4. Check strategy exit signal
    if position.strategy.check_exit_signal(position):
        actions.append(Action.CLOSE_PER_STRATEGY)
        log_exit_reason("Strategy exit signal", position)
    
    # 5. Update trailing stop
    if position.trailing_stop_enabled:
        new_stop = update_trailing_stop(position)
        if new_stop != position.stop_loss:
            position.stop_loss = new_stop
            log_info(f"Trailing stop updated to {new_stop}")
    
    return actions
```

---

## 3. Portfolio-Level Risk Controls

### 3.1 Portfolio Heat (Total Risk Exposure)

**Definition:** Sum of risk across all open positions

**Calculation:**
```python
def calculate_portfolio_heat(positions: List[Position]) -> float:
    """
    Calculate total portfolio risk as percentage of equity.
    
    Returns: Portfolio heat as decimal (0.06 = 6%)
    """
    total_risk = 0.0
    
    for position in positions:
        position_risk = abs(position.entry_price - position.stop_loss) * position.quantity
        total_risk += position_risk
    
    portfolio_heat = total_risk / account_equity
    
    return portfolio_heat
```

**Enforcement:**
```python
def validate_new_position_heat(
    signal: Signal,
    position_size: float,
    existing_positions: List[Position],
    max_heat: float = 0.06  # 6%
) -> Tuple[bool, str]:
    """
    Check if adding new position would exceed heat limit.
    """
    # Calculate risk of new position
    new_position_risk = abs(signal.entry_price - signal.stop_loss) * position_size
    
    # Calculate current heat
    current_heat = calculate_portfolio_heat(existing_positions)
    
    # Calculate new heat
    new_heat = current_heat + (new_position_risk / account_equity)
    
    if new_heat > max_heat:
        return False, f"Portfolio heat would be {new_heat:.1%}, max is {max_heat:.1%}"
    
    return True, "Approved"
```

**Rules:**
- **Maximum portfolio heat: 6%** (absolute cap)
- **Typical portfolio heat: 3-4%** (target in normal conditions)
- **High volatility adjustment:** Reduce max heat to 4% if market volatility > 2x normal

### 3.2 Position Count Limits

```python
# Global limits
MAX_TOTAL_POSITIONS = 10
MAX_POSITIONS_PER_STRATEGY = 3
MAX_POSITIONS_PER_MARKET = 5  # e.g., max 5 crypto positions

# Check before opening new position
def validate_position_count(
    strategy_name: str,
    market: str,
    current_positions: List[Position]
) -> Tuple[bool, str]:
    """Ensure we don't have too many positions."""
    
    total_positions = len(current_positions)
    strategy_positions = len([p for p in current_positions 
                              if p.strategy == strategy_name])
    market_positions = len([p for p in current_positions 
                           if p.market == market])
    
    if total_positions >= MAX_TOTAL_POSITIONS:
        return False, f"Max total positions ({MAX_TOTAL_POSITIONS}) reached"
    
    if strategy_positions >= MAX_POSITIONS_PER_STRATEGY:
        return False, f"Max positions for {strategy_name} reached"
    
    if market_positions >= MAX_POSITIONS_PER_MARKET:
        return False, f"Max positions in {market} reached"
    
    return True, "Approved"
```

### 3.3 Correlation Risk Management

**Purpose:** Prevent over-concentration in correlated assets (e.g., holding both SPY and QQQ)

**Correlation Check:**
```python
import numpy as np

def calculate_correlation(symbol1: str, symbol2: str, lookback_days: int = 30) -> float:
    """
    Calculate rolling correlation between two assets.
    
    Returns: Correlation coefficient (-1 to 1)
    """
    # Fetch recent price history
    prices1 = get_price_history(symbol1, lookback_days)
    prices2 = get_price_history(symbol2, lookback_days)
    
    # Calculate returns
    returns1 = prices1.pct_change().dropna()
    returns2 = prices2.pct_change().dropna()
    
    # Calculate correlation
    correlation = returns1.corr(returns2)
    
    return correlation

def check_correlation_risk(
    new_symbol: str,
    existing_positions: List[Position],
    correlation_threshold: float = 0.7
) -> Tuple[bool, str]:
    """
    Check if new position is too correlated with existing positions.
    """
    for position in existing_positions:
        corr = calculate_correlation(new_symbol, position.symbol)
        
        if abs(corr) > correlation_threshold:
            return False, f"High correlation ({corr:.2f}) with existing position in {position.symbol}"
    
    return True, "No significant correlation detected"
```

**Rules:**
- **Max 2 positions** with correlation > 0.7
- **Special handling** for sector ETFs (SPY, QQQ, IWM) - treat as highly correlated
- **Crypto pairs:** BTC and ETH considered correlated for this purpose

### 3.4 Leverage Limits

```python
# Strict leverage rules
MAX_LEVERAGE_STOCKS = 1.0  # No leverage on stocks (cash account)
MAX_LEVERAGE_CRYPTO = 1.5  # Max 1.5x on crypto

def calculate_current_leverage(positions: List[Position]) -> float:
    """
    Calculate current leverage ratio.
    
    Leverage = Total Position Value / Account Equity
    
    Example:
        Equity: $10,000
        Position 1: $8,000
        Position 2: $5,000
        Total: $13,000
        Leverage: 13000 / 10000 = 1.3x
    """
    total_position_value = sum(p.quantity * p.current_price 
                               for p in positions)
    
    leverage = total_position_value / account_equity
    
    return leverage

def validate_leverage(
    new_position_value: float,
    market: str,
    current_positions: List[Position]
) -> Tuple[bool, str]:
    """
    Ensure adding new position doesn't exceed leverage limits.
    """
    current_leverage = calculate_current_leverage(current_positions)
    new_leverage = current_leverage + (new_position_value / account_equity)
    
    max_leverage = MAX_LEVERAGE_STOCKS if market == 'stocks' else MAX_LEVERAGE_CRYPTO
    
    if new_leverage > max_leverage:
        return False, f"Leverage would be {new_leverage:.2f}x, max is {max_leverage:.2f}x"
    
    return True, "Leverage within limits"
```

---

## 4. Circuit Breakers

### 4.1 Daily Loss Circuit Breaker

**Trigger:** Daily loss exceeds 5% of starting equity

```python
class DailyLossCircuitBreaker:
    def __init__(self, limit_pct: float = 0.05):
        self.limit_pct = limit_pct
        self.daily_start_equity = None
        self.triggered = False
        
    def check(self, current_equity: float) -> Tuple[bool, str]:
        """
        Check if daily loss exceeds limit.
        
        Returns: (should_trigger, reason)
        """
        if self.triggered:
            return True, "Circuit breaker already triggered"
        
        # Set daily start equity if not set (at market open)
        if self.daily_start_equity is None:
            self.daily_start_equity = current_equity
            return False, ""
        
        # Calculate daily P&L
        daily_pnl = current_equity - self.daily_start_equity
        daily_pnl_pct = daily_pnl / self.daily_start_equity
        
        # Check against limit
        if daily_pnl_pct <= -self.limit_pct:
            self.triggered = True
            return True, f"Daily loss {daily_pnl_pct:.2%} exceeds limit {-self.limit_pct:.2%}"
        
        return False, ""
    
    def reset(self):
        """Reset for new trading day."""
        self.daily_start_equity = None
        self.triggered = False  # Requires manual reset
```

**Action on Trigger:**
1. Immediately halt all new position opening
2. Cancel all open limit orders
3. Close all positions at market (optional, configurable)
4. Send CRITICAL alert to Telegram + SMS
5. Log detailed state before halt
6. Require manual reset to resume trading

### 4.2 Total Drawdown Circuit Breaker

**Trigger:** Drawdown from peak equity exceeds 15%

```python
class DrawdownCircuitBreaker:
    def __init__(self, max_drawdown: float = 0.15):
        self.max_drawdown = max_drawdown
        self.peak_equity = 0.0
        self.triggered = False
        
    def check(self, current_equity: float) -> Tuple[bool, str]:
        """
        Check if drawdown from peak exceeds limit.
        """
        if self.triggered:
            return True, "Circuit breaker already triggered"
        
        # Update peak
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        # Calculate drawdown
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            
            if drawdown >= self.max_drawdown:
                self.triggered = True
                return True, f"Drawdown {drawdown:.2%} exceeds limit {self.max_drawdown:.2%}"
        
        return False, ""
    
    def reset(self):
        """Manual reset only."""
        self.triggered = False
```

**Action on Trigger:**
1. Halt all trading immediately
2. Review all open positions
3. Cancel open orders
4. Send CRITICAL alert
5. Require manual investigation and reset

### 4.3 Volatility Circuit Breaker

**Trigger:** Market volatility exceeds 3x recent average

```python
class VolatilityCircuitBreaker:
    def __init__(self, multiplier: float = 3.0, lookback_days: int = 20):
        self.multiplier = multiplier
        self.lookback_days = lookback_days
        self.triggered = False
        
    def check(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if current volatility is extreme.
        """
        if self.triggered:
            return True, "Volatility circuit breaker active"
        
        # Get recent price history
        prices = get_price_history(symbol, self.lookback_days)
        
        # Calculate ATR (Average True Range) as volatility proxy
        current_atr = calculate_atr(prices, period=14)
        average_atr = prices['atr'].mean()
        
        # Check if current volatility is extreme
        volatility_ratio = current_atr / average_atr
        
        if volatility_ratio > self.multiplier:
            self.triggered = True
            return True, f"Volatility {volatility_ratio:.1f}x normal, exceeds {self.multiplier}x limit"
        
        return False, ""
    
    def reset(self):
        """Manual reset after reviewing conditions."""
        self.triggered = False
```

**Action on Trigger:**
1. Pause new position entries (don't close existing)
2. Tighten stop losses on open positions (optional)
3. Send WARNING alert
4. Resume when volatility normalizes OR manual override

### 4.4 Coordinated Circuit Breaker System

```python
class CircuitBreakerSystem:
    """Manages all circuit breakers."""
    
    def __init__(self):
        self.daily_loss_cb = DailyLossCircuitBreaker()
        self.drawdown_cb = DrawdownCircuitBreaker()
        self.volatility_cb = VolatilityCircuitBreaker()
        
    def check_all(self, current_equity: float, symbol: str = None) -> Tuple[bool, List[str]]:
        """
        Check all circuit breakers.
        
        Returns: (any_triggered, list of reasons)
        """
        reasons = []
        
        # Check daily loss
        triggered, reason = self.daily_loss_cb.check(current_equity)
        if triggered:
            reasons.append(f"DAILY LOSS: {reason}")
        
        # Check drawdown
        triggered, reason = self.drawdown_cb.check(current_equity)
        if triggered:
            reasons.append(f"MAX DRAWDOWN: {reason}")
        
        # Check volatility (if symbol provided)
        if symbol:
            triggered, reason = self.volatility_cb.check(symbol)
            if triggered:
                reasons.append(f"VOLATILITY: {reason}")
        
        return len(reasons) > 0, reasons
    
    def trigger_emergency_stop(self, reasons: List[str]):
        """
        Execute emergency stop procedures.
        """
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reasons}")
        
        # 1. Cancel all open orders
        cancel_all_orders()
        
        # 2. Close all positions (if configured)
        if config.circuit_breaker.close_positions:
            close_all_positions_at_market()
        
        # 3. Set bot state to HALTED
        bot.state = BotState.HALTED
        
        # 4. Send critical alerts
        alert_manager.send_critical(f"🚨 CIRCUIT BREAKER TRIGGERED\n\n" + "\n".join(reasons))
        alert_manager.send_sms(f"CIRCUIT BREAKER TRIGGERED: {reasons[0]}")
        
        # 5. Log detailed state
        log_circuit_breaker_event(reasons)
    
    def reset_all(self, manual_override: bool = False):
        """
        Reset circuit breakers.
        
        Requires manual_override=True for safety.
        """
        if not manual_override:
            raise ValueError("Circuit breaker reset requires manual_override=True")
        
        self.daily_loss_cb.reset()
        self.drawdown_cb.reset()
        self.volatility_cb.reset()
        
        logger.info("Circuit breakers manually reset")
        alert_manager.send_info("Circuit breakers reset - trading resumed")
```

---

## 5. Failure Mode Handling

### 5.1 Internet/API Connection Loss

**Detection:**
```python
import time
import requests

def check_api_connectivity() -> bool:
    """Ping API endpoints to verify connectivity."""
    try:
        # Try multiple endpoints
        response = requests.get('https://api.alpaca.markets/v2/account', 
                                headers={'APCA-API-KEY-ID': api_key},
                                timeout=5)
        return response.status_code in [200, 401]  # 401 = connected but auth issue
    except (requests.Timeout, requests.ConnectionError):
        return False

def monitor_connectivity():
    """Continuously monitor API connectivity."""
    consecutive_failures = 0
    MAX_FAILURES = 3
    
    while bot.state == BotState.RUNNING:
        if not check_api_connectivity():
            consecutive_failures += 1
            logger.warning(f"API connectivity check failed ({consecutive_failures}/{MAX_FAILURES})")
            
            if consecutive_failures >= MAX_FAILURES:
                handle_connection_loss()
                break
        else:
            consecutive_failures = 0
        
        time.sleep(30)  # Check every 30 seconds
```

**Action on Connection Loss:**
```python
def handle_connection_loss():
    """
    Handle complete loss of API connectivity.
    
    This is CRITICAL - must protect capital if we can't communicate with exchange.
    """
    logger.critical("INTERNET/API CONNECTION LOST")
    
    # 1. Try to cancel all orders (if possible)
    try:
        cancel_all_orders()
        logger.info("Successfully cancelled all orders before disconnect")
    except Exception as e:
        logger.error(f"Failed to cancel orders: {e}")
    
    # 2. Try to close all positions at market (if configured and possible)
    if config.disconnect_close_positions:
        try:
            close_all_positions_at_market()
            logger.info("Successfully closed all positions before disconnect")
        except Exception as e:
            logger.error(f"Failed to close positions: {e}")
    
    # 3. Set state to ERROR
    bot.state = BotState.ERROR
    
    # 4. Send alerts (if possible via different network route)
    try:
        alert_manager.send_critical("🚨 API CONNECTION LOST - Trading halted")
        alert_manager.send_sms("API CONNECTION LOST")
    except:
        pass  # Alert system may be down too
    
    # 5. Log state to disk
    save_state_to_disk()
    
    # 6. Attempt reconnection loop
    attempt_reconnection()
```

**Reconnection Procedure:**
```python
def attempt_reconnection():
    """
    Try to reconnect with exponential backoff.
    """
    attempt = 0
    max_wait = 300  # 5 minutes max
    
    while bot.state == BotState.ERROR:
        wait_time = min(2 ** attempt, max_wait)
        logger.info(f"Reconnection attempt {attempt+1} in {wait_time}s")
        time.sleep(wait_time)
        
        if check_api_connectivity():
            logger.info("Connectivity restored")
            reconcile_state()
            bot.state = BotState.RUNNING
            alert_manager.send_info("Connectivity restored - trading resumed")
            break
        
        attempt += 1
```

### 5.2 Exchange Downtime

**Detection:**
```python
def check_exchange_status() -> Tuple[bool, str]:
    """
    Check if exchange is operational.
    
    Returns: (is_operational, status_message)
    """
    try:
        # Alpaca status check
        response = requests.get('https://alpaca.markets/status', timeout=5)
        if response.status_code == 200:
            return True, "Exchange operational"
        
        # Binance status check
        binance_response = exchange.fetch_status()
        if binance_response['status'] == 'ok':
            return True, "Exchange operational"
        
        return False, "Exchange reporting issues"
    except:
        return False, "Unable to reach exchange"
```

**Action on Exchange Downtime:**
```python
def handle_exchange_downtime():
    """
    Pause trading during exchange downtime.
    
    DO NOT cancel orders - they're on the exchange and may be unreachable.
    """
    logger.warning("Exchange downtime detected")
    
    # 1. Pause all new trading
    bot.state = BotState.PAUSED
    
    # 2. DO NOT try to cancel orders (can't reach exchange)
    
    # 3. Monitor exchange status
    alert_manager.send_warning("Exchange downtime - trading paused")
    
    # 4. Wait for exchange to come back
    while True:
        time.sleep(60)
        
        is_operational, status = check_exchange_status()
        if is_operational:
            logger.info("Exchange back online")
            reconcile_orders()  # Sync order status
            bot.state = BotState.RUNNING
            alert_manager.send_info("Exchange operational - trading resumed")
            break
```

### 5.3 Flash Crash Response

**Detection:**
```python
def detect_flash_crash(symbol: str) -> bool:
    """
    Detect extreme price movement that may indicate flash crash.
    
    Criteria: Price moves > 10% in < 1 minute
    """
    recent_prices = get_last_n_candles(symbol, timeframe='1m', n=2)
    
    if len(recent_prices) < 2:
        return False
    
    current_price = recent_prices[-1]['close']
    previous_price = recent_prices[-2]['close']
    
    price_change_pct = abs(current_price - previous_price) / previous_price
    
    return price_change_pct > 0.10  # 10% move
```

**Action on Flash Crash:**
```python
def handle_flash_crash(symbol: str):
    """
    Special handling for flash crash events.
    
    Flash crashes cause:
    - Liquidity evaporation
    - Stops get "jumped" (skip past stop price)
    - Spreads widen dramatically
    """
    logger.critical(f"FLASH CRASH DETECTED: {symbol}")
    
    # 1. Pause all trading immediately
    bot.state = BotState.PAUSED
    
    # 2. DO NOT submit market orders (spreads too wide)
    
    # 3. Review positions in crashed symbol
    affected_positions = [p for p in positions if p.symbol == symbol]
    
    # 4. Wait for volatility to calm down
    alert_manager.send_critical(f"Flash crash detected in {symbol} - trading paused")
    
    # 5. Manual intervention required
    logger.info("Waiting for manual review before resuming")
```

### 5.4 Partial Fills & Stuck Orders

**Handling Partial Fills:**
```python
def handle_partial_fill(order: Order):
    """
    Handle order that was only partially filled.
    """
    logger.info(f"Partial fill: {order.filled_quantity}/{order.quantity} filled")
    
    # Calculate remaining quantity
    remaining = order.quantity - order.filled_quantity
    
    # Decision: Cancel and leave partial position, or keep order open?
    if remaining / order.quantity < 0.10:  # < 10% remaining
        # Cancel remainder, accept partial position
        cancel_order(order.id)
        logger.info(f"Cancelled remainder of order (< 10% unfilled)")
        
        # Adjust stop loss for partial position
        adjust_stop_for_partial_fill(order)
    else:
        # Keep order open for now, monitor timeout
        order.partial_fill_time = datetime.now()
        logger.info(f"Keeping order open, monitoring for timeout")
```

**Detecting Stuck Orders:**
```python
def check_for_stuck_orders():
    """
    Identify orders that have been open too long without filling.
    """
    MAX_ORDER_AGE = 300  # 5 minutes
    
    for order in get_open_orders():
        age = (datetime.now() - order.submitted_at).total_seconds()
        
        if age > MAX_ORDER_AGE:
            logger.warning(f"Stuck order detected: {order.id}")
            handle_stuck_order(order)

def handle_stuck_order(order: Order):
    """
    Handle order that hasn't filled in reasonable time.
    """
    # Option 1: Cancel and resubmit at current market price
    cancel_order(order.id)
    
    # Get current market price
    current_price = get_current_price(order.symbol)
    
    # Resubmit at better price (closer to market)
    new_order = resubmit_order(order, new_price=current_price * 0.999)
    
    logger.info(f"Resubmitted stuck order at new price: {new_order.price}")
```

### 5.5 Order Reconciliation

**Purpose:** Ensure local state matches exchange state

```python
def reconcile_orders():
    """
    Sync order status between bot and exchange.
    
    Call this:
    - After reconnection
    - After exchange downtime
    - Every hour as preventive measure
    """
    logger.info("Starting order reconciliation")
    
    # Get orders from local database
    local_orders = db.get_open_orders()
    
    # Get orders from exchange
    exchange_orders = exchange_api.get_open_orders()
    
    # Create lookup dictionaries
    local_by_id = {o.exchange_id: o for o in local_orders}
    exchange_by_id = {o['id']: o for o in exchange_orders}
    
    # Check for discrepancies
    for order_id, local_order in local_by_id.items():
        if order_id not in exchange_by_id:
            # Order in local DB but not on exchange
            logger.warning(f"Order {order_id} not found on exchange")
            
            # Fetch order history to determine what happened
            order_history = exchange_api.get_order(order_id)
            
            if order_history['status'] == 'filled':
                # Update local state to filled
                update_order_status(local_order, 'filled', order_history)
            elif order_history['status'] == 'cancelled':
                # Update local state to cancelled
                update_order_status(local_order, 'cancelled', order_history)
    
    logger.info("Order reconciliation complete")
```

---

## 6. Validation Checklist

### Before Opening Any Position

```python
def validate_signal_comprehensive(signal: Signal) -> Tuple[bool, str]:
    """
    Master validation function - all checks before opening position.
    
    Returns: (approved, rejection_reason)
    """
    # 1. Circuit breakers
    any_triggered, reasons = circuit_breaker_system.check_all(
        current_equity=account.equity,
        symbol=signal.symbol
    )
    if any_triggered:
        return False, f"Circuit breaker: {reasons[0]}"
    
    # 2. Position sizing
    position_size = calculate_position_size(
        account_equity=account.equity,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss
    )
    
    if position_size == 0:
        return False, "Position size calculated as zero"
    
    # 3. Portfolio heat
    approved, reason = validate_new_position_heat(
        signal, position_size, current_positions
    )
    if not approved:
        return False, reason
    
    # 4. Position count
    approved, reason = validate_position_count(
        signal.strategy, signal.market, current_positions
    )
    if not approved:
        return False, reason
    
    # 5. Correlation risk
    approved, reason = check_correlation_risk(
        signal.symbol, current_positions
    )
    if not approved:
        return False, reason
    
    # 6. Leverage
    position_value = position_size * signal.entry_price
    approved, reason = validate_leverage(
        position_value, signal.market, current_positions
    )
    if not approved:
        return False, reason
    
    # 7. Minimum account balance
    if account.equity < config.min_account_balance:
        return False, f"Account equity below minimum ({config.min_account_balance})"
    
    # 8. Market hours (for stocks)
    if signal.market == 'stocks':
        if not is_market_open():
            return False, "Market closed"
    
    # 9. Stop loss sanity check
    if signal.stop_loss is None:
        return False, "No stop loss provided - MANDATORY"
    
    stop_distance_pct = abs(signal.entry_price - signal.stop_loss) / signal.entry_price
    if stop_distance_pct < 0.01:
        return False, "Stop loss too tight (< 1%)"
    if stop_distance_pct > 0.10:
        return False, "Stop loss too wide (> 10%)"
    
    # All checks passed
    return True, "Approved"
```

---

## 7. Emergency Procedures

### 7.1 Manual Kill Switch

**Telegram Command:**
```python
@bot.command('/killswitch')
def killswitch_command(update, context):
    """Emergency stop via Telegram."""
    user_id = update.effective_user.id
    
    # Verify authorized user
    if user_id != config.authorized_user_id:
        update.message.reply_text("Unauthorized")
        return
    
    # Confirm action
    update.message.reply_text("⚠️ KILL SWITCH ACTIVATED\nCancelling orders and closing positions...")
    
    # Execute kill switch
    bot_controller.kill_switch()
    
    # Report results
    update.message.reply_text("✅ Kill switch complete\n" + get_final_state_summary())
```

**Dashboard Button:**
```python
# Streamlit dashboard
if st.button("🚨 KILL SWITCH", type="primary"):
    st.warning("Confirm: This will close all positions and halt trading")
    
    if st.button("Confirm Kill Switch"):
        bot_controller.kill_switch()
        st.error("KILL SWITCH ACTIVATED")
```

**Kill Switch Implementation:**
```python
def kill_switch():
    """
    Emergency stop - close everything immediately.
    """
    logger.critical("KILL SWITCH ACTIVATED")
    
    # 1. Set state to HALTED
    bot.state = BotState.HALTED
    
    # 2. Cancel ALL orders across ALL exchanges
    cancelled_count = 0
    for exchange_name, exchange in exchanges.items():
        try:
            open_orders = exchange.fetch_open_orders()
            for order in open_orders:
                exchange.cancel_order(order['id'], order['symbol'])
                cancelled_count += 1
        except Exception as e:
            logger.error(f"Error cancelling orders on {exchange_name}: {e}")
    
    logger.info(f"Cancelled {cancelled_count} orders")
    
    # 3. Close ALL positions at market
    closed_count = 0
    for exchange_name, exchange in exchanges.items():
        try:
            positions = get_open_positions(exchange_name)
            for position in positions:
                close_position_at_market(position)
                closed_count += 1
        except Exception as e:
            logger.error(f"Error closing positions on {exchange_name}: {e}")
    
    logger.info(f"Closed {closed_count} positions")
    
    # 4. Send alerts
    summary = f"""
    KILL SWITCH EXECUTED
    
    Cancelled: {cancelled_count} orders
    Closed: {closed_count} positions
    Final Equity: ${account.equity:,.2f}
    
    Bot is HALTED. Manual reset required.
    """
    
    alert_manager.send_critical(summary)
    alert_manager.send_sms("KILL SWITCH EXECUTED")
    
    # 5. Save final state
    save_state_to_disk()
```

### 7.2 Resetting After Circuit Breaker

**Manual Reset Procedure:**
```python
def reset_circuit_breakers(admin_password: str):
    """
    Reset circuit breakers after manual review.
    
    Requires password to prevent accidental reset.
    """
    if admin_password != config.admin_password:
        raise ValueError("Invalid admin password")
    
    logger.info("Circuit breakers being manually reset")
    
    # 1. Review what triggered
    triggered_breakers = []
    if daily_loss_cb.triggered:
        triggered_breakers.append("Daily Loss")
    if drawdown_cb.triggered:
        triggered_breakers.append("Max Drawdown")
    if volatility_cb.triggered:
        triggered_breakers.append("Volatility")
    
    # 2. Log the reset
    logger.info(f"Resetting breakers: {triggered_breakers}")
    
    # 3. Reset all breakers
    circuit_breaker_system.reset_all(manual_override=True)
    
    # 4. Resume bot
    bot.state = BotState.RUNNING
    
    # 5. Alert
    alert_manager.send_info(f"Circuit breakers reset. Breakers that were triggered: {triggered_breakers}")
    
    return f"Reset complete. Triggered breakers: {triggered_breakers}"
```

---

## 8. Risk Metrics & Reporting

### 8.1 Daily Risk Report

```python
def generate_daily_risk_report() -> Dict:
    """
    Calculate all risk metrics for daily summary.
    """
    return {
        'account_equity': account.equity,
        'daily_pnl': account.equity - daily_start_equity,
        'daily_pnl_pct': (account.equity - daily_start_equity) / daily_start_equity,
        
        'peak_equity': drawdown_cb.peak_equity,
        'current_drawdown': calculate_current_drawdown(),
        'current_drawdown_pct': calculate_current_drawdown() / drawdown_cb.peak_equity,
        
        'portfolio_heat': calculate_portfolio_heat(current_positions),
        'position_count': len(current_positions),
        'total_position_value': sum(p.quantity * p.current_price for p in current_positions),
        'leverage': calculate_current_leverage(current_positions),
        
        'circuit_breakers': {
            'daily_loss': daily_loss_cb.triggered,
            'max_drawdown': drawdown_cb.triggered,
            'volatility': volatility_cb.triggered
        },
        
        'risk_warnings': get_risk_warnings()
    }
```

### 8.2 Risk Warnings

```python
def get_risk_warnings() -> List[str]:
    """
    Identify risk conditions approaching limits.
    """
    warnings = []
    
    # Check if approaching circuit breaker limits
    daily_pnl_pct = (account.equity - daily_start_equity) / daily_start_equity
    if daily_pnl_pct < -0.03:  # -3% (60% of 5% limit)
        warnings.append(f"Daily loss at {daily_pnl_pct:.1%}, approaching -5% limit")
    
    current_dd = calculate_current_drawdown() / drawdown_cb.peak_equity
    if current_dd > 0.10:  # 10% (67% of 15% limit)
        warnings.append(f"Drawdown at {current_dd:.1%}, approaching 15% limit")
    
    portfolio_heat = calculate_portfolio_heat(current_positions)
    if portfolio_heat > 0.05:  # 5% (83% of 6% limit)
        warnings.append(f"Portfolio heat at {portfolio_heat:.1%}, approaching 6% limit")
    
    # Check for high correlation
    for i, pos1 in enumerate(current_positions):
        for pos2 in current_positions[i+1:]:
            corr = calculate_correlation(pos1.symbol, pos2.symbol)
            if abs(corr) > 0.7:
                warnings.append(f"High correlation ({corr:.2f}) between {pos1.symbol} and {pos2.symbol}")
    
    return warnings
```

---

## 9. Testing Requirements

### 9.1 Risk Management Unit Tests

**Must achieve 100% test coverage for all risk logic:**

```python
# test_risk_manager.py

def test_position_sizing_basic():
    """Test basic 2% position sizing."""
    rm = RiskManager(account_equity=10000)
    size = rm.calculate_position_size(
        entry_price=400,
        stop_loss=396,
        position_risk_pct=0.02
    )
    assert size == 50  # 2% of 10k = 200, 200 / 4 = 50

def test_position_sizing_with_max_limit():
    """Test position sizing respects max position value limit."""
    rm = RiskManager(account_equity=10000)
    size = rm.calculate_position_size(
        entry_price=100,
        stop_loss=99,  # Tiny stop = huge size without limit
        position_risk_pct=0.02
    )
    # Should be capped at 30% of equity = 3000 / 100 = 30 shares
    assert size <= 30

def test_circuit_breaker_daily_loss():
    """Test daily loss circuit breaker triggers at 5%."""
    cb = DailyLossCircuitBreaker()
    cb.daily_start_equity = 10000
    
    # At 4.9% loss - should NOT trigger
    triggered, _ = cb.check(9510)
    assert not triggered
    
    # At 5.0% loss - should trigger
    triggered, reason = cb.check(9500)
    assert triggered
    assert "5" in reason

def test_circuit_breaker_max_drawdown():
    """Test max drawdown circuit breaker."""
    cb = DrawdownCircuitBreaker()
    cb.peak_equity = 12000
    
    # At 14% drawdown - should NOT trigger
    triggered, _ = cb.check(10320)
    assert not triggered
    
    # At 15% drawdown - should trigger
    triggered, reason = cb.check(10200)
    assert triggered

def test_portfolio_heat_calculation():
    """Test portfolio heat calculation."""
    positions = [
        Position(entry_price=100, stop_loss=98, quantity=50),  # Risk: 100
        Position(entry_price=200, stop_loss=195, quantity=10)  # Risk: 50
    ]
    
    heat = calculate_portfolio_heat(positions, account_equity=10000)
    assert heat == 0.015  # 150 / 10000 = 1.5%

def test_correlation_rejection():
    """Test highly correlated positions are rejected."""
    existing_positions = [Position(symbol='SPY')]
    
    # QQQ is highly correlated with SPY
    approved, reason = check_correlation_risk('QQQ', existing_positions)
    assert not approved
    assert 'correlation' in reason.lower()

# Run all tests with: pytest test_risk_manager.py -v --cov=src/risk_manager
```

### 9.2 Stress Test Scenarios

**Must pass all stress tests before live deployment:**

1. **Internet Loss Scenario**
   - Simulate network disconnect
   - Verify kill switch triggers
   - Verify orders cancelled (if possible)
   - Verify reconnection logic

2. **Flash Crash Scenario**
   - Inject 15% price drop in 30 seconds
   - Verify volatility circuit breaker triggers
   - Verify no panic selling at worst prices

3. **Partial Fill Scenario**
   - Mock order partially filled (40% filled)
   - Verify position tracking correct
   - Verify stop loss adjusted appropriately

4. **Simultaneous Losses Scenario**
   - Simulate multiple positions hitting stops simultaneously
   - Verify circuit breaker triggers if total loss > 5%
   - Verify remaining positions handled correctly

5. **Exchange Downtime Scenario**
   - Mock 503 errors from exchange API
   - Verify trading pauses gracefully
   - Verify resume when exchange recovers

---

## 10. Configuration Reference

### 10.1 Risk Configuration File

```yaml
# config/risk.yaml

position:
  # Position-level controls
  risk_pct: 0.02  # Risk 2% per trade
  max_position_pct: 0.30  # Max 30% in single position
  min_stop_distance_pct: 0.01  # Min 1% stop distance
  max_stop_distance_pct: 0.10  # Max 10% stop distance

portfolio:
  # Portfolio-level controls
  max_portfolio_heat: 0.06  # Max 6% total risk
  max_total_positions: 10
  max_positions_per_strategy: 3
  max_positions_per_market: 5
  correlation_threshold: 0.7  # Flag if > 70% correlated
  max_correlated_positions: 2

leverage:
  # Leverage limits
  max_leverage_stocks: 1.0  # No leverage
  max_leverage_crypto: 1.5  # Max 1.5x

circuit_breakers:
  # Circuit breaker settings
  daily_loss_limit: 0.05  # 5% daily loss
  max_drawdown: 0.15  # 15% from peak
  volatility_multiplier: 3.0  # Pause if vol > 3x
  
  # Actions on trigger
  close_positions_on_trigger: false  # Keep positions open
  send_sms_alert: true
  require_manual_reset: true

emergency:
  # Kill switch settings
  disconnect_close_positions: true  # Close if API lost
  min_account_balance: 100  # Halt if below this
  authorized_users: ['123456789']  # Telegram user IDs
```

---

## Summary

This Risk Management Specification defines a comprehensive, multi-layered risk control system designed to protect capital in all market conditions and failure scenarios. The system is designed to **fail safe** - any unexpected condition results in trading halt rather than uncontrolled losses.

**Key Principles:**
1. ✅ **Every position MUST have a stop loss**
2. ✅ **Never risk more than 2% per trade**
3. ✅ **Total portfolio risk capped at 6%**
4. ✅ **Circuit breakers are non-negotiable**
5. ✅ **System defaults to safe state on any error**

**Implementation Priority:**
- **CRITICAL**: Position sizing, stop losses, circuit breakers
- **HIGH**: Portfolio heat, leverage limits, correlation checks
- **MEDIUM**: Volatility detection, position count limits
- **LOW**: Advanced correlation analysis, adaptive parameters

**Before going live, ensure:**
- [ ] All unit tests passing (100% coverage on risk logic)
- [ ] All stress tests passing
- [ ] Circuit breakers tested and functional
- [ ] Kill switch tested from all interfaces
- [ ] Order reconciliation tested
- [ ] Reconnection logic tested
- [ ] 6 months successful paper trading

**Remember:** The goal is to survive long enough to profit. Risk management is more important than any individual trade or strategy.

---

**Document Status**: Implementation Ready  
**Required Review**: Before any live deployment with real capital
