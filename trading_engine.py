import config
from model import train_model
from signal_generator import generate_signal
from data_handler import DataHandler

class TradingEngine:
    def __init__(self, data_handler: DataHandler):
        self.data_handler = data_handler
        self.model_ready = False
        self.historical_training_complete = False
        self.bar_count = 0
    
    def process_historical_data_completed(self):
        """Called when historical data processing is complete"""
        df = self.data_handler.get_dataframe()
        train_model(df)
        self.model_ready = True
        self.historical_training_complete = True
        print("Model ready and historical training complete")
    
    def process_real_time_bar(self, bar_data: dict) -> str:
        """Process a single real-time bar and return signal"""
        self.bar_count += 1
        df = self.data_handler.get_dataframe()
        
        # Check if we should generate signals
        if (self.data_handler.has_seen_historical_delimiter() and 
            self.model_ready and 
            self.historical_training_complete):
            
            signal = generate_signal(df)
            print(f"Real-time Signal: {signal}")
            
            # Retrain periodically
            if self.bar_count % config.RETRAIN_INTERVAL == 0:
                train_model(df)
                print(f"Model retrained after {self.bar_count} bars")
            
            return signal
        else:
            # Train model if we have enough data, but don't generate signals yet
            if len(df) >= 100 and not self.model_ready:
                train_model(df)
                self.model_ready = True
                if self.data_handler.has_seen_historical_delimiter():
                    self.historical_training_complete = True
                    print("Model ready - signals will start")
                else:
                    print("Model ready - waiting for historical data delimiter")
            
            return "HOLD"
    
    def is_ready_for_signals(self) -> bool:
        """Check if the engine is ready to generate trading signals"""
        return (self.data_handler.has_seen_historical_delimiter() and 
                self.model_ready and 
                self.historical_training_complete)