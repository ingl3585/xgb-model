from tcp_connection import start_server
from data_handler import DataHandler
from trading_engine import TradingEngine

class ApplicationCoordinator:
    def __init__(self):
        self.data_handler = DataHandler()
        self.trading_engine = TradingEngine(self.data_handler)
    
    def process_data_chunk(self, chunk: str) -> list[str]:
        """Process incoming data chunk and return list of responses"""
        historical_processed, real_time_bars = self.data_handler.process_data_chunk(chunk)
        responses = []
        
        if historical_processed:
            self.trading_engine.process_historical_data_completed()
        
        for bar_data in real_time_bars:
            signal = self.trading_engine.process_real_time_bar(bar_data)
            responses.append(signal)
        
        return responses
    
    def handle_message(self, message: str) -> str:
        """Handle a processed message and return response"""
        return message

if __name__ == "__main__":
    try:
        coordinator = ApplicationCoordinator()
        start_server(coordinator.process_data_chunk, coordinator.handle_message)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Application terminated")