import config
import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from indicators import calculate_rsi, calculate_ema, calculate_vwap
from logging_config import get_trading_logger, log_performance, log_trading_event
import time

# Initialize model logger
model_logger = get_trading_logger('model')

# Prepare features for ML model
@log_performance(model_logger, "Feature preparation")
def prepare_features(df):
    model_logger.info(
        "Starting feature calculation",
        extra={
            'input_rows': len(df),
            'columns': list(df.columns)
        }
    )
    
    try:
        df['RSI'] = calculate_rsi(df)
        df['EMA_Fast'] = calculate_ema(df, config.EMA_FAST)
        df['EMA_Slow'] = calculate_ema(df, config.EMA_SLOW)
        df['EMA_Diff'] = df['EMA_Fast'] - df['EMA_Slow']
        df['VWAP'] = calculate_vwap(df)
        df['Price_VWAP_Diff'] = df['Close'] - df['VWAP']
        df['Lagged_Return'] = df['Close'].pct_change().shift(1)
        df['Above_VWAP'] = (df['Close'] > df['VWAP']).astype(int)
        
        features = ['RSI', 'EMA_Diff', 'Price_VWAP_Diff', 'Lagged_Return', 'Above_VWAP']
        
        model_logger.info(
            "Feature calculation completed",
            extra={
                'features_created': features,
                'features_count': len(features),
                'output_rows': len(df)
            }
        )
        
        return df, features
        
    except Exception as e:
        model_logger.error(
            "Feature calculation failed",
            extra={
                'error_type': type(e).__name__,
                'input_shape': df.shape if df is not None else None
            },
            exc_info=True
        )
        raise

# Train XGBoost model with proper class mapping
@log_performance(model_logger, "Model training")
def train_model(df, features):
    # Input validation with logging
    model_logger.info(
        "Starting model training",
        extra={
            'input_rows': len(df) if df is not None else 0,
            'features': features,
            'features_count': len(features) if features else 0
        }
    )
    
    if features is None or len(features) == 0:
        model_logger.error("Invalid features list provided")
        raise ValueError("Features list cannot be None or empty")
    
    if df is None or df.empty:
        model_logger.error("Invalid dataframe provided")
        raise ValueError("DataFrame cannot be None or empty")
    
    # Create target variable: 0=Hold, 1=Buy, 2=Sell
    df = df.copy()  # Avoid modifying original dataframe
    df['Target'] = 0  # Default to Hold
    
    # Calculate price change for next bar
    df['Next_Close'] = df['Close'].shift(-1)
    price_change = df['Next_Close'] - df['Close']
    
    # Assign classes: 0=Hold, 1=Buy, 2=Sell (XGBoost compatible)
    df.loc[price_change > config.PRICE_CHANGE_THRESHOLD, 'Target'] = 1  # Buy
    df.loc[price_change < -config.PRICE_CHANGE_THRESHOLD, 'Target'] = 2  # Sell
    
    # Use most recent training window
    train_df = df.iloc[-config.TRAINING_WINDOW:].dropna()
    
    model_logger.debug(
        "Training data prepared",
        extra={
            'original_rows': len(df),
            'training_window': config.TRAINING_WINDOW,
            'training_rows_after_dropna': len(train_df)
        }
    )
    
    if len(train_df) < 100:  # Minimum data requirement
        model_logger.error(
            "Insufficient training data",
            extra={
                'available_rows': len(train_df),
                'minimum_required': 100
            }
        )
        raise ValueError(f"Insufficient training data: {len(train_df)} rows, need at least 100")
    
    X = train_df[features]
    y = train_df['Target']
    
    # Check class distribution
    class_counts = y.value_counts().sort_index()
    
    log_trading_event(
        model_logger,
        'class_distribution_analysis',
        hold_count=class_counts.get(0, 0),
        buy_count=class_counts.get(1, 0),
        sell_count=class_counts.get(2, 0),
        total_samples=len(y)
    )
    
    # Ensure we have all three classes
    unique_classes = sorted(y.unique())
    if len(unique_classes) < 2:
        model_logger.warning(
            "Limited class diversity detected",
            extra={
                'unique_classes_count': len(unique_classes),
                'classes_found': unique_classes,
                'impact': 'Model performance may be reduced'
            }
        )
    
    # Split data ensuring stratification when possible
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=config.TEST_SIZE, 
            random_state=config.XGB_RANDOM_STATE,
            stratify=y if len(unique_classes) > 1 else None
        )
        
        model_logger.debug(
            "Data split completed with stratification",
            extra={
                'train_samples': len(X_train),
                'test_samples': len(X_test),
                'test_size_ratio': config.TEST_SIZE,
                'stratified': True
            }
        )
        
    except ValueError as e:
        model_logger.warning(
            "Stratified split failed, using random split",
            extra={
                'reason': str(e),
                'fallback_method': 'random_split'
            }
        )
        
        # Fallback without stratification if classes are too imbalanced
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=config.TEST_SIZE, 
            random_state=config.XGB_RANDOM_STATE
        )
    
    # Configure XGBoost for multiclass classification
    model = XGBClassifier(
        n_estimators=config.XGB_N_ESTIMATORS,
        max_depth=config.XGB_MAX_DEPTH,
        learning_rate=config.XGB_LEARNING_RATE,
        random_state=config.XGB_RANDOM_STATE,
        objective='multi:softprob',  # Multiclass probability
        num_class=3,  # Three classes: Hold, Buy, Sell
        eval_metric='mlogloss'
    )
    
    # Train the model with timing
    training_start = time.time()
    model.fit(X_train, y_train)
    training_time = time.time() - training_start
    
    # Evaluate model performance
    evaluation_start = time.time()
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    evaluation_time = time.time() - evaluation_start
    
    # Generate detailed classification report
    class_report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    
    log_trading_event(
        model_logger,
        'model_training_complete',
        accuracy=round(accuracy, 4),
        training_samples=len(X_train),
        test_samples=len(X_test),
        training_time_seconds=round(training_time, 3),
        evaluation_time_seconds=round(evaluation_time, 3),
        precision_macro=round(class_report.get('macro avg', {}).get('precision', 0), 4),
        recall_macro=round(class_report.get('macro avg', {}).get('recall', 0), 4),
        f1_macro=round(class_report.get('macro avg', {}).get('f1-score', 0), 4)
    )
    
    # Log per-class performance
    for class_label in ['0', '1', '2']:  # Hold, Buy, Sell
        if class_label in class_report:
            class_names = {0: 'HOLD', 1: 'BUY', 2: 'SELL'}
            model_logger.debug(
                f"Class performance: {class_names.get(int(class_label), class_label)}",
                extra={
                    'class': class_names.get(int(class_label), class_label),
                    'precision': round(class_report[class_label]['precision'], 4),
                    'recall': round(class_report[class_label]['recall'], 4),
                    'f1_score': round(class_report[class_label]['f1-score'], 4),
                    'support': class_report[class_label]['support']
                }
            )
    
    return model