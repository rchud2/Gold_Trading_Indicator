import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import requests

# CONFIG
SYMBOL = "GC=F"  #gold futures, can be changed
DATA_PERIOD = "1y"
RSI_PERIOD = 14
EMA_FAST = 9
EMA_SLOW = 21
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# rules
POSITION_SIZE_PCT = 0.03
MAX_DRAWDOWN = 0.20 


def fetch_data(symbol: str, period: str = "1y") -> pd.DataFrame:
    #taking the data from yfinance
    print(f"FEtching data for {symbol}...")
    df = yf.download(symbol, period=period, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {symbol}")
    print(f"   Loaded {len(df)} days of data")
    
    # idk what this does but it works
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    return df


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = (-delta).where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    #calculate ema
    return prices.ewm(span=period, adjust=False).mean()


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    #Calculate MACD, signal line and histogram
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    #MAke buy/sell signals based on strategy
    
    close = df['Close']
    # Calculate indicators
    df['RSI'] = calculate_rsi(close, RSI_PERIOD)
    df['EMA9'] = calculate_ema(close, EMA_FAST)
    df['EMA21'] = calculate_ema(close, EMA_SLOW)
    df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = calculate_macd(close)
    
    # for EMA crossover
    df['EMA_Cross'] = np.where(df['EMA9'] > df['EMA21'], 1, -1)
    df['EMA_Cross_Change'] = df['EMA_Cross'].diff()
    
    # buy signal: EMA9 crosses above EMA21 AND RSI < 30
    df['Buy_Signal'] = (df['EMA_Cross_Change'] > 0) & (df['RSI'] < 30)
    
    # sell signal: EMA9 crosses below EMA21 AND RSI > 70
    df['Sell_Signal'] = (df['EMA_Cross_Change'] < 0) & (df['RSI'] > 70)

    print("   RSI, EMA9, EMA21, MACD calculated")
    return df


def get_latest_signal(df: pd.DataFrame) -> dict:
    latest = df.iloc[-1]
    
    close = latest['Close']
    if hasattr(close, 'item'):
        close = close.item()
    
    signal = {
        'date': str(latest.name.date()),
        'close': close,
        'rsi': latest['RSI'],
        'ema9': latest['EMA9'],
        'ema21': latest['EMA21'],
        'macd': latest['MACD'],
        'macd_signal': latest['MACD_Signal'],
        'action': 'HOLD',
        'reason': ''
    }
    
    # Check buy signal
    if latest['Buy_Signal']:
        signal['action'] = 'BUY'
        signal['reason'] = f"EMA9 crossed above EMA21 (EMA9={latest['EMA9']:.2f}, EMA21={latest['EMA21']:.2f}) + RSI={latest['RSI']:.1f} < 30"
    
    # Check sell signal
    elif latest['Sell_Signal']:
        signal['action'] = 'SELL'
        signal['reason'] = f"EMA9 crossed below EMA21 (EMA9={latest['EMA9']:.2f}, EMA21={latest['EMA21']:.2f}) + RSI={latest['RSI']:.1f} > 70"
    
    # Check EMA
    elif latest['EMA9'] > latest['EMA21']:
        signal['reason'] = f"EMA9 above EMA21, RSI={latest['RSI']:.1f}"
    else:
        signal['reason'] = f"EMA9 below EMA21, RSI={latest['RSI']:.1f}"
    
    return signal


def get_recent_signals(df: pd.DataFrame, days: int = 30) -> list:
    signals = []
    buy_signals = df[df['Buy_Signal'] == True].tail(days)
    sell_signals = df[df['Sell_Signal'] == True].tail(days)
    
    for idx in buy_signals.index:
        price = df.loc[idx, 'Close']
        if hasattr(price, 'item'):
            price = price.item()
        signals.append({
            'date': str(idx.date()),
            'action': 'BUY',
            'price': price,
            'rsi': df.loc[idx, 'RSI']
        })
    
    for idx in sell_signals.index:
        price = df.loc[idx, 'Close']
        if hasattr(price, 'item'):
            price = price.item()
        signals.append({
            'date': str(idx.date()),
            'action': 'SELL',
            'price': price,
            'rsi': df.loc[idx, 'RSI']
        })
    
    return sorted(signals, key=lambda x: x['date'], reverse=True)


def format_recent_signals_message(recent_signals: list, limit: int = 10) -> str:
    if not recent_signals:
        return "No trading signals in the last 30 days"
    
    message_lines = []
    message_lines.append("=" * 60)
    message_lines.append("Recent trading signals (Last 30 Days)")
    message_lines.append("=" * 60)
    
    for i, s in enumerate(recent_signals[:limit], 1):
        signal = "🟢 BUY" if s['action'] == 'BUY' else "🔴 SELL"
        message_lines.append(f"{i:2d}. {signal} | {s['date']} | ${s['price']:.2f} | RSI: {s['rsi']:.1f}")
    
    message_lines.append("=" * 60)
    message_lines.append(f"Total signals found: {len(recent_signals)}")
    message_lines.append(f"Showing last {min(limit, len(recent_signals))} signals")
    
    return "\n".join(message_lines)


def format_summary_message(df: pd.DataFrame, signal: dict, recent_signals: list) -> str:
    #making a summary
    message_lines = []
    
    #header
    message_lines.append("=" * 60)
    message_lines.append(f"📈 GOLD TRADING STRATEGY SUMMARY")
    message_lines.append(f"   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    message_lines.append("=" * 60)
    
    #current Signal
    message_lines.append("")
    message_lines.append("🎯 CURRENT SIGNAL:")
    message_lines.append(f"   Date:     {signal['date']}")
    message_lines.append(f"   Price:    ${signal['close']:.2f}")
    message_lines.append(f"   RSI(14):  {signal['rsi']:.1f}")
    message_lines.append(f"   EMA(9):   ${signal['ema9']:.2f}")
    message_lines.append(f"   EMA(21):  ${signal['ema21']:.2f}")
    message_lines.append(f"   MACD:     {signal['macd']:.4f}")
    message_lines.append(f"   Signal:   {signal['macd_signal']:.4f}")
    message_lines.append(f"   ACTION:   {signal['action']}")
    message_lines.append(f"   Reason:   {signal['reason']}")
    
    #position Sizing
    message_lines.append("")
    message_lines.append("💼 POSITION SIZING:")
    message_lines.append(f"   Position Size: {POSITION_SIZE_PCT*100:.0f}% of capital")
    message_lines.append(f"   Max Drawdown:  {MAX_DRAWDOWN*100:.0f}%")
    
    #recent Signals
    if recent_signals:
        message_lines.append("")
        message_lines.append("📜 RECENT SIGNALS (Last 30 Days):")
        message_lines.append("-" * 50)
        
        for i, s in enumerate(recent_signals[:5], 1):  # Show last 5 in summary
            emoji = "🟢 BUY" if s['action'] == 'BUY' else "🔴 SELL"
            message_lines.append(f"   {i}. {emoji} | {s['date']} | ${s['price']:.2f} | RSI: {s['rsi']:.1f}")
        
        if len(recent_signals) > 5:
            message_lines.append(f"   ... and {len(recent_signals) - 5} more signals")
    
    #performance Metrics 
    message_lines.append("")
    message_lines.append("📊 MARKET CONTEXT:")
    
    #calculate some simple metrics
    df_clean = df.dropna()
    price_change = ((df_clean['Close'].iloc[-1] - df_clean['Close'].iloc[-5]) / df_clean['Close'].iloc[-5]) * 100
    message_lines.append(f"   Price Change (5 days): {price_change:+.2f}%")
    
    #count recent signals
    recent_buy = len([s for s in recent_signals[:30] if s['action'] == 'BUY'])
    recent_sell = len([s for s in recent_signals[:30] if s['action'] == 'SELL'])
    message_lines.append(f"   Signals (30 days): {recent_buy} BUY / {recent_sell} SELL")
    
    message_lines.append("")
    message_lines.append("=" * 60)
    message_lines.append("⚠️  This is not financial advice. Trade at your own risk.")
    
    return "\n".join(message_lines)


from config import BOT_TOKEN, CHAT_ID

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat in CHAT_ID:
        payload = {"chat_id": chat, "text": message}
        requests.post(url, data=payload)


def print_signal(signal: dict, recent_signals: list = None):
    #form the main message
    message_lines = []
    message_lines.append("=" * 60)
    message_lines.append(f"📈 GOLD TRADING SIGNAL - {signal['date']}")
    message_lines.append("=" * 60)
    message_lines.append(f"💰 Price: ${signal['close']:.2f}")
    message_lines.append(f"📊 RSI(14): {signal['rsi']:.1f}")
    message_lines.append(f"   EMA(9):  ${signal['ema9']:.2f}")
    message_lines.append(f"   EMA(21): ${signal['ema21']:.2f}")
    message_lines.append(f"   MACD:    {signal['macd']:.4f}")
    message_lines.append(f"   Signal:  {signal['macd_signal']:.4f}")
    message_lines.append("-" * 60)
    message_lines.append(f"🎯 ACTION: {signal['action']}")
    message_lines.append(f"   Reason: {signal['reason']}")
    message_lines.append("=" * 60)
    message_lines.append(f"\n💼 Position Sizing: {POSITION_SIZE_PCT*100:.0f}% of capital per trade")
    message_lines.append(f"⚠️  Max Drawdown Limit: {MAX_DRAWDOWN*100:.0f}%")
    
    ##recent signals if can find
    if recent_signals:
        message_lines.append("\n" + "=" * 60)
        message_lines.append("📜 RECENT SIGNALS (Last 30 Days):")
        message_lines.append("-" * 50)
        for i, s in enumerate(recent_signals[:5], 1):
            emoji = "🟢" if s['action'] == 'BUY' else "🔴"
            message_lines.append(f"   {i}. {emoji} {s['date']}: {s['action']} @ ${s['price']:.2f} (RSI: {s['rsi']:.1f})")
        if len(recent_signals) > 5:
            message_lines.append(f"   ... and {len(recent_signals) - 5} more signals")
        message_lines.append("=" * 60)
    
    message_text = "\n".join(message_lines)
    print("\n" + message_text)
    
    return message_text


def main():
    print("\n" + "=" * 60)
    print("   BASIC GOLD TRADING STRATEGY")
    print("   Symbol: GC=F (Gold Futures) | Timeframe: Daily")
    print("=" * 60 + "\n")
    
    try:
        #fetch data
        df = fetch_data(SYMBOL, DATA_PERIOD)
        # calculate indicators and signals
        df = generate_signals(df)
        # get latest signal
        signal = get_latest_signal(df)
        #get recent signals
        recent_signals = get_recent_signals(df, days=30)
        #print to console with recent signals
        console_message = print_signal(signal, recent_signals)
        #send to Telegram - Option 1: Combined summary message
        summary_message = format_summary_message(df, signal, recent_signals)
        send_telegram(summary_message)
        
        # alt. option: send separate messages
        '''
        send_telegram(console_message)
        if recent_signals:
            recent_message = format_recent_signals_message(recent_signals, limit=10)
            send_telegram(recent_message)'''
        
        # show in console usin print
        if recent_signals:
            print("\n📜 RECENT SIGNALS DETAIL (Last 30 days):")
            print("-" * 50)
            for i, s in enumerate(recent_signals[:10], 1):
                emoji = "🟢 BUY" if s['action'] == 'BUY' else "🔴 SELL"
                print(f"   {i:2d}. {emoji} | {s['date']} | ${s['price']:.2f} | RSI: {s['rsi']:.1f}")
            if len(recent_signals) > 10:
                print(f"   ... and {len(recent_signals) - 10} more signals")
        else:
            print("\n📜 No signals in the last 30 days")
        
        print("\n" + "=" * 60)
        print("✅ Analysis complete! Check Telegram for full report.")
        
        return signal
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()