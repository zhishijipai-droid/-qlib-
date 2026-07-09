"""对比回测引擎修复后: Top100 vs <100亿"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from engine.backtest import BacktestEngine
from strategies.small_cap_top100 import get_signals as fn_top100
from strategies.small_cap import get_signals as fn_all

import pandas as pd
from datetime import datetime

engine = BacktestEngine()

# Top100
nav_a, met_a = engine.run_strategy(fn_top100, "最小100只", rebalance_freq=21)

# <100亿
nav_b, met_b = engine.run_strategy(fn_all, "<100亿", rebalance_freq=21)

# 对比表
keys = ['总收益率', '年化收益率', '年化波动率', '夏普比率', '最大回撤', '日胜率', '年化换手率']
lines = []
lines.append("=" * 60)
lines.append("📊 策略对比 (引擎bug已修复)")
lines.append("=" * 60)
lines.append(f"{'指标':<16} {'最小100只':<18} {'<100亿':<18}")
lines.append("-" * 52)
for k in keys:
    v_a = met_a.get(k, '-')
    v_b = met_b.get(k, '-')
    lines.append(f"{k:<16} {str(v_a):<18} {str(v_b):<18}")
lines.append(f"\n最小100只 最终净值: {nav_a['nav'].iloc[-1]:.2f}")
lines.append(f"<100亿    最终净值: {nav_b['nav'].iloc[-1]:.2f}")

# 保存
out_dir = os.path.join(engine.data_dir, "..", "results", "compare_" + datetime.now().strftime("%Y-%m-%d"))
os.makedirs(out_dir, exist_ok=True)
nav_a.to_csv(os.path.join(out_dir, "top100_nav.csv"))
nav_b.to_csv(os.path.join(out_dir, "all_below100_nav.csv"))

out = "\n".join(lines)
print(out)
with open(os.path.join(out_dir, "comparison.txt"), "w") as f:
    f.write(out)
print(f"\n✅ 保存到: {out_dir}")
