import os
import sys

# Ensure vendor directory is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars as sdk

# Strategy parameters (tuned against frozen dev window for optimal PnL & low drawdown)
LOOKBACK_BARS = 120
DIP_THRESHOLD = 0.0080  # 0.80% drop from 120-bar rolling high
TAKE_PROFIT = 0.0127    # 1.27% gain from entry
STOP_LOSS = 0.0150      # 1.50% loss from entry
COOLDOWN_BARS = 110     # Min bars between exit and next entry
MAX_SLIPPAGE_BPS = 100  # 1% max slippage

# State tracking
closes_history = {}  # symbol -> list of float closes
last_exit_seq = {}   # symbol -> seq of last exit
entry_prices = {}    # symbol -> float entry price


def on_batch(state: sdk.BarsState, batch: dict):
    orders = []
    current_seq = batch["seq"]

    for bar in batch["bars"]:
        symbol = bar["symbol"]
        close_price = int(bar["c"])

        if symbol not in closes_history:
            closes_history[symbol] = []
            last_exit_seq[symbol] = -9999
            entry_prices[symbol] = 0

        history = closes_history[symbol]
        history.append(close_price)

        held = state.positions.get(symbol)

        if held is not None and held.qty > 0:
            # Position is held: check exit conditions (TP or SL)
            entry_p = entry_prices.get(symbol, 0)
            if entry_p > 0:
                ret = (close_price - entry_p) / entry_p
                if ret >= TAKE_PROFIT or ret <= -STOP_LOSS:
                    orders.append({
                        "side": "sell",
                        "symbol": symbol,
                        "qty": held.qty,
                        "max_slippage_bps": MAX_SLIPPAGE_BPS
                    })
                    last_exit_seq[symbol] = current_seq
                    entry_prices[symbol] = 0
        else:
            # No position: check dip entry condition
            if len(history) >= LOOKBACK_BARS:
                if current_seq - last_exit_seq[symbol] >= COOLDOWN_BARS:
                    recent_window = history[-LOOKBACK_BARS:]
                    roll_high = max(recent_window)
                    dip = (roll_high - close_price) / roll_high

                    if dip >= DIP_THRESHOLD:
                        # Compute buy spend within limits
                        spend = min(state.cash, state.weight_room(symbol))
                        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
                        if spend >= min_notional:
                            orders.append({
                                "side": "buy",
                                "symbol": symbol,
                                "notional_quote_units": spend,
                                "max_slippage_bps": MAX_SLIPPAGE_BPS
                            })
                            entry_prices[symbol] = close_price

    return orders


if __name__ == "__main__":
    sdk.run(on_batch)

