# Gold_Trading_Indicator
Code that accesses Yahoo Finance to access multiple indicators, and output a decision on whether to go long, short or wait for a trade for gold futures. Afterwards, it will send the consolidated information to the relevant telegram chats of different users.

Strategy Overview
Symbol: Gold Futures (GC=F)

Timeframe: Daily

Indicators:
- RSI (14)
- EMA (9, 21)
- MACD (12, 26, 9)

Entry Rules:
Signal Condition
- BUY	EMA9 crosses above EMA21 AND RSI < 30
- SELL	EMA9 crosses below EMA21 AND RSI > 70
- HOLD	No crossover signal

Risk Management
- Position Size: 3% of capital per trade

Max Drawdown: 20%

Prerequisites
- Python 3.7+
- Git installed
- Internet connection (for fetching price data)
