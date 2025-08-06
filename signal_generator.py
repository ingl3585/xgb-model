import pandas as pd
import numpy as np
from collections import deque
from typing import Deque

import model
import config

# Track recent signal accuracy (1.0 = win, 0.0 = loss)
ACCURACY_HISTORY: Deque[float] = deque(maxlen=50)

def _dynamic_threshold() -> float:
    if not ACCURACY_HISTORY:
        return config.SIGNAL_DEFAULT_THRESHOLD
    
    recent_accuracy = np.mean(ACCURACY_HISTORY)
    
    # Adjust threshold based on recent performance
    if recent_accuracy < 0.35:  # Poor performance
        adjustment = 0.1
    elif recent_accuracy < 0.5:  # Below breakeven
        adjustment = 0.05
    elif recent_accuracy > 0.65:  # Good performance
        adjustment = -0.05
    else:  # Neutral performance
        adjustment = 0.0
    
    threshold = config.SIGNAL_DEFAULT_THRESHOLD + adjustment
    return min(max(threshold, config.SIGNAL_THRESHOLD_MIN), config.SIGNAL_THRESHOLD_MAX)

def generate_signal(df: pd.DataFrame) -> str:
    signal, prob = model.predict(df)
    
    threshold = _dynamic_threshold()
    if prob > threshold:
        if signal == 1:
            return "BUY"
        else:
            return "SELL"
    else:
        return "HOLD"

def record_result(was_correct: bool):
    """Record whether the last signal was correct"""
    ACCURACY_HISTORY.append(1.0 if was_correct else 0.0)