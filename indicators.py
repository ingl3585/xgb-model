import pandas as pd
import numpy as np
import config
from typing import Tuple

def calculate_rsi(df: pd.DataFrame, period: int | None = None, price_col: str = "close") -> pd.Series:
    period = period or config.RSI_PERIOD
    diff = df[price_col].diff()
    gain = diff.clip(lower=0)
    loss = -diff.clip(upper=0)

    # Use exponential moving average for RS
    roll_up = gain.ewm(alpha=1 / period, adjust=False).mean()
    roll_down = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = roll_up / (roll_down.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.rename("RSI")

def calculate_ema(df: pd.DataFrame, period: int, price_col: str = "close") -> pd.Series:
    return df[price_col].ewm(span=period, adjust=False).mean()

def calculate_macd(
    df: pd.DataFrame,
    fast: int | None = None,
    slow: int | None = None,
    signal: int | None = None,
    price_col: str = "close"
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    fast = fast or config.MACD_FAST
    slow = slow or config.MACD_SLOW
    signal = signal or config.MACD_SIGNAL

    ema_fast = calculate_ema(df, fast, price_col)
    ema_slow = calculate_ema(df, slow, price_col)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_line.rename("MACD"), signal_line.rename("MACD_signal"), macd_hist.rename("MACD_hist")

def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int | None = None,
    num_std: float | None = None,
    price_col: str = "close"
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    period = period or config.BOLL_PERIOD
    num_std = num_std or config.BOLL_STD

    sma = df[price_col].rolling(window=period, min_periods=period).mean()
    rolling_std = df[price_col].rolling(window=period, min_periods=period).std()

    upper_band = sma + (rolling_std * num_std)
    lower_band = sma - (rolling_std * num_std)
    return sma.rename("BOLL_MID"), upper_band.rename("BOLL_UP"), lower_band.rename("BOLL_LOW")

def calculate_atr(df: pd.DataFrame, period: int | None = None) -> pd.Series:
    period = period or config.ATR_PERIOD
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr.rename("ATR")

def calculate_vwap(df: pd.DataFrame, window: int | None = None) -> pd.Series:
    if window:
        pv = (df['close'] * df['volume']).rolling(window=window).sum()
        vol = df['volume'].rolling(window=window).sum()
        vwap = pv / vol
    else:
        pv = (df['close'] * df['volume']).cumsum()
        vol = df['volume'].cumsum()
        vwap = pv / vol
    return vwap.rename("VWAP")
