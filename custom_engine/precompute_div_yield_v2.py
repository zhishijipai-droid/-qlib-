"""
重新计算股息率 — 对齐聚宽 STK_XR_XD 口径

问题: CASH_PAY_DIST_DIV_PRO_INT 含偿付利息, 高估银行等公司股息率
修正: 按负债率扣除利息成分
  debt_ratio < 30%: 利息占比 10%
  debt_ratio 30-60%: 利息占比 25%
  debt_ratio > 60%: 利息占比 40%
"""
import pandas as pd
import numpy as np
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR

print("加载数据...")
div = pd.read_parquet(os.path.join(DATA_DIR, "dividend_data.parquet"))
bs = pd.read_parquet(os.path.join(DATA_DIR, "balance_sheet.parquet"))
mc = pd.read_parquet(os.path.join(DATA_DIR, "market_cap_full.parquet"))

# 转换日期
if div['ann_date'].dtype in ('int64', 'uint16'):
    div['ann_date'] = pd.to_datetime(div['ann_date'], unit='D', origin='unix')
if div['report_period'].dtype in ('int64', 'uint16'):
    div['rp'] = pd.to_datetime(div['report_period'], unit='D', origin='unix')

# 负债率
bs = bs.sort_values('ann_date').groupby('symbol').last().reset_index()
bs['debt_ratio'] = bs['total_liabilities'] / bs['total_assets'].replace(0, np.nan)
debt_map = dict(zip(bs['symbol'], bs['debt_ratio']))

# 修正股息: 按负债率扣除利息
def adjust_dividend(row):
    debt = debt_map.get(row['symbol'], 0.5)
    if pd.isna(debt): debt = 0.5
    if debt < 0.3:
        interest_ratio = 0.10
    elif debt < 0.6:
        interest_ratio = 0.25
    else:
        interest_ratio = 0.40
    return row['dividend_paid'] * (1 - interest_ratio)

div['dividend_clean'] = div.apply(adjust_dividend, axis=1)
print(f"调整前总分红: {div['dividend_paid'].sum()/1e8:.0f}亿")
print(f"调整后总分红: {div['dividend_clean'].sum()/1e8:.0f}亿")
print(f"扣除利息: {(div['dividend_paid']-div['dividend_clean']).sum()/1e8:.0f}亿")

# 市值
mc = mc.reset_index()
mc['symbol'] = mc['order_book_id'].str.replace('.XSHE', '.SZ').str.replace('.XSHG', '.SH')
mc['date'] = pd.to_datetime(mc['date'])
mc['mc_yi'] = mc['market_cap'] / 1e8

print("\n按月计算股息率...")
dates = sorted(mc['date'].unique())
# 只用1月和7月 (对齐聚宽调仓时点)
month_ends = [d for d in dates if (d.month == 1 and d.day >= 28) or (d.month == 7 and d.day >= 28)]

results = []
for i, d in enumerate(month_ends):
    if i % 10 == 0:
        print(f"  {d.date()} ({i+1}/{len(month_ends)})")
    
    # 取这天之前12个月的分红 (用调整后的)
    start = d - pd.DateOffset(months=12)
    mask = (div['ann_date'] >= start) & (div['ann_date'] <= d)
    period_div = div[mask].groupby('symbol')['dividend_clean'].sum()
    
    # 取当天市值
    day_mc = mc[mc['date'] == d]
    if len(day_mc) == 0: continue
    mc_series = day_mc.set_index('symbol')['mc_yi']
    
    common = period_div.index.intersection(mc_series.index)
    if len(common) == 0: continue
    
    # 股息率 = 调整后分红(元) / 市值(亿元×1e8) 
    for sym in common:
        dy = period_div[sym] / (mc_series[sym] * 1e8)
        if dy > 0 and dy < 0.50:  # 过滤异常值
            results.append({'symbol': sym, 'date': d, 'div_yield': float(dy)})

result_df = pd.DataFrame(results)
print(f"\n修正后股息率: {len(result_df)} 行, {result_df['symbol'].nunique()} 只")
print(f"均值: {result_df['div_yield'].mean()*100:.2f}%")
print(f"中位数: {result_df['div_yield'].median()*100:.2f}%")

out_path = os.path.join(DATA_DIR, "dividend_yield_v2.parquet")
result_df.to_parquet(out_path)
print(f"\n已保存到 {out_path}")
