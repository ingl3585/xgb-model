import pandas as pd
import config
from historical_data import process_historical_data

class DataHandler:
    def __init__(self):
        self.df = pd.DataFrame(columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
        self.historical_delimiter_seen = False
        self.data_buffer = ""
    
    def process_data_chunk(self, chunk: str) -> tuple[bool, list[dict]]:
        self.data_buffer += chunk
        historical_processed = False
        real_time_bars = []
        
        # Check for historical data delimiter
        if config.DELIMITER in self.data_buffer:
            parts = self.data_buffer.split(config.DELIMITER, 1)
            historical_data = parts[0]
            self.data_buffer = parts[1] if len(parts) > 1 else ""
            
            self.df = process_historical_data(historical_data)
            self.historical_delimiter_seen = True
            historical_processed = True
            print(f"Received {len(self.df)} bars of historical data")
        
        # Process real-time bars
        while '\n' in self.data_buffer:
            line, self.data_buffer = self.data_buffer.split('\n', 1)
            data = line.strip()
            if not data:
                continue
            
            bar_data = self._parse_bar_data(data)
            if bar_data:
                real_time_bars.append(bar_data)
                self._add_bar_to_dataframe(bar_data)
        
        return historical_processed, real_time_bars
    
    def _parse_bar_data(self, data: str) -> dict:
        """Parse a single bar of real-time data"""
        try:
            parts = data.split(',')
            if len(parts) != 6:
                return None
            
            timestamp, open_str, high_str, low_str, close_str, volume_str = parts
            
            return {
                'Timestamp': pd.to_datetime(timestamp),
                'Open': float(open_str),
                'High': float(high_str),
                'Low': float(low_str),
                'Close': float(close_str),
                'Volume': float(volume_str)
            }
        except (ValueError, IndexError):
            return None
    
    def _add_bar_to_dataframe(self, bar_data: dict):
        """Add a single bar to the DataFrame"""
        new_row = pd.DataFrame([bar_data])
        self.df = pd.concat([self.df, new_row], ignore_index=True) if not self.df.empty else new_row
        
        # Trim DataFrame to training window size
        if len(self.df) > config.TRAINING_WINDOW * 2:
            self.df = self.df.tail(config.TRAINING_WINDOW)
    
    def get_dataframe(self) -> pd.DataFrame:
        """Get the current DataFrame"""
        return self.df.copy()
    
    def has_seen_historical_delimiter(self) -> bool:
        """Check if historical delimiter has been processed"""
        return self.historical_delimiter_seen
    
    def get_data_length(self) -> int:
        """Get the number of bars in the DataFrame"""
        return len(self.df)