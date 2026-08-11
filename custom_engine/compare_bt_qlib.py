"""Backtrader vs Qlib 逐日对比"""
import json
import numpy as np
import pandas as pd

bt_path = r"D:\bigquant\output\dividend_yield_v6.json"
qlib_path = r"D:\bigquant\output\dividend_yield_v6_qlib.json"

with open(bt_path, 'r', encoding='utf-8') as f:
    bt_data = json.load(f)
with open(qlib_path, 'r', encoding='utf-8') as f:
    qlib_data = json.load(f)

bt_s = bt_data['strategies'][0]
qlib_s = qlib_data['strategies'][0]

# ============================================
# 1. 基本指标
# ============================================
print("=" * 60)
print("1. 基本指标对比")
print("-" * 40)
keys = ['annual_return', 'sharpe', 'max_drawdown', 'total_return', 'calmar', 'sortino', 'volatility', 'win_rate']
print(f"{'指标':<20} {'Backtrader':>12} {'Qlib':>12} {'差值':>10}")
for k in keys:
    bt_v = bt_s.get(k, 0)
    ql_v = qlib_s.get(k, 0)
    diff = ql_v - bt_v
    print(f"{k:<20} {bt_v:>12.2f} {ql_v:>12.2f} {diff:>+10.2f}")

# ============================================
# 2. NAV 对齐
# ============================================
print("\n" + "=" * 60)
print("2. NAV 逐日对比")

bt_nav = {d['date']: d['nav'] for d in bt_s['nav_history']}
qlib_nav = {d['date']: d['nav'] for d in qlib_s['nav_history']}

common_dates = sorted(set(bt_nav.keys()) & set(qlib_nav.keys()))
print(f"  Backtrader: {len(bt_nav)} 天, {list(bt_s['nav_history'])[0]['date']} → {list(bt_s['nav_history'])[-1]['date']}")
print(f"  Qlib:       {len(qlib_nav)} 天, {list(qlib_s['nav_history'])[0]['date']} → {list(qlib_s['nav_history'])[-1]['date']}")
print(f"  共同日期:   {len(common_dates)} 天")

# 逐日差值
diffs = []
for d in common_dates:
    diff = qlib_nav[d] - bt_nav[d]
    diffs.append((d, bt_nav[d], qlib_nav[d], diff))

# Top 10 最大差异
diffs_sorted = sorted(diffs, key=lambda x: abs(x[3]), reverse=True)
print(f"\n  Top 10 最大差异日:")
print(f"  {'日期':<12} {'BT净值':>14} {'Qlib净值':>14} {'差值':>14}")
for d, bv, qv, diff in diffs_sorted[:10]:
    print(f"  {d:<12} {bv:>14,.0f} {qv:>14,.0f} {diff:>+14,.0f}")

# 末10日
print(f"\n  最后 10 天:")
print(f"  {'日期':<12} {'BT净值':>14} {'Qlib净值':>14} {'差值':>14}")
for d, bv, qv, diff in diffs[-10:]:
    sign = "+" if diff >= 0 else ""
    print(f"  {d:<12} {bv:>14,.0f} {qv:>14,.0f} {diff:>+14,.0f}")

# ============================================
# 3. 调仓日差异
# ============================================
print("\n" + "=" * 60)
print("3. 调仓日差异")

# 找信号日 (NAV 大幅变化的日期)
bt_nav_list = list(bt_s['nav_history'])
sig_dates = set()
prev_nav = bt_nav_list[0]['nav']
for p in bt_nav_list[1:]:
    if abs(p['nav'] - prev_nav) / max(prev_nav, 1) > 0.005:  # NAV 突变 > 0.5%
        sig_dates.add(p['date'])
    prev_nav = p['nav']

# 也可能是交易发生日
trade_dates = set(t['date'] for t in bt_s.get('trade_log', []))

sig_and_trade = sig_dates | trade_dates
sig_date_list = sorted(sig_and_trade)

print(f"  NAV突变日: {len(sig_dates)} 天, 交易发生日: {len(trade_dates)} 天, 合并: {len(sig_date_list)} 天")

# 对比每个调仓日的持仓差异
print(f"\n  调仓日净值对比:")
print(f"  {'日期':<12} {'BT净值':>14} {'Qlib净值':>14} {'差值':>10} {'价差%':>10}")
for d in sig_date_list:
    if d in bt_nav and d in qlib_nav:
        bv = bt_nav[d]
        qv = qlib_nav[d]
        diff = qv - bv
        pct = diff / bv * 100 if bv > 0 else 0
        if abs(pct) > 0.1:
            print(f"  {d:<12} {bv:>14,.0f} {qv:>14,.0f} {diff:>+10,.0f} {pct:>+9.2f}%")

# ============================================
# 4. 交易对比
# ============================================
print("\n" + "=" * 60)
print("4. 交易对比")

bt_trades = bt_s.get('trade_log', [])
qlib_trades = qlib_s.get('trade_log', [])
print(f"  Backtrader 交易: {len(bt_trades)} 笔")
print(f"  Qlib 交易:       {len(qlib_trades)} 笔")

# 按日期统计
from collections import Counter
bt_by_date = Counter(t['date'][:7] for t in bt_trades)  # YYYY-MM
ql_by_date = Counter(t['date'][:7] for t in qlib_trades)
months = sorted(set(bt_by_date.keys()) | set(ql_by_date.keys()))
print(f"\n  按月交易次数:")
print(f"  {'月份':<10} {'BT':>6} {'Qlib':>6} {'差异':>6}")
for m in months:
    b = bt_by_date.get(m, 0)
    q = ql_by_date.get(m, 0)
    d = q - b
    flag = " ***" if d != 0 else ""
    print(f"  {m:<10} {b:>6} {q:>6} {d:>+6}{flag}")

# 按股票统计
bt_by_sym = Counter(t['symbol'] for t in bt_trades)
ql_by_sym = Counter(t['symbol'] for t in qlib_trades)
all_syms = sorted(set(bt_by_sym.keys()) | set(ql_by_sym.keys()))
print(f"\n  按股票交易差异 (Top 15):")
top_diffs = []
for s in all_syms:
    diff = ql_by_sym.get(s, 0) - bt_by_sym.get(s, 0)
    if diff != 0:
        top_diffs.append((s, bt_by_sym.get(s, 0), ql_by_sym.get(s, 0), diff))
top_diffs.sort(key=lambda x: abs(x[3]), reverse=True)
print(f"  {'股票':<14} {'BT':>6} {'Qlib':>6} {'差异':>6}")
for s, b, q, d in top_diffs[:15]:
    print(f"  {s:<14} {b:>6} {q:>6} {d:>+6}")

# ============================================
# 5. 持仓对比 (最后一个信号日)
# ============================================
print("\n" + "=" * 60)
print("5. 持仓对比")

bt_pos = {s['symbol']: s['qty'] for s in bt_s.get('position_snapshots', [{}])[-1].get('holdings', [])}
ql_pos = {s['symbol']: s['qty'] for s in qlib_s.get('position_snapshots', [{}])[-1].get('holdings', [])}
all_pos_syms = set(bt_pos.keys()) | set(ql_pos.keys())
print(f"  BT持仓: {len(bt_pos)} 只, Qlib持仓: {len(ql_pos)} 只")
print(f"  重叠: {len(set(bt_pos.keys()) & set(ql_pos.keys()))} 只")

diffs_pos = []
for s in all_pos_syms:
    b = bt_pos.get(s, 0)
    q = ql_pos.get(s, 0)
    if b != q:
        diffs_pos.append((s, b, q, q - b))
diffs_pos.sort(key=lambda x: abs(x[3]), reverse=True)
if diffs_pos:
    print(f"\n  仓位差异 (Top 20):")
    print(f"  {'股票':<14} {'BT股数':>10} {'Qlib股数':>10} {'差异':>10}")
    for s, b, q, d in diffs_pos[:20]:
        print(f"  {s:<14} {b:>10} {q:>10} {d:>+10}")

# ============================================
# 6. 日收益率相关性
# ============================================
print("\n" + "=" * 60)
print("6. 日收益率相关性")

bt_rets = []
ql_rets = []
for d in common_dates[1:]:
    if d in bt_nav and common_dates[common_dates.index(d)-1] in bt_nav:
        prev_d = common_dates[common_dates.index(d)-1]
        bt_ret = (bt_nav[d] / bt_nav[prev_d] - 1) * 100
        ql_ret = (qlib_nav[d] / qlib_nav[prev_d] - 1) * 100
        bt_rets.append(bt_ret)
        ql_rets.append(ql_ret)

corr = np.corrcoef(bt_rets, ql_rets)[0, 1]
print(f"  皮尔逊相关系数: {corr:.4f}")
print(f"  BT 日收益均值:  {np.mean(bt_rets):.4f}%  |  Qlib 日收益均值: {np.mean(ql_rets):.4f}%")
print(f"  BT 日波动:     {np.std(bt_rets):.4f}%  |  Qlib 日波动:    {np.std(ql_rets):.4f}%")
