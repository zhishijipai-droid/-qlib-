"""
重新跑两个策略回测，补充交易统计指标
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import json, math
import numpy as np
from datetime import datetime
from engine.backtest import BacktestEngine
from strategies.small_cap import get_signals as fn1
from strategies.micro_cap import get_signals as fn2

def pct_val(s):
    return float(str(s).replace('%','').replace('+',''))

def run_and_save(strat_id, fn, name, json_path):
    print(f"\n▶ {name}")
    engine = BacktestEngine()
    nav_df, metrics = engine.run_strategy(fn, name, rebalance_freq=21)
    
    # ===== 引擎原始指标 =====
    total_ret = pct_val(metrics.get('总收益率', '0%'))
    ann_ret = pct_val(metrics.get('年化收益率', '0%'))
    ann_vol = pct_val(metrics.get('年化波动率', '0%'))
    sharpe = float(metrics.get('夏普比率', '0'))
    mdd = abs(pct_val(metrics.get('最大回撤', '0%')))
    calmar = float(metrics.get('卡尔玛比率', '0'))
    win_rate = float(metrics.get('日胜率', '50%').replace('%',''))
    total_value_10k = round(10000 * nav_df['nav'].iloc[-1] / 1000000, 2)
    
    # ===== 交易统计 (引擎新加的) =====
    n_trades = int(metrics.get('交易次数', '0'))
    n_wins = int(metrics.get('盈利次数', '0'))
    n_losses = int(metrics.get('亏损次数', '0'))
    pl_ratio = float(metrics.get('盈亏比', '0').replace('N/A', '0'))
    trade_win_rate = float(metrics.get('交易胜率', '0%').replace('%',''))
    
    print(f"  总收益率: {total_ret}%  年化: {ann_ret}%  夏普: {sharpe}")
    print(f"  交易次数: {n_trades}  盈利: {n_wins}  亏损: {n_losses}  盈亏比: {pl_ratio:.2f}")
    
    # ===== 基准净值 =====
    bench_history = []
    bn = engine._benchmark_nav
    if bn is not None:
        for i in range(len(nav_df)):
            if i < len(bn):
                v = float(bn.iloc[i])
                bench_history.append(round(v, 6) if not np.isnan(v) else 1.0)
            else:
                bench_history.append(1.0)
    
    # ===== 净值序列 =====
    nav_history = []
    for date, row in nav_df.iterrows():
        nav_history.append({
            "date": date.strftime("%Y-%m-%d"),
            "nav": round(float(row['nav']), 2),
            "is_simulation": False
        })
    
    import pandas as pd
    
    # ===== 每月调仓 =====
    end_date = engine.calendar['trade_date'].max()
    full_data = engine._prepare_data(end_date)
    trade_dates = sorted(full_data['trade_date'].unique())
    trade_dates = [d for d in trade_dates if d >= pd.Timestamp('2020-12-24')]
    date_groups = dict(tuple(full_data.groupby('trade_date')))
    rebalance_dates = trade_dates[::21]
    monthly_trades = []
    prev_symbols = set()
    # 从引擎获取调仓日的nav
    nav_map = {}
    for ps in engine._position_snapshots:
        nav_map[ps['date']] = ps['nav']
    
    for d in rebalance_dates[:60]:
        if d < trade_dates[0]: continue
        today = date_groups.get(d)
        if today is None or len(today)==0: continue
        tradable = engine._filter_tradable(today)
        if len(tradable)==0: continue
        signals = fn(tradable)
        if signals is None or len(signals)==0: continue
        cur_symbols = set(signals['symbol'])
        added = cur_symbols - prev_symbols
        removed = prev_symbols - cur_symbols
        price_dict = dict(zip(tradable['symbol'], tradable['close_adj']))
        date_str = d.strftime("%Y-%m-%d")
        nav = nav_map.get(date_str, 0)
        n = len(cur_symbols)
        weight = 1.0 / n if n > 0 else 0
        def top_n(syms, n=99999):
            res = []
            for s in list(syms)[:n]:
                p = price_dict.get(s, 0)
                # 估算股数: nav * weight / price, 按板块规则取整
                if p > 0 and nav > 0:
                    raw_shares = nav * weight / p
                    if s.startswith('688'):
                        shares = int(raw_shares) if raw_shares >= 200 else 0
                    elif s.startswith('8'):
                        shares = int(raw_shares) if raw_shares >= 100 else 0
                    else:
                        shares = int(raw_shares / 100) * 100
                else:
                    shares = 0
                res.append({"symbol": s, "price": round(p, 2), "shares": shares, "amount": round(shares * p, 2)})
            return res
        monthly_trades.append({
            "date": d.strftime("%Y-%m-%d"),
            "n_holdings": len(cur_symbols),
            "n_added": len(added),
            "n_removed": len(removed),
            "top_added": top_n(added),
            "top_removed": top_n(removed),
        })
        prev_symbols = cur_symbols
    
    # ===== 组装 =====
    strategy = {
        "id": strat_id,
        "name": name,
        "source": "雷菱API + 自定义引擎",
        "description": "",
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
        "monthly_trades": monthly_trades,
        "trade_log": list(engine._trade_log)[-200:],  # 最近200笔
        "position_snapshots": [dict(
            date=s['date'],
            nav=s['nav'],
            holdings=s['holdings']  # 全部持仓
        ) for s in list(engine._position_snapshots)],  # 全部月份
        # 交易统计
        "trade_stats": {
            "n_trades": n_trades,
            "n_wins": n_wins,
            "n_losses": n_losses,
            "win_rate": round(trade_win_rate, 2),
            "profit_loss_ratio": round(pl_ratio, 2)
        }
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"strategies": [strategy], "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ 保存到 {json_path}")
    return strategy

if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out_dir, exist_ok=True)
    
    s1 = run_and_save("small_cap_100yi", fn1, "<100亿小市值", os.path.join(out_dir, "small_cap_100yi.json"))
    s2 = run_and_save("micro_cap_400", fn2, "微盘股(最小400)", os.path.join(out_dir, "micro_cap_400.json"))
    
    print("\n✅ 全部完成!")
