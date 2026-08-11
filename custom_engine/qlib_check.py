"""检查红利v6策略涉及的股票和日期"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from strategies.dividend_yield_v6 import get_signals as div_fn

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 1. 加载K线，获取调仓日期
kline = pd.read_parquet(f"{DATA_DIR}/kline_adj.parquet", columns=['symbol', 'trade_date'])
if kline['trade_date'].dtype.name == 'uint16':
    kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit='D', origin='unix')

all_dates = sorted(kline['trade_date'].unique())

# 调仓日：每年1月/7月首个交易日
rb_dates = []
for d in all_dates:
    if d.month in (1, 7):
        if not rb_dates or d.month != rb_dates[-1].month or d.year != rb_dates[-1].year:
            rb_dates.append(d)

print(f"调仓日: {len(rb_dates)} 个, {rb_dates[0].date()} -> {rb_dates[-1].date()}")

# 2. 计算每个调仓日的信号
all_stocks = set()
for d in rb_dates:
    day_data = kline[kline['trade_date'] == d]
    if len(day_data) == 0:
        continue
    tradable = day_data[['symbol', 'trade_date']].copy()
    result = div_fn(tradable)
    if result is not None and len(result) > 0:
        for s in result['symbol']:
            all_stocks.add(s)

print(f"涉及股票: {len(all_stocks)} 只")
print(f"示例: {sorted(all_stocks)[:10]}")

# 3. 估算数据大小
print(f"\n完整K线: {kline['symbol'].nunique()} 只, {len(kline)} 行, "
      f"{kline['trade_date'].min().date()} -> {kline['trade_date'].max().date()}")

# 只读取这些股票的完整K线
kline_full = pd.read_parquet(f"{DATA_DIR}/kline_adj.parquet")
if kline_full['trade_date'].dtype.name == 'uint16':
    kline_full['trade_date'] = pd.to_datetime(kline_full['trade_date'], unit='D', origin='unix')

subset = kline_full[kline_full['symbol'].isin(all_stocks)]
print(f"子集: {len(subset)} 行, {subset['symbol'].nunique()} 只")
print(f"内存: {subset.memory_usage(deep=True).sum()/1024/1024:.1f} MB")
print(f"列: {list(subset.columns)}")

del kline, kline_full, subset
