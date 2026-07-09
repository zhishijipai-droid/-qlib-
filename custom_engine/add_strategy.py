"""
一键添加新策略到监控页面

用法:
  python add_strategy.py <策略ID> <策略文件名> [策略显示名]

示例:
  python add_strategy.py small_cap_top100 small_cap_top100 "最小100只"
  python add_strategy.py barra_4f barra_4factor "Barra四因子"

流程:
  1. 从 strategies/<文件名>.py 导入 get_signals
  2. 用引擎跑回测，获取净值 + 指标
  3. 提取每月调仓数据
  4. 更新 strategy.html 页面
"""
import sys, os, json, importlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if len(sys.argv) < 3:
    print("用法: python add_strategy.py <策略ID> <文件名> [显示名]")
    print("示例: python add_strategy.py small_top100 small_cap_top100 '最小100只'")
    sys.exit(1)

STRAT_ID = sys.argv[1]
MODULE_NAME = sys.argv[2]
STRAT_NAME = sys.argv[3] if len(sys.argv) > 3 else STRAT_ID

# ==== 1. 导入策略 ====
print(f"\n▶ 导入策略: {MODULE_NAME}")
try:
    mod = importlib.import_module(f"strategies.{MODULE_NAME}")
    get_signals = mod.get_signals
    name = getattr(mod, "STRATEGY_NAME", MODULE_NAME)
except Exception as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

print(f"   策略名: {name}")

# ==== 2. 跑回测 ====
print(f"\n▶ 跑回测...")
from engine.backtest import BacktestEngine
engine = BacktestEngine()
nav_df, metrics = engine.run_strategy(get_signals, name, rebalance_freq=21)

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

print(f"   年化: {ann_ret}%  累计: {total_ret}%  夏普: {sharpe}")

# ==== 3. 提取每月调仓 ====
import pandas as pd
import numpy as np

print(f"\n▶ 提取月度调仓数据...")
end_date = engine.calendar['trade_date'].max()
full_data = engine._prepare_data(end_date)
trade_dates = sorted(full_data['trade_date'].unique())
trade_dates = [d for d in trade_dates if d >= pd.Timestamp('2020-12-24')]
date_groups = dict(tuple(full_data.groupby('trade_date')))

rebalance_dates = trade_dates[::21]
rebalance_set = set(rebalance_dates)
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

print(f"   调仓记录: {len(monthly_trades)}个月")

# ==== 4. 组装数据 ====
print(f"\n▶ 组装策略数据...")
nav_history = []
for date, row in nav_df.iterrows():
    nav_history.append({
        "date": date.strftime("%Y-%m-%d"),
        "nav": round(float(row['nav']), 2),
        "is_simulation": False
    })

strategy_data = {
    "id": STRAT_ID,
    "name": STRAT_NAME,
    "source": "雷菱API + 自定义引擎",
    "description": f"自动生成的策略: {name}",
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
    "monthly_trades": monthly_trades
}

# ==== 5. 更新页面 ====
print(f"\n▶ 更新 strategy.html ...")
html_path = os.path.join(os.path.dirname(__file__), "..", "output", "strategy.html")
if not os.path.exists(html_path):
    print(f"❌ 找不到 strategy.html，请先运行 python build_webpage.py")
    sys.exit(1)

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# 替换STRATS数组 — 追加新策略
import re
match = re.search(r'var STRATS = (\[.*?\]);', html, re.DOTALL)
if match:
    old_array = match.group(1)
    # 在最后一项前插入新策略
    new_entry = json.dumps({
        "id": STRAT_ID, "name": STRAT_NAME,
        "ann": round(ann_ret, 2), "tot": round(total_ret, 2),
        "sharpe": round(sharpe, 2), "mdd": round(mdd, 2),
        "cal": round(calmar, 2), "vol": round(ann_vol, 2),
        "wr": round(win_rate, 1), "val": total_value_10k,
        "reb": "monthly"
    }, ensure_ascii=False)
    
    # 在最后一个 ] 前插入
    new_array = old_array.rstrip()[:-1] + ",\n    " + new_entry + "\n]"
    html = html.replace(old_array, new_array)
    
    # 替换DETAIL = 新策略数据
    detail_json = json.dumps(strategy_data, ensure_ascii=False)
    html = re.sub(r'var DETAIL = .*?;', f'var DETAIL = {detail_json};', html)
    
    # 写入更新提示
    from datetime import datetime
    html = re.sub(
        r'<span id="updTime">.*?</span>',
        f'<span id="updTime">{datetime.now().strftime("%Y-%m-%d %H:%M")}</span>',
        html
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"   ✅ strategy.html 已更新")
else:
    print(f"❌ 找不到 STRATS 数组")

print(f"\n✅ 完成! 打开 strategy.html 查看新策略")
print(f"   策略ID: {STRAT_ID}")
print(f"   策略名: {STRAT_NAME}")
print(f"   年化: {ann_ret}%  夏普: {sharpe}")
