import config

# Calculate RSI
def calculate_rsi(data, period=config.RSI_PERIOD):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# Calculate EMA
def calculate_ema(data, period):
    return data['Close'].ewm(span=period, adjust=False).mean()

# Calculate VWAP
def calculate_vwap(data):
    typical_price = (data['High'] + data['Low'] + data['Close']) / 3
    volume_price = typical_price * data['Volume']
    cumulative_volume_price = volume_price.cumsum()
    cumulative_volume = data['Volume'].cumsum()
    return cumulative_volume_price / cumulative_volume