import pandas as pd
import config
import time
import socket
import threading
import signal
import sys
from historical_data import process_historical_data
from model import prepare_features, train_model
from signal_generator import generate_signals
from logging_config import (
    setup_trading_logging, get_trading_logger, 
    log_performance, log_trading_event
)

# Initialize logging infrastructure
setup_trading_logging(
    log_level=config.LOG_LEVEL,
    log_directory=config.LOG_DIRECTORY,
    console_output=config.LOG_CONSOLE_OUTPUT
)

# Get loggers for different components
tcp_logger = get_trading_logger('tcp')
system_logger = get_trading_logger('system')
data_logger = get_trading_logger('data')

# Global variables for clean shutdown
server_socket = None
client_threads = []
shutdown_event = threading.Event()

# Handle client connection with proper TCP message framing
def handle_client(client_socket):
    df = pd.DataFrame(columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    model = None
    features = None
    model_lock = threading.Lock()
    buffer = ""
    historical_processing_complete = False  # Flag to track if historical data is processed
    
    def read_message():
        """Read complete messages from TCP stream, handling fragmentation"""
        nonlocal buffer
        while not shutdown_event.is_set():
            try:
                # Set socket timeout for responsive shutdown
                client_socket.settimeout(1.0)
                chunk = client_socket.recv(config.BUFFER_SIZE).decode('utf-8')
                if not chunk:
                    tcp_logger.debug("Client disconnected - no data received")
                    return None
                buffer += chunk
                
                # Process complete messages (terminated by newline)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        yield line.strip()
            except socket.timeout:
                # Check for shutdown signal
                continue
            except Exception as e:
                if not shutdown_event.is_set():
                    tcp_logger.error(
                        "Error reading TCP message",
                        extra={'error_type': type(e).__name__, 'client_thread': threading.current_thread().name},
                        exc_info=True
                    )
                return None
    
    try:
        for message in read_message():
            if not message or shutdown_event.is_set():
                break
                
            tcp_logger.debug(
                "Received TCP message",
                extra={
                    'message_length': len(message),
                    'message_preview': message[:100] if len(message) > 100 else message,
                    'client_thread': threading.current_thread().name
                }
            )
            
            # Check if data is historical or real-time
            if config.DELIMITER in message:
                # Historical data - process and train initial model
                historical_data = message.split(config.DELIMITER)[0]
                try:
                    start_time = time.time()
                    data_logger.info(
                        "Starting historical data processing",
                        extra={
                            'data_length': len(historical_data),
                            'client_thread': threading.current_thread().name
                        }
                    )
                    
                    df = process_historical_data(historical_data)
                    df, features = prepare_features(df)
                    
                    with model_lock:
                        model = train_model(df, features)
                    
                    historical_processing_complete = True
                    processing_time = time.time() - start_time
                    
                    log_trading_event(
                        data_logger,
                        'historical_processing_complete',
                        bars_processed=len(df),
                        features_count=len(features),
                        processing_time_seconds=round(processing_time, 3)
                    )
                    
                    send_response(client_socket, "HISTORICAL_PROCESSED")
                    
                except Exception as e:
                    data_logger.error(
                        "Failed to process historical data",
                        extra={
                            'error_type': type(e).__name__,
                            'client_thread': threading.current_thread().name
                        },
                        exc_info=True
                    )
                    historical_processing_complete = False
                    send_response(client_socket, "HISTORICAL_ERROR")
                continue
            
            # Real-time data - handle various formats
            try:
                parts = message.split(',')
                if len(parts) < 5:
                    data_logger.warning(
                        "Incomplete market data received",
                        extra={
                            'expected_fields': 5,
                            'received_fields': len(parts),
                            'data_parts': parts,
                            'client_thread': threading.current_thread().name
                        }
                    )
                    send_response(client_socket, "ERROR")
                    continue
                
                if len(parts) == 5:
                    # Missing timestamp, use current time
                    timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
                    open_str, high_str, low_str, close_str, volume_str = parts
                elif len(parts) == 6:
                    # Complete data with timestamp
                    timestamp, open_str, high_str, low_str, close_str, volume_str = parts
                else:
                    data_logger.warning(
                        "Unexpected market data format",
                        extra={
                            'received_fields': len(parts),
                            'data_parts': parts[:5],  # Log first 5 parts for debugging
                            'client_thread': threading.current_thread().name
                        }
                    )
                    send_response(client_socket, "INVALID_DATA")
                    continue
                
                # Comprehensive input validation
                try:
                    open_price, high, low, close, volume = map(float, [open_str, high_str, low_str, close_str, volume_str])
                    
                    # Validate price relationships (OHLC logic)
                    if not (0 < low <= high and low <= open_price <= high and low <= close <= high):
                        raise ValueError(f"Invalid OHLC relationships: O={open_price}, H={high}, L={low}, C={close}")
                    
                    # Validate reasonable ranges (example for futures - adjust as needed)
                    if any(price <= 0 or price > 100000 for price in [open_price, high, low, close]):
                        raise ValueError(f"Price out of reasonable range")
                        
                    if volume < 0:
                        raise ValueError(f"Invalid volume: {volume}")
                        
                    # Validate timestamp
                    timestamp_dt = pd.to_datetime(timestamp)
                    
                except (ValueError, TypeError) as e:
                    data_logger.error(
                        "Market data validation failed",
                        extra={
                            'validation_error': str(e),
                            'raw_data': parts,
                            'client_thread': threading.current_thread().name
                        }
                    )
                    send_response(client_socket, "INVALID_DATA")
                    continue
                
                new_row = pd.DataFrame({
                    'Timestamp': [timestamp_dt],
                    'Open': [open_price],
                    'High': [high],
                    'Low': [low],
                    'Close': [close],
                    'Volume': [volume]
                })
                df = pd.concat([df, new_row], ignore_index=True)
                
                # Prevent memory leaks by limiting DataFrame size
                if len(df) > config.TRAINING_WINDOW * 2:
                    original_size = len(df)
                    df = df.tail(config.TRAINING_WINDOW).copy()
                    data_logger.info(
                        "DataFrame memory management - trimmed data",
                        extra={
                            'original_size': original_size,
                            'trimmed_size': len(df),
                            'training_window': config.TRAINING_WINDOW,
                            'client_thread': threading.current_thread().name
                        }
                    )
                
                # Generate signal only if historical processing is complete
                with model_lock:
                    if historical_processing_complete and model is not None:
                        signal = generate_signals(df, model, features)
                        # Send signal back to NinjaScript
                        send_response(client_socket, signal)
                        
                        log_trading_event(
                            tcp_logger,
                            'trading_signal_sent',
                            signal=signal,
                            current_price=df['Close'].iloc[-1] if not df.empty else None,
                            bars_processed=len(df),
                            client_thread=threading.current_thread().name
                        )
                    else:
                        # During historical processing, acknowledge data receipt without signal
                        send_response(client_socket, "LEARNING")
                        if not historical_processing_complete:
                            data_logger.debug(
                                "Data received during historical processing phase",
                                extra={
                                    'bars_received': len(df),
                                    'client_thread': threading.current_thread().name
                                }
                            )
                        else:
                            tcp_logger.warning(
                                "Model unavailable - sending LEARNING status",
                                extra={
                                    'model_status': 'None' if model is None else 'Available',
                                    'client_thread': threading.current_thread().name
                                }
                            )
                
                # Retrain model periodically
                if len(df) % config.RETRAIN_INTERVAL == 0:
                    start_time = time.time()
                    data_logger.info(
                        "Starting periodic model retraining",
                        extra={
                            'total_bars': len(df),
                            'retrain_interval': config.RETRAIN_INTERVAL,
                            'client_thread': threading.current_thread().name
                        }
                    )
                    
                    with model_lock:
                        try:
                            model = train_model(df, features)
                            retrain_time = time.time() - start_time
                            
                            log_trading_event(
                                data_logger,
                                'model_retrained',
                                bars_used=len(df),
                                features_count=len(features),
                                retrain_time_seconds=round(retrain_time, 3)
                            )
                            
                        except Exception as e:
                            data_logger.error(
                                "Model retraining failed",
                                extra={
                                    'error_type': type(e).__name__,
                                    'bars_attempted': len(df),
                                    'client_thread': threading.current_thread().name
                                },
                                exc_info=True
                            )
                            
            except ValueError as e:
                data_logger.error(
                    "Data conversion error",
                    extra={
                        'message': message,
                        'error_type': type(e).__name__,
                        'client_thread': threading.current_thread().name
                    },
                    exc_info=True
                )
                send_response(client_socket, "ERROR")
            except Exception as e:
                data_logger.error(
                    "Real-time data processing error",
                    extra={
                        'message': message,
                        'error_type': type(e).__name__,
                        'client_thread': threading.current_thread().name
                    },
                    exc_info=True
                )
                send_response(client_socket, "ERROR")
                
    except Exception as e:
        if not shutdown_event.is_set():
            tcp_logger.error(
                "Client connection error",
                extra={
                    'error_type': type(e).__name__,
                    'client_thread': threading.current_thread().name
                },
                exc_info=True
            )
    finally:
        try:
            client_socket.close()
        except:
            pass
        tcp_logger.info(
            "Client connection closed",
            extra={'client_thread': threading.current_thread().name}
        )

def send_response(client_socket, message):
    """Send response with proper message framing"""
    try:
        response = f"{message}\n"
        client_socket.send(response.encode('utf-8'))
        tcp_logger.debug(
            "TCP response sent",
            extra={
                'response': message,
                'response_length': len(response),
                'client_thread': threading.current_thread().name
            }
        )
    except Exception as e:
        tcp_logger.error(
            "Failed to send TCP response",
            extra={
                'response': message,
                'error_type': type(e).__name__,
                'client_thread': threading.current_thread().name
            },
            exc_info=True
        )

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    system_logger.info(
        "Shutdown signal received",
        extra={
            'signal': signum,
            'active_client_threads': len([t for t in client_threads if t.is_alive()])
        }
    )
    
    shutdown_event.set()
    
    # Close server socket
    global server_socket
    if server_socket:
        try:
            server_socket.close()
            system_logger.info("Server socket closed successfully")
        except Exception as e:
            system_logger.error(
                "Error closing server socket",
                extra={'error_type': type(e).__name__},
                exc_info=True
            )
    
    # Wait for client threads to finish
    system_logger.info(
        "Waiting for client connections to close",
        extra={'active_threads': len(client_threads)}
    )
    
    for thread in client_threads[:]:
        if thread.is_alive():
            thread.join(timeout=2.0)
    
    log_trading_event(
        system_logger,
        'system_shutdown_complete',
        total_client_connections=len(client_threads)
    )
    
    sys.exit(0)

# TCP server
def start_server():
    global server_socket
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.HOST, config.PORT))
    server_socket.listen(1)
    
    log_trading_event(
        system_logger,
        'server_startup',
        host=config.HOST,
        port=config.PORT,
        buffer_size=config.BUFFER_SIZE,
        training_window=config.TRAINING_WINDOW,
        retrain_interval=config.RETRAIN_INTERVAL
    )
    
    try:
        while not shutdown_event.is_set():
            try:
                # Set timeout for responsive shutdown
                server_socket.settimeout(1.0)
                client_socket, addr = server_socket.accept()
                
                log_trading_event(
                    tcp_logger,
                    'client_connected',
                    client_address=addr[0],
                    client_port=addr[1],
                    total_active_connections=len([t for t in client_threads if t.is_alive()]) + 1
                )
                
                client_thread = threading.Thread(target=handle_client, args=(client_socket,))
                client_thread.daemon = True  # Daemon threads will exit when main exits
                client_threads.append(client_thread)
                client_thread.start()
                
            except socket.timeout:
                # Check for shutdown signal
                continue
            except Exception as e:
                if not shutdown_event.is_set():
                    system_logger.error(
                        "TCP server error",
                        extra={'error_type': type(e).__name__},
                        exc_info=True
                    )
                    time.sleep(5)
    except KeyboardInterrupt:
        # This shouldn't happen since we handle SIGINT, but just in case
        signal_handler(signal.SIGINT, None)