import pandas as pd
from logging_config import get_trading_logger, log_performance, log_trading_event
import time

# Initialize data logger
data_logger = get_trading_logger('data')

# Process historical data
@log_performance(data_logger, "Historical data processing")
def process_historical_data(data_str):
    data_logger.info(
        "Starting historical data processing",
        extra={
            'raw_data_length': len(data_str),
            'raw_data_preview': data_str[:200] if len(data_str) > 200 else data_str
        }
    )
    
    try:
        # Split data into lines and filter empty ones
        lines = [line.strip() for line in data_str.split('\n') if line.strip()]
        
        data_logger.debug(
            "Data parsing initiated",
            extra={
                'total_lines': len(lines),
                'sample_line': lines[0] if lines else 'No data lines found'
            }
        )
        
        if not lines:
            data_logger.error("No valid data lines found in historical data")
            raise ValueError("No valid data lines found in historical data")
        
        # Parse CSV data into DataFrame
        parsed_data = []
        invalid_lines = []
        
        for i, line in enumerate(lines):
            try:
                parts = line.split(',')
                if len(parts) != 6:
                    invalid_lines.append({'line_number': i + 1, 'parts_count': len(parts), 'line': line[:100]})
                    continue
                parsed_data.append(parts)
            except Exception as e:
                invalid_lines.append({'line_number': i + 1, 'error': str(e), 'line': line[:100]})
        
        if invalid_lines:
            data_logger.warning(
                "Invalid lines detected during parsing",
                extra={
                    'invalid_count': len(invalid_lines),
                    'total_lines': len(lines),
                    'invalid_lines': invalid_lines[:5]  # Log first 5 invalid lines
                }
            )
        
        if not parsed_data:
            data_logger.error("No valid data could be parsed from historical data")
            raise ValueError("No valid data could be parsed from historical data")
        
        # Create DataFrame
        df = pd.DataFrame(parsed_data, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        # Data type conversion with error handling
        conversion_start = time.time()
        
        try:
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        except Exception as e:
            data_logger.error(
                "Timestamp conversion failed",
                extra={'error': str(e), 'sample_timestamps': df['Timestamp'].head().tolist()}
            )
            raise
        
        try:
            numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            df[numeric_columns] = df[numeric_columns].astype(float)
        except Exception as e:
            data_logger.error(
                "Numeric conversion failed",
                extra={'error': str(e), 'sample_data': df[numeric_columns].head().to_dict()}
            )
            raise
        
        conversion_time = time.time() - conversion_start
        
        # Data validation
        validation_issues = []
        
        # Check for null values
        null_counts = df.isnull().sum()
        if null_counts.any():
            validation_issues.append(f"Null values found: {null_counts.to_dict()}")
        
        # Check OHLC relationships
        invalid_ohlc = df[(df['Low'] > df['High']) | 
                         (df['Open'] < df['Low']) | (df['Open'] > df['High']) |
                         (df['Close'] < df['Low']) | (df['Close'] > df['High'])]
        
        if not invalid_ohlc.empty:
            validation_issues.append(f"Invalid OHLC relationships in {len(invalid_ohlc)} rows")
        
        # Check for negative volumes
        negative_volume = df[df['Volume'] < 0]
        if not negative_volume.empty:
            validation_issues.append(f"Negative volume in {len(negative_volume)} rows")
        
        if validation_issues:
            data_logger.warning(
                "Data validation issues detected",
                extra={
                    'issues': validation_issues,
                    'total_rows': len(df)
                }
            )
        
        # Log successful processing
        log_trading_event(
            data_logger,
            'historical_data_processed',
            total_rows=len(df),
            valid_rows=len(df) - len(invalid_lines),
            invalid_lines=len(invalid_lines),
            conversion_time_ms=round(conversion_time * 1000, 2),
            date_range_start=df['Timestamp'].min().isoformat() if not df.empty else None,
            date_range_end=df['Timestamp'].max().isoformat() if not df.empty else None,
            validation_issues_count=len(validation_issues)
        )
        
        # Log sample data for debugging (first few rows)
        data_logger.debug(
            "Historical data sample",
            extra={
                'sample_data': df.head().to_dict('records'),
                'data_shape': df.shape,
                'columns': list(df.columns)
            }
        )
        
        return df
        
    except Exception as e:
        data_logger.error(
            "Historical data processing failed",
            extra={
                'error_type': type(e).__name__,
                'raw_data_length': len(data_str),
                'error_details': str(e)
            },
            exc_info=True
        )
        raise