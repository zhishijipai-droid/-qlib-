"""
严格按引擎真实回测数据生成微盘股JSON
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import json
from datetime import datetime
from engine.backtest import BacktestEngine
from strategies.micro_cap import get_signals

# ====== 跑回测 ======
print("▶ 跑回测...")
engine = BacktestEngine()
nav_df, metrics = engine.run_strategy(get_signals, "微盘股(月)", rebalance_freq=21)

# ====== 输出引擎原始指标 ======
print(f"\n引擎原始指标:")
for k, v in metrics.items():
    print(f"  {k}: {v}")

# ====== 提取净值数据 ======
def pct_val(s):
    return float(str(s).replace('%','').replace('+',''))

total_ret = pct_val(metrics.get('总收益率', '0%'))
ann_ret = pct_val(metrics.get('年化收益率', '0%'))
ann_vol = pct_val(metrics.get('年化波动率', '0%'))
sharpe = float(metrics.get('夏普比率', '0'))
mdd = abs(pct_val(metrics.get('最大回撤', '0%')))
calmar = float(metrics.get('卡尔玛比率', '0'))
win_rate = float(metrics.get('日胜率', '50%').replace('%',''))
final_nav = nav_df['nav'].iloc[-1]
total_value_10k = round(10000 * final_nav / 1000000, 2)

print(f"\n解析后指标:")
print(f"  总收益率: {total_ret}%")
print(f"  年化收益率: {ann_ret}%")
print(f"  年化波动率: {ann_vol}%")
print(f"  夏普比率: {sharpe}")
print(f"  最大回撤: {mdd}%")
print(f"  卡尔玛比率: {calmar}")
print(f"  日胜率: {win_rate}%")
print(f"  1万→: ¥{total_value_10k}")

# ====== 提取基准净值 ======
bench_history = []
bn = engine._benchmark_nav
if bn is not None:
    for i in range(len(nav_df)):
        if i < len(bn):
            v = float(bn.iloc[i])
            bench_history.append(round(v, 6) if not np.isnan(v) else 1.0)
        else:
            bench_history.append(1.0)
print(f"  基准数据: {len(bench_history)}天, 最终{bench_history[-1]:.4f}")

# ====== 净值序列 ======
nav_history = []
for date, row in nav_df.iterrows():
    nav_history.append({
        "date": date.strftime("%Y-%m-%d"),
        "nav": round(float(row['nav']), 2),
        "is_simulation": False
    })

# ====== 提取每月调仓 ======
print("\n▶ 提取月度调仓数据...")
end_date = engine.calendar['trade_date'].max()
full_data = engine._prepare_data(end_date)
trade_dates = sorted(full_data['trade_date'].unique())
trade_dates = [d for d in trade_dates if d >= pd.Timestamp('2020-12-24')]
date_groups = dict(tuple(full_data.groupby('trade_date')))

rebalance_dates = trade_dates[::21]
monthly_trades = []
prev_symbols = set()

for d in rebalance_dates[:60]:
    if d < trade_dates[0]:
        continue
    today = date_groups.get(d)
    if today is None or len(today) == 0:
        continue
    tradable = engine._filter_tradable(today)
    if len(tradable) == 0:
        continue
    signals = get_signals(tradable)
    if signals is None or len(signals) == 0:
        continue
    cur_symbols = set(signals['symbol'])
    added = cur_symbols - prev_symbols
    removed = prev_symbols - cur_symbols
    price_dict = dict(zip(tradable['symbol'], tradable['close_adj']))

    def top_n(syms, n=5):
        result = []
        for s in list(syms)[:n]:
            p = price_dict.get(s, 0)
            result.append({"symbol": s, "price": round(p, 2)})
        return result

    monthly_trades.append({
        "date": d.strftime("%Y-%m-%d"),
        "n_holdings": len(cur_symbols),
        "n_added": len(added),
        "n_removed": len(removed),
        "top_added": top_n(added),
        "top_removed": top_n(removed),
    })
    prev_symbols = cur_symbols

print(f"  调仓记录: {len(monthly_trades)}个月")

# ====== 组装策略条目 ======
strategy = {
    "id": "micro_cap_400",
    "name": "微盘股(最小400)",
    "source": "雷菱API + 自定义引擎",
    "description": "全A股市值最小的400只股票，等权每月调仓。参考米筐微盘股指数(866006.RI)。",
    "start_date": nav_history[0]['date'],
    "end_date": nav_history[-1]['date'],
    "annual_return": round(ann_ret, 2),
    "total_return": round(total_ret, 2),
    "sharpe": round(sharpe, 2),
    "max_drawdown": round(mdd, 2),
    "calmar": round(calmar, 2),
    "annual_vol": round(ann_vol, 2),
    "win_rate": win_rate,
    "total_value_10k": total_value_10k,
    "rebalance": "monthly",
    "nav_history": nav_history,
    "benchmark_nav": bench_history,
    "monthly_trades": monthly_trades
}

# ====== 保存 ======
out = {
    "strategies": [strategy],
    "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
}

out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "micro_cap_400.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"\n✅ 保存到: {out_path}")
print(f"   大小: {os.path.getsize(out_path) / 1024:.1f} KB")
print(f"   净值点: {len(nav_history)}")
print(f"   月度调仓: {len(monthly_trades)}笔")
