import pandas as pd

def process_historical_data(data_str):
    lines = [line.strip() for line in data_str.split('\n') if line.strip()]
    
    if not lines:
        raise ValueError("No valid data lines found")
    
    parsed_data = []
    for line in lines:
        parts = line.split(',')
        if len(parts) == 6:
            parsed_data.append(parts)
    
    if not parsed_data:
        raise ValueError("No valid data could be parsed")
    
    df = pd.DataFrame(parsed_data, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
    
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    numeric_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    df[numeric_columns] = df[numeric_columns].astype(float)

    print(f'Historical Data: {df.head()}')
    
    return df