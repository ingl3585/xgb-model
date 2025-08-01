import pandas as pd
import numpy as np
from typing import Tuple, List, Dict
from xgboost import XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
import joblib
import logging
import os

import indicators

MODELS_DIR = "models"
os.makedirs(MODELS_DIR, exist_ok=True)

def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Basic indicators
    df['EMA_fast'] = indicators.calculate_ema(df, 12)
    df['EMA_slow'] = indicators.calculate_ema(df, 26)
    df['EMA_diff'] = df['EMA_fast'] - df['EMA_slow']

    # RSI
    df['RSI'] = indicators.calculate_rsi(df)

    # MACD
    macd_line, macd_signal, macd_hist = indicators.calculate_macd(df)
    df = df.join([macd_line, macd_signal, macd_hist])

    # Bollinger Bands
    boll_mid, boll_up, boll_low = indicators.calculate_bollinger_bands(df)
    df = df.join([boll_mid, boll_up, boll_low])
    df['BOLL_width'] = (boll_up - boll_low) / boll_mid

    # ATR
    df['ATR'] = indicators.calculate_atr(df)

    # VWAP
    df['VWAP'] = indicators.calculate_vwap(df)

    # Lagged return
    df['return_1'] = df['close'].pct_change()

    # Target label (next period direction)
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)

    return df

def _prepare_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    df = _compute_indicators(df)

    # Drop rows with NaNs created by indicators
    df = df.dropna()

    feature_cols: List[str] = [
        'EMA_diff',
        'RSI',
        'MACD',
        'MACD_hist',
        'BOLL_width',
        'ATR',
        'return_1',
        'close',  # raw price level
        'VWAP'
    ]

    X = df[feature_cols]
    y = df['target']
    return X, y

def train_model(df: pd.DataFrame, model_name: str = "xgb_classifier.joblib") -> Dict[str, float]:
    X, y = _prepare_features(df)

    tss = TimeSeriesSplit(n_splits=5)
    metrics = {}

    # Class weights
    class_weights = y.value_counts(normalize=True)
    weights = y.map({cls: 1.0 / w for cls, w in class_weights.items()})

    best_iteration_scores = []

    for fold, (train_idx, val_idx) in enumerate(tss.split(X)):
        LOGGER.info("Training fold %s", fold + 1)
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        w_train, w_val = weights.iloc[train_idx], weights.iloc[val_idx]

        model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            n_estimators=1000,
            learning_rate=0.01,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=-1,
            random_state=42
        )

        model.fit(
            X_train,
            y_train,
            sample_weight=w_train,
            eval_set=[(X_val, y_val)],
            eval_sample_weight=[w_val],
            verbose=False,
            early_stopping_rounds=50,
        )

        preds = (model.predict_proba(X_val)[:, 1] > 0.5).astype(int)
        acc = accuracy_score(y_val, preds)
        metrics[f"fold_{fold + 1}_accuracy"] = acc
        best_iteration_scores.append(model.best_iteration or model.n_estimators)

    LOGGER.info("Cross‑val accuracy: %.4f ± %.4f", np.mean(list(metrics.values())), np.std(list(metrics.values())))
    metrics["cv_mean_accuracy"] = float(np.mean(list(metrics.values())))
    metrics["cv_std_accuracy"] = float(np.std(list(metrics.values())))
    metrics["best_iteration_mean"] = float(np.mean(best_iteration_scores))

    # Fit on full data with best_iterations as guidance
    n_estimators_final = int(np.mean(best_iteration_scores) * 1.1)
    final_model = XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        n_estimators=n_estimators_final,
        learning_rate=0.01,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=-1,
        random_state=42
    )
    final_model.fit(X, y, sample_weight=weights, verbose=False)
    joblib.dump(final_model, os.path.join(MODELS_DIR, model_name))
    LOGGER.info("Saved trained model to %s/%s", MODELS_DIR, model_name)
    return metrics

_MODEL_CACHE = None

def _load_model(model_name: str = "xgb_classifier.joblib"):
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = joblib.load(os.path.join(MODELS_DIR, model_name))
    return _MODEL_CACHE

def predict(df_recent: pd.DataFrame, model_name: str = "xgb_classifier.joblib") -> Tuple[int, float]:
    """Generate a prediction for the most recent row.

    Returns:
        signal (int): 1 for long, 0 for flat/short
        probability (float): predicted probability of upward move
    """
    if df_recent.empty:
        raise ValueError("Input dataframe is empty for prediction")

    model = _load_model(model_name)
    X, _ = _prepare_features(df_recent)
    latest_row = X.iloc[[-1]]
    prob_up = float(model.predict_proba(latest_row)[0, 1])
    signal = int(prob_up > 0.5)
    return signal, prob_up
