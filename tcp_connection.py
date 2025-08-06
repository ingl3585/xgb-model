import config
import socket
import threading
import signal

# Global shutdown flag
shutdown_flag = False

def signal_handler(signum, frame):
    global shutdown_flag
    print("\nShutting down server...")
    shutdown_flag = True

def handle_client(client_socket, data_processor, message_handler):
    while True:
        try:
            chunk = client_socket.recv(config.BUFFER_SIZE).decode('utf-8')
            if not chunk:
                break
            
            # Process the data chunk
            responses = data_processor(chunk)
            
            # Handle each response
            for response in responses:
                message = message_handler(response)
                if message:
                    send_response(client_socket, message)
                    
        except Exception as e:
            print(f"Error handling client: {e}")
            break
    
    client_socket.close()

def send_response(client_socket, message):
    client_socket.send(f"{message}\n".encode('utf-8'))

def start_server(data_processor, message_handler):
    global shutdown_flag
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.HOST, config.PORT))
    server_socket.listen(1)
    server_socket.settimeout(1.0)  # Set timeout for non-blocking accept
    
    print(f"Waiting on NinjaTrader...")
    
    try:
        while not shutdown_flag:
            try:
                client_socket, addr = server_socket.accept()
                print(f"Client connected: {addr}")
                
                client_thread = threading.Thread(
                    target=handle_client, 
                    args=(client_socket, data_processor, message_handler)
                )
                client_thread.daemon = True
                client_thread.start()
            except socket.timeout:
                continue  # Check shutdown flag again
    finally:
        server_socket.close()
        print("Server socket closed")