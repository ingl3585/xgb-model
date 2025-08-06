import pandas as pd
import config
import socket
import threading
from historical_data import process_historical_data
from model import train_model
from signal_generator import generate_signal

def handle_client(client_socket):
    df = pd.DataFrame(columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    historical_processing_complete = False
    just_processed_historical = False
    data_buffer = ""
    
    while True:
        try:
            # Receive data and add to buffer
            chunk = client_socket.recv(config.BUFFER_SIZE).decode('utf-8')
            if not chunk:
                break
            
            data_buffer += chunk
            
            # Check for historical data first (before line processing)
            if config.DELIMITER in data_buffer:
                print(f"Found historical data delimiter in buffer")
                historical_data = data_buffer.split(config.DELIMITER)[0]
                data_buffer = data_buffer.split(config.DELIMITER, 1)[1] if config.DELIMITER in data_buffer else ""
                
                print(f"Received historical data: {len(historical_data)} bytes")
                try:
                    print(f"Processing {len(historical_data.splitlines())} lines of historical data...")
                    df = process_historical_data(historical_data)
                    print(f"Processed {len(df)} bars, training model...")
                    
                    # Check if we have enough data for training
                    if len(df) < 10:  # Reduced minimum from 100 to 10 for small historical datasets
                        print(f"Not enough historical data for training (got {len(df)} bars, need at least 10)")
                        send_response(client_socket, "HISTORICAL_ERROR")
                        continue
                    elif len(df) < 100:
                        print(f"Small historical dataset (got {len(df)} bars), will supplement with real-time data")
                        
                    print("Starting model training...")
                    train_result = train_model(df)
                    print(f"Model training result: {train_result}")
                    historical_processing_complete = True
                    just_processed_historical = True
                    print("Model training complete, sending confirmation")
                    response_msg = "HISTORICAL_PROCESSED"
                    print(f"Sending response: {response_msg}")
                    send_response(client_socket, response_msg)
                    print("Response sent successfully")
                    
                    # Clear any remaining buffer to avoid immediate real-time processing
                    data_buffer = ""
                    continue
                    
                except Exception as e:
                    print(f"Error processing historical data: {e}")
                    import traceback
                    traceback.print_exc()
                    send_response(client_socket, "HISTORICAL_ERROR")
                    continue
            
            # Process complete lines (ended with newline) for real-time data
            while '\n' in data_buffer:
                line, data_buffer = data_buffer.split('\n', 1)
                data = line.strip()
                if not data:
                    continue
                
                # Skip historical data processing here since handled above
                if config.DELIMITER in data:
                    continue
                
                # Real-time data - single bar per line
                parts = data.split(',')
                
                if len(parts) == 6:
                    timestamp, open_str, high_str, low_str, close_str, volume_str = parts
                elif len(parts) == 5:
                    timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
                    open_str, high_str, low_str, close_str, volume_str = parts
                else:
                    print(f"Invalid bar format: expected 5 or 6 parts, got {len(parts)} in: {data}")
                    send_response(client_socket, "ERROR")
                    continue
                
                try:
                    open_price, high, low, close, volume = map(float, [open_str, high_str, low_str, close_str, volume_str])
                    timestamp_dt = pd.to_datetime(timestamp)
                    
                    new_row = pd.DataFrame({
                        'Timestamp': [timestamp_dt],
                        'Open': [open_price],
                        'High': [high],
                        'Low': [low],
                        'Close': [close],
                        'Volume': [volume]
                    })
                    
                    if df.empty:
                        df = new_row.copy()
                    else:
                        df = pd.concat([df, new_row], ignore_index=True)
                    
                    # Keep only recent data
                    if len(df) > config.TRAINING_WINDOW * 2:
                        df = df.tail(config.TRAINING_WINDOW).copy()
                    
                    print(f"Added 1 bar, total bars: {len(df)}")
                    
                    # Skip sending response if we just processed historical data
                    if just_processed_historical:
                        print("Skipping real-time response - just processed historical data")
                        just_processed_historical = False
                        continue
                    
                    # Generate signal if ready (only for the last bar)
                    if historical_processing_complete and not df.empty:
                        signal = generate_signal(df)
                        send_response(client_socket, signal)
                    else:
                        send_response(client_socket, "LEARNING")
                    
                    # Retrain periodically
                    if len(df) % config.RETRAIN_INTERVAL == 0 and len(df) >= 100:
                        print("Retraining model...")
                        train_model(df)
                        
                except ValueError as e:
                    print(f"Error parsing bar data: {e} in: {data}")
                    send_response(client_socket, "ERROR")
                    continue
                
        except Exception as e:
            print(f"Connection error: {e}")
            send_response(client_socket, "ERROR")
            break
    
    client_socket.close()

def send_response(client_socket, message):
    try:
        response = f"{message}\n"
        print(f"DEBUG: Sending response '{message}' to client")
        client_socket.send(response.encode('utf-8'))
        client_socket.flush() if hasattr(client_socket, 'flush') else None
        print(f"DEBUG: Response '{message}' sent successfully")
    except Exception as e:
        print(f"DEBUG: Error sending response '{message}': {e}")

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.HOST, config.PORT))
    server_socket.listen(1)
    
    print(f"Server listening on {config.HOST}:{config.PORT}")
    
    while True:
        try:
            client_socket, addr = server_socket.accept()
            print(f"Client connected: {addr}")
            
            client_thread = threading.Thread(target=handle_client, args=(client_socket,))
            client_thread.daemon = True
            client_thread.start()
            
        except KeyboardInterrupt:
            break
    
    server_socket.close()