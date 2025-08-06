import pandas as pd
import numpy as np
from typing import Tuple, List, Dict
from xgboost import XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
import joblib
import os

import indicators
import config

MODELS_DIR = "models"
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_CACHE = None

def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df['EMA_fast'] = indicators.calculate_ema(df, config.EMA_FAST)
    df['EMA_slow'] = indicators.calculate_ema(df, config.EMA_SLOW)
    df['EMA_diff'] = df['EMA_fast'] - df['EMA_slow']

    df['RSI'] = indicators.calculate_rsi(df)

    macd_line, macd_signal, macd_hist = indicators.calculate_macd(df)
    df['MACD'] = macd_line
    df['MACD_signal'] = macd_signal
    df['MACD_hist'] = macd_hist

    boll_mid, boll_up, boll_low = indicators.calculate_bollinger_bands(df)
    df['BOLL_mid'] = boll_mid
    df['BOLL_up'] = boll_up
    df['BOLL_low'] = boll_low
    df['BOLL_width'] = (boll_up - boll_low) / boll_mid

    df['ATR'] = indicators.calculate_atr(df)
    df['VWAP'] = indicators.calculate_vwap(df)
    df['return_1'] = df['close'].pct_change()
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)

    return df

def prepare_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    df = df.copy()
    print(f"Starting with {len(df)} bars")
    
    # First rename columns to lowercase for consistency with indicators
    column_mapping = {
        'Open': 'open',
        'High': 'high', 
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume',
        'Timestamp': 'timestamp'
    }
    df = df.rename(columns=column_mapping)
    print(f"After renaming columns: {len(df)} bars")
    
    df = _compute_indicators(df)
    print(f"After computing indicators: {len(df)} bars")
    print(f"Columns after indicators: {df.columns.tolist()}")
    
    # Check for NaN values before dropping
    nan_counts = df.isnull().sum()
    print(f"NaN counts per column:\n{nan_counts}")
    
    # Instead of aggressive dropna(), only drop rows where critical features are NaN
    # Keep rows where only early-period indicators are NaN (expected behavior)
    critical_features = ['close', 'EMA_diff', 'RSI', 'MACD', 'VWAP', 'return_1', 'target']
    
    # Fill NaN Bollinger Bands with reasonable defaults for early periods
    df['BOLL_width'] = df['BOLL_width'].fillna(0.02)  # Default width
    df['BOLL_mid'] = df['BOLL_mid'].fillna(df['close'])  # Use close price
    df['BOLL_up'] = df['BOLL_up'].fillna(df['close'] * 1.01)  # Close + 1%
    df['BOLL_low'] = df['BOLL_low'].fillna(df['close'] * 0.99)  # Close - 1%
    
    # Only drop rows where critical features are still NaN
    df = df.dropna(subset=critical_features)
    print(f"After selective dropna(): {len(df)} bars")

    feature_cols: List[str] = [
        'EMA_diff', 'RSI', 'MACD', 'MACD_hist', 'BOLL_width', 
        'ATR', 'return_1', 'close', 'VWAP'
    ]

    X = df[feature_cols]
    y = df['target']
    return X, y

def train_model(df: pd.DataFrame, model_name: str = "xgb_classifier.joblib") -> Dict[str, float]:
    X, y = prepare_features(df)
    
    print(f"After feature preparation: X shape {X.shape}, y shape {y.shape}")
    
    if len(X) == 0:
        raise ValueError("No samples left after feature preparation")
    
    # Adjust number of folds based on available data
    if len(X) < 50:
        # For very small datasets, skip cross-validation and train directly
        print(f"Small dataset ({len(X)} samples), skipping cross-validation")
        n_splits = 0
    else:
        n_splits = min(config.XGB_N_SPLITS, len(X) // 10)  # At least 10 samples per fold
        n_splits = max(2, n_splits)  # Minimum 2 folds
        print(f"Using {n_splits} cross-validation folds for {len(X)} samples")
    
    class_weights = y.value_counts(normalize=True)
    weights = y.map({cls: 1.0 / w for cls, w in class_weights.items()})
    best_iteration_scores = []
    metrics = {}
    
    if n_splits == 0:
        # Skip cross-validation for small datasets
        print("Training single model without cross-validation")
        final_model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            n_estimators=min(50, config.XGB_N_ESTIMATORS),  # Reduce estimators for small datasets
            learning_rate=config.XGB_LEARNING_RATE,
            max_depth=min(3, config.XGB_MAX_DEPTH),  # Reduce depth for small datasets
            subsample=config.XGB_SUBSAMPLE,
            colsample_bytree=config.XGB_COLSAMPLE_BYTREE,
            n_jobs=-1,
            random_state=config.XGB_RANDOM_STATE
        )
        final_model.fit(X, y, sample_weight=weights, verbose=False)
        joblib.dump(final_model, os.path.join(MODELS_DIR, model_name))
        metrics["simple_training"] = True
        return metrics
    
    # Cross-validation training for larger datasets
    tss = TimeSeriesSplit(n_splits=n_splits)
    
    for fold, (train_idx, val_idx) in enumerate(tss.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        w_train, w_val = weights.iloc[train_idx], weights.iloc[val_idx]

        model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            n_estimators=config.XGB_N_ESTIMATORS,
            learning_rate=config.XGB_LEARNING_RATE,
            max_depth=config.XGB_MAX_DEPTH,
            subsample=config.XGB_SUBSAMPLE,
            colsample_bytree=config.XGB_COLSAMPLE_BYTREE,
            early_stopping_rounds=config.XGB_EARLY_STOPPING_ROUNDS,
            n_jobs=-1,
            random_state=config.XGB_RANDOM_STATE
        )

        model.fit(X_train, y_train, sample_weight=w_train, 
                 eval_set=[(X_val, y_val)], sample_weight_eval_set=[w_val], verbose=False)

        preds = (model.predict_proba(X_val)[:, 1] > config.XGB_PREDICTION_THRESHOLD).astype(int)
        acc = accuracy_score(y_val, preds)
        metrics[f"fold_{fold + 1}_accuracy"] = acc
        best_iteration_scores.append(model.best_iteration or model.n_estimators)

    metrics["cv_mean_accuracy"] = float(np.mean(list(metrics.values())))
    metrics["cv_std_accuracy"] = float(np.std(list(metrics.values())))
    metrics["best_iteration_mean"] = float(np.mean(best_iteration_scores))

    n_estimators_final = int(np.mean(best_iteration_scores) * config.XGB_FINAL_MODEL_MULTIPLIER)
    final_model = XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        n_estimators=n_estimators_final,
        learning_rate=config.XGB_LEARNING_RATE,
        max_depth=config.XGB_MAX_DEPTH,
        subsample=config.XGB_SUBSAMPLE,
        colsample_bytree=config.XGB_COLSAMPLE_BYTREE,
        n_jobs=-1,
        random_state=config.XGB_RANDOM_STATE
    )
    final_model.fit(X, y, sample_weight=weights, verbose=False)
    joblib.dump(final_model, os.path.join(MODELS_DIR, model_name))
    return metrics

def _load_model(model_name: str = "xgb_classifier.joblib"):
    global MODEL_CACHE
    if MODEL_CACHE is None:
        model_path = os.path.join(MODELS_DIR, model_name)
        MODEL_CACHE = joblib.load(model_path)
    return MODEL_CACHE

def predict(df_recent: pd.DataFrame, model_name: str = "xgb_classifier.joblib") -> Tuple[int, float]:
    if df_recent.empty:
        raise ValueError("Input dataframe is empty for prediction")
    
    model = _load_model(model_name)
    X, _ = prepare_features(df_recent)
    latest_row = X.iloc[[-1]]
    prob_up = float(model.predict_proba(latest_row)[0, 1])
    signal = int(prob_up > config.XGB_PREDICTION_THRESHOLD)
    
    return signal, prob_up