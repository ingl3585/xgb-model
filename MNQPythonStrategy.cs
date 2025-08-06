#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using System.Net.Sockets;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class MNQPythonStrategy : Strategy
    {
        private TcpClient client;
        private NetworkStream stream;
        private bool historicalDataSent = false;
        
        // Connection settings
        private string host = "localhost";
        private int port = 9999;
        
        // Trading settings
        private int contractSize = 1;
        private int stopLossTicks = 50;
        private int profitTargetTicks = 100;
        private int historicalBarsToSend = 240;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "MNQPythonStrategy";
                BarsRequiredToTrade = 1;
            }
            else if (State == State.DataLoaded)
            {
                ConnectToServer();
            }
            else if (State == State.Realtime)
            {
                if (!historicalDataSent && client != null && client.Connected)
                {
                    SendHistoricalData();
                }
            }
            else if (State == State.Terminated)
            {
                DisconnectFromServer();
            }
        }

        private void ConnectToServer()
        {
            try
            {
                client = new TcpClient(host, port);
                stream = client.GetStream();
                stream.ReadTimeout = 30000;
                stream.WriteTimeout = 30000;
                Print("Connected to Python server");
            }
            catch (Exception e)
            {
                Print($"Connection failed: {e.Message}");
            }
        }

        private void SendHistoricalData()
        {
            if (historicalDataSent || Bars == null || client == null || !client.Connected)
                return;

            try
            {
                var data = new StringBuilder();
                int barsToSend = Math.Min(Bars.Count, historicalBarsToSend);
                
                for (int i = Math.Min(barsToSend - 1, CurrentBar); i >= 0; i--)
                {
                    data.AppendLine($"{Time[i]:yyyy-MM-dd HH:mm:ss},{Open[i]:F2},{High[i]:F2},{Low[i]:F2},{Close[i]:F2},{Volume[i]}");
                }
                
                string message = data.ToString() + "||";
                byte[] buffer = Encoding.UTF8.GetBytes(message);
                stream.Write(buffer, 0, buffer.Length);
                stream.Flush();

                historicalDataSent = true;
                Print($"Historical data sent: {barsToSend} bars");
            }
            catch (Exception e)
            {
                Print($"Error sending historical data: {e.Message}");
            }
        }

        protected override void OnBarUpdate()
        {
            if (State != State.Realtime || CurrentBar < BarsRequiredToTrade || client == null || !client.Connected || !historicalDataSent)
                return;

            try
            {
                // Send real-time bar data
                string barData = $"{Time[0]:yyyy-MM-dd HH:mm:ss},{Open[0]:F2},{High[0]:F2},{Low[0]:F2},{Close[0]:F2},{Volume[0]}";
                byte[] data = Encoding.UTF8.GetBytes(barData + "\n");
                stream.Write(data, 0, data.Length);
                stream.Flush();

                // Get trading signal
                string signal = ReadResponse();
                
                // Execute trades based on signal
                if (!string.IsNullOrEmpty(signal))
                {
                    if (signal == "BUY" && Position.MarketPosition == MarketPosition.Flat)
                    {
                        EnterLong(contractSize, "Long");
                        SetStopLoss("Long", CalculationMode.Ticks, stopLossTicks, false);
                        SetProfitTarget("Long", CalculationMode.Ticks, profitTargetTicks);
                        Print($"BUY signal at {Close[0]:F2}");
                    }
                    else if (signal == "SELL" && Position.MarketPosition == MarketPosition.Flat)
                    {
                        EnterShort(contractSize, "Short");
                        SetStopLoss("Short", CalculationMode.Ticks, stopLossTicks, false);
                        SetProfitTarget("Short", CalculationMode.Ticks, profitTargetTicks);
                        Print($"SELL signal at {Close[0]:F2}");
                    }
                    // HOLD = no action
                }
            }
            catch (Exception e)
            {
                Print($"Error: {e.Message}");
            }
        }

        private string ReadResponse()
        {
            try
            {
                byte[] buffer = new byte[1024];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                return Encoding.UTF8.GetString(buffer, 0, bytesRead).Trim();
            }
            catch (Exception e)
            {
                Print($"Error: {e.Message}");
                return "HOLD";
            }
        }

        private void DisconnectFromServer()
        {
            try
            {
                stream?.Close();
                client?.Close();
            }
            catch { }
        }
    }
}