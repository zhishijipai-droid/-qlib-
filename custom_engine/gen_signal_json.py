"""从CSV生成今日信号策略的持仓数据（含股价、市值）"""
import json, os
import pandas as pd
import numpy as np
csv_path = "C:/Users/86133/Downloads/四个股票池持仓.csv"
out_path = "D:/bigquant/output/current_signal.json"
data_dir = "D:/bigquant/custom_engine/data"

df = pd.read_csv(csv_path, encoding='gbk')

# 筛选: HOLD+BUY, 排除ETF, 排除SELL
is_etf = df['symbol'].str.contains(r'159\d{3}|163\d{3}|515\d{3}|516\d{3}|560\d{3}|562\d{3}|563\d{3}|501\d{3}', regex=True)
stock = df[df['action'].isin(['HOLD','BUY'])].copy()
stock = stock[~is_etf]
stock = stock[stock['target_position_raw'].notna() & (stock['target_position_raw'] > 0)]

# 转换symbol
def convert_symbol(s):
    if s.startswith('SHSE.'): return s.replace('SHSE.', '') + '.SH'
    elif s.startswith('SZSE.'): return s.replace('SZSE.', '') + '.SZ'
    return s

def lookup_price(sym_code, price_map, price_map_bj, price_map_sz):
    # 依次尝试 .SH, .BJ, .SZ
    for pmap in [price_map, price_map_bj, price_map_sz]:
        if sym_code in pmap:
            return pmap[sym_code]
    # 尝试去掉后缀
    base = sym_code.split('.')[0]
    for pmap in [price_map, price_map_bj, price_map_sz]:
        for k, v in pmap.items():
            if k.startswith(base):
                return v
    return 0

def parse_shares(note):
    """从note中提取股数, 如 '买入1400股' → 1400"""
    import re
    m = re.search(r'买入(\d+)股', str(note))
    if m:
        return int(m.group(1))
    # 也可能是 "增持XXXX股" 等格式
    m = re.search(r'(\d+)股', str(note))
    if m:
        return int(m.group(1))
    return 0

stock['shares_raw'] = stock['note'].apply(parse_shares)
stock['code'] = stock['symbol'].apply(convert_symbol)
stock['name'] = stock['stock_name_raw'].str.replace('*ST', '').str.replace('ST', '')
trade_date = str(stock['trade_date'].iloc[0])

# 按股票池分别归一化权重 (每个池=100%, 然后各占50%)
# 日池: target_per_pool / pool_sum, 然后 × 0.5
# 周池: target_per_pool / pool_sum, 然后 × 0.5
stock['pool'] = stock['cohort_id'].str.split('__').str[0]
stock['weight'] = 0.0
for pool_name in stock['pool'].unique():
    mask = stock['pool'] == pool_name
    pool_total = stock.loc[mask, 'target_position_raw'].sum()
    stock.loc[mask, 'weight'] = stock.loc[mask, 'target_position_raw'] / pool_total * 0.5
print(f"各池权重: {stock.groupby('pool')['weight'].sum().to_dict()}")

# === 获取股价数据 (成本价 + 最新价) ===
print(f"加载K线数据...")
kline = pd.read_parquet(os.path.join(data_dir, "kline_1d.parquet"))
if kline['trade_date'].dtype == 'uint16':
    kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit='D', origin='unix')

# 成本价: 信号日期
signal_ts = pd.Timestamp(trade_date)
cost_day = kline[kline['trade_date'] == signal_ts]
if len(cost_day) > 0:
    cost_map = dict(zip(cost_day['symbol'], cost_day['close']))
    cost_map_bj = {k: v for k, v in cost_map.items() if k.endswith('.BJ')}
    cost_map_sz = {k: v for k, v in cost_map.items() if k.endswith('.SZ') or k.endswith('.SH')}
else:
    cost_map, cost_map_bj, cost_map_sz = {}, {}, {}

# 最新价: 最新交易日
latest_date = kline['trade_date'].max()
latest_day = kline[kline['trade_date'] == latest_date]
if len(latest_day) > 0:
    latest_map = dict(zip(latest_day['symbol'], latest_day['close']))
    latest_map_bj = {k: v for k, v in latest_map.items() if k.endswith('.BJ')}
    latest_map_sz = {k: v for k, v in latest_map.items() if k.endswith('.SZ') or k.endswith('.SH')}
else:
    latest_map, latest_map_bj, latest_map_sz = {}, {}, {}

print(f"  成本日: {signal_ts.date()}, 最新日: {latest_date.date()}")

holdings = []
for _, row in stock.iterrows():
    code = row['code']
    cost_price = lookup_price(code, cost_map, cost_map_bj, cost_map_sz)
    latest_price = lookup_price(code, latest_map, latest_map_bj, latest_map_sz)
    shares = int(row['shares_raw'])
    
    cost_value = shares * cost_price if cost_price > 0 else 0
    curr_value = shares * latest_price if latest_price > 0 else 0
    pnl = curr_value - cost_value
    pnl_pct = pnl / cost_value * 100 if cost_value > 0 else 0
    
    holdings.append({
        "symbol": code,
        "name": row['name'],
        "shares": shares,
        "price": round(latest_price, 2),
        "cost_price": round(cost_price, 2),
        "value": round(curr_value, 2),
        "cost_value": round(cost_value, 2),
        "weight": round(row['weight'] * 100, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
    })

holdings.sort(key=lambda x: x['weight'], reverse=True)

# === 生成净值曲线 ===
print(f"\n生成净值曲线...")
dates = sorted(kline['trade_date'].unique())
start_date = pd.Timestamp(trade_date)  # 从信号日开始
dates = [d for d in dates if d >= start_date and d <= latest_date]

nav_vals = []
valid_dates = []
for d in dates:
    day = kline[kline['trade_date'] == d]
    if len(day) == 0: continue
    day_prices = dict(zip(day['symbol'], day['close']))
    total = 0
    has_data = 0
    for hh in holdings:
        sym = hh['symbol']
        sh = hh['shares']
        if sym in day_prices:
            total += sh * day_prices[sym]
            has_data += 1
    if has_data >= 30 and total > 0:
        nav_vals.append(total)
        valid_dates.append(d)

if nav_vals:
    init_val = nav_vals[0]
    nav4 = np.array([v / init_val for v in nav_vals])
    
    if len(nav4) >= 3:  # 至少有3天才能算有意义
        daily_ret = nav4[1:] / nav4[:-1] - 1
        n_days = len(daily_ret)
        ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
        sharpe = float(np.mean(daily_ret) / np.std(daily_ret, ddof=1) * np.sqrt(252)) if ann_vol > 0 and np.std(daily_ret) > 0 else 0
        down = daily_ret[daily_ret < 0]
        downside = float(np.std(down, ddof=1) * np.sqrt(252)) if len(down) > 1 else ann_vol
        sortino = float(np.mean(daily_ret) / (downside / np.sqrt(252)) * np.sqrt(252)) if downside > 0 else 0
        peak = np.maximum.accumulate(nav4)
        dd = (nav4 - peak) / peak * 100
        max_dd = float(np.min(dd))
        dd_end = int(np.argmin(dd))
        dd_start = int(np.argmax(peak[:dd_end+1])) if dd_end > 0 else 0
        calmar = float(np.mean(daily_ret) * 252 / abs(max_dd) * 100) if max_dd != 0 else 0
        daily_win = int(np.sum(daily_ret > 0))
        daily_win_rate = daily_win / n_days if n_days > 0 else 0
        total_years = n_days / 252
        ann_ret = float(nav4[-1] ** (1 / total_years) - 1) if total_years > 0 and len(nav4) > 1 else 0
    else:
        n_days = len(nav4) - 1
        ann_vol = 0; sharpe = 0; sortino = 0
        max_dd = 0; dd_start = 0; dd_end = 0; calmar = 0
        daily_win_rate = 0; ann_ret = 0
    
    tot_ret = float((nav4[-1] - 1) * 100)
    
    print(f"  有效天数: {n_days}")
    print(f"  起始: {valid_dates[0].date()} ¥{init_val:,.0f}")
    print(f"  最新: {valid_dates[-1].date()} ¥{nav_vals[-1]:,.0f} ({tot_ret:+.2f}%)")
    print(f"  年化: {ann_ret*100:+.2f}% 波动: {ann_vol*100:.2f}% 夏普: {sharpe:.2f} 回撤: {max_dd:.2f}%")
else:
    nav4 = [1.0]
    ann_ret = 0; tot_ret = 0; ann_vol = 0; sharpe = 0
    sortino = 0; max_dd = 0; dd_start = 0; dd_end = 0
    calmar = 0; daily_win_rate = 0; daily_win = 0; n_days = 0

strategy = {
    "id": "current_signal",
    "name": "今日信号",
    "source": "日池+周池信号",
    "description": f"基于{trade_date}信号, {len(holdings)}只持仓",
    "date": trade_date,
    "n_holdings": len(holdings),
    "holdings": holdings,
    "annual_return": round(ann_ret*100, 2),
    "total_return": round(tot_ret, 2),
    "sharpe": round(sharpe, 2),
    "max_drawdown": round(abs(max_dd), 2),
    "calmar": round(calmar, 2),
    "annual_vol": round(ann_vol*100, 2),
    "sortino": round(sortino, 2),
    "daily_win_rate": round(daily_win_rate, 4),
    "win_rate": round(daily_win_rate*100, 1),
    "bench_total_return": 0,
    "bench_vol": 0,
    "total_value_10k": round(nav4[-1]*10000, 2),
    "rebalance": "每日更新",
    "n_wins": 0, "n_losses": 0, "profit_loss_ratio": 0, "trade_win_rate": "0",
    "nav_dd_start": str(valid_dates[dd_start].date()) if nav_vals else "",
    "nav_dd_end": str(valid_dates[dd_end].date()) if nav_vals else "",
    "nav_history": [{"date": str(d.date()), "nav": round(float(n), 4)} for d, n in zip(valid_dates, nav4)],
    "dates": [str(d.date()) for d in valid_dates],
    "navs": [round(float(n), 4) for n in nav4],
}

data = {"strategies": [strategy], "generated_at": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%S")}

with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 显示前5
print(f"\n✅ 已保存: {out_path}")
print(f"   持仓: {len(holdings)} 只")
print(f"   日期: {trade_date}")
print(f"\n   前5持仓:")
for h in holdings[:5]:
    print(f"     {h['symbol']}  ¥{h['price']}  {h['shares']}股  ¥{h['value']:.0f}  {h['weight']}%")
