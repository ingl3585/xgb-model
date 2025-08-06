from tcp_connection import start_server

if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Application terminated")