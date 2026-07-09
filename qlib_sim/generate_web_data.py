"""生成<100亿策略网页数据：净值+每月调仓详情"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import json
from datetime import datetime
from engine.backtest import BacktestEngine
from strategies.small_cap import get_signals

# ====== 跑回测 ======
engine = BacktestEngine()
nav_df, metrics = engine.run_strategy(get_signals, "<100亿", rebalance_freq=21)

# ====== 提取每月调仓数据 ======
# 重新跑一遍信号，记录每个调仓日选了哪些股票
end_date = engine.calendar['trade_date'].max()
full_data = engine._prepare_data(end_date)
trade_dates = sorted(full_data['trade_date'].unique())
trade_dates = [d for d in trade_dates if d >= pd.Timestamp('2020-12-24')]
date_groups = dict(tuple(full_data.groupby('trade_date')))

rebalance_dates = trade_dates[::21]  # 跟引擎一致的频率
rebalance_set = set(rebalance_dates)

monthly_trades = []
prev_symbols = set()
start_date = trade_dates[0]

for d in rebalance_dates[:60]:  # 最多60个月
    if d < start_date:
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
    
    # 计算当日价格
    price_dict = dict(zip(tradable['symbol'], tradable['close_adj']))
    
    # 取前5新增和前5移除
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

print(f"调仓记录: {len(monthly_trades)}个月")

# ====== 净值数据 ======
nav_history = []
bench_history = []
bn = engine._benchmark_nav
for i, (date, row) in enumerate(nav_df.iterrows()):
    nav_history.append({
        "date": date.strftime("%Y-%m-%d"),
        "nav": round(float(row['nav']), 2),
        "is_simulation": False
    })
    # 加入基准净值(位置对齐,bench_nav索引是整数)
    if bn is not None and i < len(bn):
        v = float(bn.iloc[i])
        bench_history.append(round(v, 6) if not (v != v) else 1.0)  # NaN→1.0
    else:
        bench_history.append(1.0)

print(f"基准数据: {len(bench_history)}天, 最终{bench_history[-1]:.4f}")

# ====== 指标 ======
def pct_val(s):
    return float(str(s).replace('%','').replace('+',''))

total_ret = pct_val(metrics.get('总收益率', '0%'))
ann_ret = pct_val(metrics.get('年化收益率', '0%'))
ann_vol = pct_val(metrics.get('年化波动率', '0%'))
sharpe = float(metrics.get('夏普比率', '0'))
mdd = abs(pct_val(metrics.get('最大回撤', '0%')))
calmar = float(metrics.get('卡尔玛比率', '0'))
win_rate = float(metrics.get('日胜率', '53%').replace('%',''))
final_nav = nav_df['nav'].iloc[-1]
total_value_10k = round(10000 * final_nav / 1000000, 2)  # 以1万为基准

# ====== 组装策略条目 ======
strategy = {
    "id": "small_cap_100yi",
    "name": "<100亿小市值",
    "source": "雷菱API + 自定义引擎",
    "description": "全A股市值<100亿的股票，等权每月调仓。剔除ST/停牌。约2900只成分股，极度分散，风格接近小微盘等权指数。",
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
out_path = os.path.join(out_dir, "small_cap_100yi.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"✅ 保存到: {out_path}")
print(f"   大小: {os.path.getsize(out_path) / 1024:.1f} KB")
print()
print(f"   净值点: {len(nav_history)}")
print(f"   月度调仓: {len(monthly_trades)}笔")
print(f"   年化: {ann_ret}%")
print(f"   累计: {total_ret}%")
print(f"   夏普: {sharpe}")
print(f"   回撤: {mdd}%")
print(f"   1万→¥{total_value_10k}")
