# TCP Configuration
HOST = "localhost"
PORT = 9999
BUFFER_SIZE = 4096
DELIMITER = "||"
TCP_TIMEOUT = 5.0  # Socket timeout in seconds
MAX_RECONNECT_ATTEMPTS = 3

# Indicator Periods
RSI_PERIOD = 14
EMA_FAST = 12
EMA_SLOW = 26

# Machine Learning Settings
TRAINING_WINDOW = 5000  # Number of bars for training
XGB_N_ESTIMATORS = 100
XGB_MAX_DEPTH = 5
XGB_LEARNING_RATE = 0.1
XGB_RANDOM_STATE = 42
TEST_SIZE = 0.2
PRICE_CHANGE_THRESHOLD = 0.5  # Points for XGBoost target (buy/sell)
RETRAIN_INTERVAL = 100  # Retrain model every 100 bars

# Risk Management
STOP_LOSS_TICKS = 50
PROFIT_TARGET_TICKS = 100
CONTRACT_SIZE = 1

# Historical Data
HISTORICAL_BARS = 5000  # Number of historical bars to process

# Logging Configuration
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIRECTORY = 'logs'  # Directory for log files
LOG_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB per log file
LOG_BACKUP_COUNT = 10  # Number of backup files to retain
LOG_CONSOLE_OUTPUT = True  # Enable console logging
LOG_PERFORMANCE_TRACKING = True  # Enable performance metrics logging