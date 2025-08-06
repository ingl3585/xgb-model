import pandas as pd
import config
import socket
import threading
from historical_data import process_historical_data
from model import train_model
from signal_generator import generate_signal

def handle_client(client_socket):
    df = pd.DataFrame(columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    model_ready = False
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
            print(f"Received {len(df)} bars of historical data")
            
            if len(df) >= 100:
                train_model(df)
                model_ready = True
                print("Model ready")
            
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
            
            if model_ready:
                signal = generate_signal(df)
                print(f"Signal: {signal}")
                send_response(client_socket, signal)
            else:
                if len(df) >= 100:
                    train_model(df)
                    model_ready = True
                    print("Model ready")
                send_response(client_socket, "HOLD")
            
            # Retrain periodically
            if model_ready and bar_count % config.RETRAIN_INTERVAL == 0:
                train_model(df)

def send_response(client_socket, message):
    client_socket.send(f"{message}\n".encode('utf-8'))

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.HOST, config.PORT))
    server_socket.listen(1)
    
    print(f"Server listening on {config.HOST}:{config.PORT}")
    
    while True:
        client_socket, addr = server_socket.accept()
        print(f"Client connected: {addr}")
        
        client_thread = threading.Thread(target=handle_client, args=(client_socket,))
        client_thread.daemon = True
        client_thread.start()