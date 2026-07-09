"""
对比回测: <100亿 vs 最小100只
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.dirname(__file__)))

from engine.backtest import BacktestEngine
engine = BacktestEngine()

# 1. 最小100只
from strategies.small_cap_top100 import get_signals as fn_top100
print("\n" + "="*50)
print("▶ 策略A: 最小100只")
nav_a, met_a = engine.run_strategy(fn_top100, "最小100只", rebalance_freq=21)

# 2. <100亿
from strategies.small_cap import get_signals as fn_all
print("\n" + "="*50)
print("▶ 策略B: <100亿")
nav_b, met_b = engine.run_strategy(fn_all, "<100亿", rebalance_freq=21)

# 3. 对比
print("\n" + "="*60)
print("📊 策略对比")
print("="*60)

keys = ['总收益率', '年化收益率', '年化波动率', '夏普比率', '最大回撤', '日胜率', '年化换手率']
print(f"{'指标':<16} {'最小100只':<18} {'<100亿':<18}")
print("-"*52)
for k in keys:
    v_a = met_a.get(k, '-')
    v_b = met_b.get(k, '-')
    print(f"{k:<16} {str(v_a):<18} {str(v_b):<18}")

# 净值末尾
print(f"\n最小100只 最终净值: {nav_a['nav'].iloc[-1]:.4f}")
print(f"<100亿    最终净值: {nav_b['nav'].iloc[-1]:.4f}")

# 保存
out_dir = "/d/bigquant/qlib_sim/results/compare_" + __import__('datetime').datetime.now().strftime("%Y-%m-%d")
os.makedirs(out_dir, exist_ok=True)
nav_a.to_csv(os.path.join(out_dir, "top100_nav.csv"))
nav_b.to_csv(os.path.join(out_dir, "all_below100_nav.csv"))
print(f"\n✅ 详细净值保存到: {out_dir}")
