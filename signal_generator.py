import pandas as pd
import numpy as np
from collections import deque
from typing import Deque, Tuple

import model
import indicators

CONF_HISTORY: Deque[float] = deque(maxlen=100)  # Track recent probability scores

def _dynamic_threshold() -> float:
    if not CONF_HISTORY:
        return 0.55  # sensible default
    mean_conf = np.mean(CONF_HISTORY)
    # Encourage selectivity when model has been confident recently
    return min(max(mean_conf, 0.5), 0.7)

def _volatility_ok(df: pd.DataFrame) -> bool:
    atr = indicators.calculate_atr(df).iloc[-1]
    atr_series = indicators.calculate_atr(df)
    threshold = atr_series.quantile(0.2)
    return bool(atr > threshold)

def _bollinger_ok(df: pd.DataFrame) -> bool:
    _, upper, lower = indicators.calculate_bollinger_bands(df)
    price = df['close'].iloc[-1]
    proximity = min(abs(price - lower.iloc[-1]), abs(upper.iloc[-1] - price)) / (upper.iloc[-1] - lower.iloc[-1])
    return bool(proximity < 0.25)  # within 25% of band

def generate_signal(df: pd.DataFrame) -> Tuple[int, float]:
    signal, prob = model.predict(df)

    # Update history
    CONF_HISTORY.append(prob)

    # Adaptive threshold
    threshold = _dynamic_threshold()
    LOGGER.debug("Adaptive threshold: %.3f", threshold)

    # Volatility/band filters
    if not _volatility_ok(df) or not _bollinger_ok(df):
        LOGGER.debug("Filters veto trade: volatility_ok=%s bollinger_ok=%s", _volatility_ok(df), _bollinger_ok(df))
        return 0, prob

    if prob > threshold:
        return signal, prob
    else:
        return 0, prob
