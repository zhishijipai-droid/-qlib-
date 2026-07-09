"""三策略对比: Top100 vs <100亿 vs 30-50亿"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from engine.backtest import BacktestEngine
from strategies.small_cap_top100 import get_signals as fn_top100
from strategies.small_cap import get_signals as fn_all
from strategies.small_cap_30_50 import get_signals as fn_30_50
from datetime import datetime

engine = BacktestEngine()

print("▶ 策略A: 最小100只")
nav_a, met_a = engine.run_strategy(fn_top100, "最小100只", rebalance_freq=21)

print("\n▶ 策略B: <100亿")
nav_b, met_b = engine.run_strategy(fn_all, "<100亿", rebalance_freq=21)

print("\n▶ 策略C: 30-50亿")
nav_c, met_c = engine.run_strategy(fn_30_50, "30-50亿", rebalance_freq=21)

keys = ['总收益率', '年化收益率', '年化波动率', '夏普比率', '最大回撤', '日胜率', '年化换手率']

print("\n" + "="*70)
print("📊 三策略对比")
print("="*70)
print(f"{'指标':<16} {'最小100只':<18} {'<100亿':<18} {'30-50亿':<18}")
print("-"*70)
for k in keys:
    v1 = met_a.get(k, '-')
    v2 = met_b.get(k, '-')
    v3 = met_c.get(k, '-')
    print(f"{k:<16} {str(v1):<18} {str(v2):<18} {str(v3):<18}")

print(f"\n{'最终净值':<16} {nav_a['nav'].iloc[-1]:>10.2f}       {nav_b['nav'].iloc[-1]:>10.2f}       {nav_c['nav'].iloc[-1]:>10.2f}")

out_dir = os.path.join(engine.data_dir, "..", "results", "compare3_" + datetime.now().strftime("%Y-%m-%d"))
os.makedirs(out_dir, exist_ok=True)
nav_a.to_csv(os.path.join(out_dir, "top100_nav.csv"))
nav_b.to_csv(os.path.join(out_dir, "all_below100_nav.csv"))
nav_c.to_csv(os.path.join(out_dir, "30_50_nav.csv"))
print(f"\n✅ 保存到: {out_dir}")
