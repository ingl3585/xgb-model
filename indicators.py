import pandas as pd
import config

def calculate_rsi(df, period=None):
    period = period or config.RSI_PERIOD
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(alpha=1/period).mean()
    avg_loss = loss.ewm(alpha=1/period).mean()
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_ema(df, period, col='close'):
    return df[col].ewm(span=period).mean()

def calculate_macd(df):
    ema12 = calculate_ema(df, config.MACD_FAST)
    ema26 = calculate_ema(df, config.MACD_SLOW)
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=config.MACD_SIGNAL).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(df, period=None, std_dev=None):
    period = period or config.BOLL_PERIOD
    std_dev = std_dev or config.BOLL_STD
    
    sma = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return sma, upper, lower

def calculate_atr(df, period=None):
    period = period or config.ATR_PERIOD
    
    h_l = df['high'] - df['low']
    h_c = abs(df['high'] - df['close'].shift())
    l_c = abs(df['low'] - df['close'].shift())
    
    tr = pd.concat([h_l, h_c, l_c], axis=1).max(axis=1)
    return tr.ewm(span=period).mean()

def calculate_vwap(df):
    return (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()