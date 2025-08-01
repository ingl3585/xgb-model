from model import prepare_features
import numpy as np
from logging_config import get_trading_logger, log_trading_event
import time

# Initialize signals logger
signals_logger = get_trading_logger('signals')

# Generate trading signals with updated class mapping
def generate_signals(df, model, features):
    try:
        signal_start_time = time.time()
        
        signals_logger.debug(
            "Starting signal generation",
            extra={
                'input_rows': len(df),
                'features': features,
                'model_type': type(model).__name__
            }
        )
        
        # Work on a copy to ensure thread safety
        df_copy = df.copy()
        df_processed, _ = prepare_features(df_copy)
        latest_data = df_processed[features].iloc[-1:].dropna()
        
        if latest_data.empty:
            signals_logger.warning(
                "No valid data available for signal generation",
                extra={
                    'processed_rows': len(df_processed),
                    'features_requested': features
                }
            )
            return "HOLD"
        
        # Get prediction and probability with timing
        prediction_start = time.time()
        prediction = model.predict(latest_data)[0]
        probabilities = model.predict_proba(latest_data)[0]
        prediction_time = time.time() - prediction_start
        
        # Class mapping: 0=Hold, 1=Buy, 2=Sell  
        max_prob = np.max(probabilities)
        confidence_threshold = 0.6  # Minimum confidence for trade signals
        
        signals_logger.debug(
            "ML prediction completed",
            extra={
                'prediction': int(prediction),
                'probabilities': probabilities.tolist(),
                'max_confidence': round(max_prob, 4),
                'confidence_threshold': confidence_threshold,
                'prediction_time_ms': round(prediction_time * 1000, 2)
            }
        )
        
        # Additional filters for signal quality
        current_price = df_processed['Close'].iloc[-1]
        current_vwap = df_processed['VWAP'].iloc[-1]
        current_rsi = df_processed['RSI'].iloc[-1]
        
        signals_logger.debug(
            "Market context for signal generation",
            extra={
                'current_price': round(current_price, 2),
                'current_vwap': round(current_vwap, 2),
                'current_rsi': round(current_rsi, 2),
                'price_vs_vwap': 'above' if current_price > current_vwap else 'below'
            }
        )
        
        # Only trade with sufficient confidence
        if max_prob < confidence_threshold:
            signals_logger.debug(
                "Signal filtered due to low confidence",
                extra={
                    'confidence': round(max_prob, 4),
                    'threshold': confidence_threshold,
                    'raw_prediction': int(prediction)
                }
            )
            return "HOLD"
        
        final_signal = "HOLD"  # Default signal
        signal_reason = "default"
        
        if prediction == 1:  # Buy signal
            # Additional buy conditions: price above VWAP and RSI not overbought
            if current_price > current_vwap and current_rsi < 70:
                final_signal = "BUY"
                signal_reason = "ml_prediction_with_filters"
            else:
                signal_reason = f"buy_filtered_price_vs_vwap={current_price > current_vwap}_rsi={current_rsi < 70}"
                
        elif prediction == 2:  # Sell signal  
            # Additional sell conditions: price below VWAP and RSI not oversold
            if current_price < current_vwap and current_rsi > 30:
                final_signal = "SELL"
                signal_reason = "ml_prediction_with_filters"
            else:
                signal_reason = f"sell_filtered_price_vs_vwap={current_price < current_vwap}_rsi={current_rsi > 30}"
        else:
            signal_reason = "ml_prediction_hold"
        
        # Log the final signal generation
        processing_time = time.time() - signal_start_time
        
        log_trading_event(
            signals_logger,
            'signal_generated',
            signal=final_signal,
            reason=signal_reason,
            ml_prediction=int(prediction),
            confidence=round(max_prob, 4),
            market_price=round(current_price, 2),
            vwap=round(current_vwap, 2),
            rsi=round(current_rsi, 2),
            processing_time_ms=round(processing_time * 1000, 2)
        )
        
        return final_signal
        
    except Exception as e:
        signals_logger.error(
            "Signal generation failed",
            extra={
                'error_type': type(e).__name__,
                'input_rows': len(df) if df is not None else 0,
                'features': features,
                'model_available': model is not None
            },
            exc_info=True
        )
        return "HOLD"