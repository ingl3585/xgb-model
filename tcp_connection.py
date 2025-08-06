import pandas as pd
import config
import socket
import threading
import signal
import sys
from historical_data import process_historical_data
from model import train_model
from signal_generator import generate_signal

# Global shutdown flag
shutdown_flag = False

def signal_handler(signum, frame):
    global shutdown_flag
    print("\nShutting down server...")
    shutdown_flag = True

def handle_client(client_socket):
    df = pd.DataFrame(columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    model_ready = False
    historical_training_complete = False
    historical_delimiter_seen = False
    data_buffer = ""
    bar_count = 0
    
    while True:
        chunk = client_socket.recv(config.BUFFER_SIZE).decode('utf-8')
        if not chunk:
            break
        
        data_buffer += chunk
        
        # Historical data
        if config.DELIMITER in data_buffer:
            parts = data_buffer.split(config.DELIMITER, 1)
            historical_data = parts[0]
            data_buffer = parts[1] if len(parts) > 1 else ""
            
            df = process_historical_data(historical_data)
            historical_delimiter_seen = True
            print(f"Received {len(df)} bars of historical data")
            
            if len(df) >= 100:
                train_model(df)
                model_ready = True
                historical_training_complete = True
                print("Model ready and historical training complete - signals will start")
            else:
                # Even if historical data is small, we can start signals if model was already trained
                if model_ready:
                    historical_training_complete = True
                    print("Historical data received - signals will start on next bar")
            
            continue
        
        # Real-time bars
        while '\n' in data_buffer:
            line, data_buffer = data_buffer.split('\n', 1)
            data = line.strip()
            if not data:
                continue
            
            parts = data.split(',')
            timestamp, open_str, high_str, low_str, close_str, volume_str = parts
            
            new_row = pd.DataFrame({
                'Timestamp': [pd.to_datetime(timestamp)],
                'Open': [float(open_str)],
                'High': [float(high_str)],
                'Low': [float(low_str)],
                'Close': [float(close_str)],
                'Volume': [float(volume_str)]
            })
            
            df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
            
            if len(df) > config.TRAINING_WINDOW * 2:
                df = df.tail(config.TRAINING_WINDOW)
            
            bar_count += 1
            
            # Only generate signals after we've seen the historical delimiter
            if historical_delimiter_seen and model_ready and historical_training_complete:
                signal = generate_signal(df)
                print(f"Real-time Signal: {signal}")
                send_response(client_socket, signal)
            else:
                # Train model if we have enough data, but don't generate signals yet
                if len(df) >= 100 and not model_ready:
                    train_model(df)
                    model_ready = True
                    if historical_delimiter_seen:
                        historical_training_complete = True
                        print("Model ready - signals will start")
                    else:
                        print("Model ready - waiting for historical data delimiter")
                send_response(client_socket, "HOLD")
            
            # Retrain periodically
            if model_ready and bar_count % config.RETRAIN_INTERVAL == 0:
                train_model(df)

def send_response(client_socket, message):
    client_socket.send(f"{message}\n".encode('utf-8'))

def start_server():
    global shutdown_flag
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.HOST, config.PORT))
    server_socket.listen(1)
    server_socket.settimeout(1.0)  # Set timeout for non-blocking accept
    
    print(f"Server listening on {config.HOST}:{config.PORT}")
    print("Press Ctrl+C to shutdown")
    
    try:
        while not shutdown_flag:
            try:
                client_socket, addr = server_socket.accept()
                print(f"Client connected: {addr}")
                
                client_thread = threading.Thread(target=handle_client, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue  # Check shutdown flag again
    finally:
        server_socket.close()
        print("Server socket closed")