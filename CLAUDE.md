# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the Application
```bash
python3 main.py
```
This starts the TCP server that listens for connections from NinjaScript trading platform.

### Required Dependencies
```bash
pip install pandas xgboost scikit-learn
```

## Architecture Overview

This is a real-time trading signal generator that uses XGBoost machine learning to predict buy/sell signals for financial markets. The system is designed to integrate with NinjaScript trading platform via TCP connection.

### Core Components

**TCP Server (`tcp_connection.py`)**: Central component that handles client connections, processes both historical and real-time market data, and coordinates model training and signal generation.

**Machine Learning Pipeline**:
- `model.py`: XGBoost classifier for predicting price movements (buy/sell/hold)
- `indicators.py`: Technical indicators (RSI, EMA, VWAP) used as ML features
- `signal_generator.py`: Converts ML predictions into trading signals with additional filters

**Data Processing**:
- `historical_data.py`: Processes historical market data for initial model training

**Configuration (`config.py`)**: Centralized settings for TCP connection, ML parameters, trading rules, and risk management.

### Data Flow

1. Historical data is sent from NinjaScript → processed → used to train initial XGBoost model
2. Real-time bars arrive → technical indicators calculated → model predicts → signals sent back
3. Model retrains periodically (every 100 bars) to adapt to market conditions

### Key Settings

- TCP server runs on localhost:9999
- Model uses 5000 historical bars for training
- Retrains every 100 new bars
- Requires price change threshold of 0.5 points for buy/sell classification