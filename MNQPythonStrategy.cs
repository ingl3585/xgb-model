#region Using declarations
using System;
using System.Net.Sockets;
using System.Text;
using System.Linq;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class MNQPythonStrategy : Strategy
    {
        private string host = "localhost";  // Must match config.HOST
        private int port = 9999;  // Must match config.PORT
        private TcpClient client;
        private NetworkStream stream;
        private double stopLossTicks = 50;  // Must match config.STOP_LOSS_TICKS
        private double profitTargetTicks = 50;  // Must match config.PROFIT_TARGET_TICKS
        private int contractSize = 1;  // Must match config.CONTRACT_SIZE
        private int historicalBarsToSend = 5000;  // Must match config.HISTORICAL_BARS
        private bool historicalDataSent = false;
        private const string DELIMITER = "||";  // Must match config.DELIMITER

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "MNQ Strategy with Python, VWAP, and ML via TCP";
                Name = "MNQPythonStrategy";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.Infinite;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = 0;
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Gtc;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 20;
            }
            else if (State == State.Realtime)
            {
                // Connect to Python TCP server
                try
                {
                    client = new TcpClient(host, port);
                    stream = client.GetStream();
                    Print("Connected to Python server");
                    SendHistoricalData();
                }
                catch (Exception e)
                {
                    Print($"Failed to connect to server: {e.Message}");
                }
            }
            else if (State == State.Terminated)
            {
                // Clean up TCP connection
                if (stream != null) stream.Close();
                if (client != null) client.Close();
            }
        }

        private void SendHistoricalData()
        {
            if (historicalDataSent || Bars == null || CurrentBar < historicalBarsToSend)
                return;

            try
            {
                Print($"Preparing to send {historicalBarsToSend} historical bars...");
                
                // Collect historical data with validation
                StringBuilder historicalData = new StringBuilder();
                int startIndex = Math.Max(0, CurrentBar - historicalBarsToSend);
                int actualBars = 0;
                
                for (int i = startIndex; i <= CurrentBar; i++)
                {
                    // Validate data before sending
                    if (Times[0][i] != null && Opens[0][i] > 0 && Highs[0][i] > 0 && 
                        Lows[0][i] > 0 && Closes[0][i] > 0 && Volumes[0][i] >= 0)
                    {
                        historicalData.AppendLine($"{Times[0][i].ToString("yyyy-MM-dd HH:mm:ss")},{Opens[0][i]},{Highs[0][i]},{Lows[0][i]},{Closes[0][i]},{Volumes[0][i]}");
                        actualBars++;
                    }
                }
                
                if (actualBars == 0)
                {
                    Print("No valid historical data to send");
                    return;
                }
                
                historicalData.Append(DELIMITER);

                // Send historical data
                byte[] data = Encoding.UTF8.GetBytes(historicalData.ToString());
                stream.Write(data, 0, data.Length);
                stream.Flush();
                Print($"Sent {actualBars} valid historical bars");

                // Wait for confirmation with timeout
                string response = ReceiveResponse();
                
                if (response == "HISTORICAL_PROCESSED")
                {
                    historicalDataSent = true;
                    Print("Historical data successfully processed by Python server");
                }
                else if (response == "ERROR")
                {
                    Print("Python server reported error processing historical data");
                }
                else
                {
                    Print($"Unexpected response from server: {response}");
                }
            }
            catch (Exception e)
            {
                Print($"Error sending historical data: {e.Message}");
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < BarsRequiredToTrade || client == null || !client.Connected || !historicalDataSent)
                return;

            try
            {
                // Send real-time OHLC and volume data with proper formatting
                string dataLine = $"{Time[0].ToString("yyyy-MM-dd HH:mm:ss")},{Open[0]},{High[0]},{Low[0]},{Close[0]},{Volume[0]}";
                byte[] data = Encoding.UTF8.GetBytes(dataLine + "\n");
                stream.Write(data, 0, data.Length);
                stream.Flush(); // Ensure data is sent immediately
                Print($"Sent real-time data: {dataLine}");

                // Receive signal from Python server with timeout
                string signal = ReceiveResponse();
                
                if (string.IsNullOrEmpty(signal))
                {
                    Print("No response received from Python server");
                    return;
                }
                
                Print($"Received signal: {signal}");

                // Execute trades based on signal with additional validation
                if (signal == "BUY" && Position.MarketPosition == MarketPosition.Flat)
                {
                    EnterLong(contractSize, "LongEntry");
                    SetStopLoss("LongEntry", CalculationMode.Ticks, stopLossTicks, false);
                    SetProfitTarget("LongEntry", CalculationMode.Ticks, profitTargetTicks);
                    Print($"Executed BUY order at {Close[0]}");
                }
                else if (signal == "SELL" && Position.MarketPosition == MarketPosition.Flat)
                {
                    EnterShort(contractSize, "ShortEntry");
                    SetStopLoss("ShortEntry", CalculationMode.Ticks, stopLossTicks, false);
                    SetProfitTarget("ShortEntry", CalculationMode.Ticks, profitTargetTicks);
                    Print($"Executed SELL order at {Close[0]}");
                }
                else if (signal == "ERROR")
                {
                    Print("Python server returned ERROR - check data format");
                }
            }
            catch (Exception e)
            {
                Print($"TCP error: {e.Message}");
                ReconnectToServer();
            }
        }
        
        private string ReceiveResponse()
        {
            try
            {
                // Set a read timeout to prevent hanging
                stream.ReadTimeout = 5000; // 5 seconds
                
                byte[] buffer = new byte[1024];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                
                if (bytesRead > 0)
                {
                    string response = Encoding.UTF8.GetString(buffer, 0, bytesRead).Trim();
                    return response;
                }
                
                return null;
            }
            catch (Exception e)
            {
                Print($"Error receiving response: {e.Message}");
                return null;
            }
        }
        
        private void ReconnectToServer()
        {
            try
            {
                Print("Attempting to reconnect to Python server...");
                
                if (stream != null) 
                {
                    stream.Close();
                    stream = null;
                }
                if (client != null) 
                {
                    client.Close();
                    client = null;
                }
                
                // Wait before reconnecting
                System.Threading.Thread.Sleep(1000);
                
                client = new TcpClient(host, port);
                stream = client.GetStream();
                stream.ReadTimeout = 5000;
                stream.WriteTimeout = 5000;
                
                Print("Reconnected to Python server");
                historicalDataSent = false; // Resend historical data on reconnect
                SendHistoricalData();
            }
            catch (Exception e)
            {
                Print($"Reconnection failed: {e.Message}");
            }
        }
    }
}