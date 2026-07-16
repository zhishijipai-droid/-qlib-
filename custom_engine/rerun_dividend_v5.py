"""生成红利v5完整JSON"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import json, pandas as pd, numpy as np
from datetime import datetime
from engine.backtest import BacktestEngine
from strategies.dividend_yield_v5 import get_signals as fn_v5

def pct_val(s):
    return float(str(s).replace('%','').replace('+',''))

def run_and_save(strat_id, fn, name, json_path, freq=126):
    engine = BacktestEngine()
    nav_df, metrics = engine.run_strategy(fn, name, rebalance_freq=freq)

    total_ret = pct_val(metrics.get('总收益率','0%'))
    ann_ret = pct_val(metrics.get('年化收益率','0%'))
    ann_vol = pct_val(metrics.get('年化波动率','0%'))
    sharpe = float(metrics.get('夏普比率','0'))
    mdd = abs(pct_val(metrics.get('最大回撤','0%')))
    calmar = float(metrics.get('卡尔玛比率','0'))
    win_rate = float(metrics.get('日胜率','50%').replace('%',''))
    total_value_10k = round(10000 * nav_df['nav'].iloc[-1] / 1000000, 2)
    n_trades = int(metrics.get('交易次数','0'))
    n_wins = int(metrics.get('盈利次数','0'))
    n_losses = int(metrics.get('亏损次数','0'))
    pl_ratio = float(metrics.get('盈亏比','0').replace('N/A','0'))
    trade_win_rate = float(metrics.get('交易胜率','0%').replace('%',''))

    bench_history = []
    bn = engine._benchmark_nav
    if bn is not None:
        for i in range(len(nav_df)):
            v = float(bn.iloc[i]) if i < len(bn) else 1.0
            bench_history.append(round(v,6) if not np.isnan(v) else 1.0)

    nav_history = []
    for date, row in nav_df.iterrows():
        nav_history.append({"date": date.strftime("%Y-%m-%d"), "nav": round(float(row['nav']),2), "is_simulation":False})

    # 计算额外指标
    daily_ret = [nav_history[i]['nav']/nav_history[i-1]['nav']-1 for i in range(1,len(nav_history))]
    bench_ret = [bench_history[i]/bench_history[i-1]-1 for i in range(1,len(bench_history))]
    bench_total_ret = (bench_history[-1]/bench_history[0]-1)*100
    bench_vol = np.std(bench_ret)*np.sqrt(252)*100 if bench_ret else 0
    excess = [daily_ret[i]-bench_ret[i] for i in range(min(len(daily_ret),len(bench_ret)))]
    excess_total = (1+np.array(excess)).prod()-1 if excess else 0
    excess_nav = (1+np.array(excess)).cumprod()
    excess_dd = excess_nav/np.maximum.accumulate(excess_nav)-1
    excess_mdd = excess_dd.min()*100
    down_ret = [r for r in daily_ret if r<0]
    sortino = np.mean(daily_ret)/np.std(down_ret)*np.sqrt(252) if np.std(down_ret)>0 else 0
    daily_wr = sum(1 for r in daily_ret if r>0)/len(daily_ret) if daily_ret else 0
    n2 = min(len(daily_ret),len(bench_ret))
    if n2>20: beta,alpha = np.polyfit(bench_ret[:n2],daily_ret[:n2],1); alpha_ann=alpha*252
    else: beta,alpha,alpha_ann=0,0,0
    te = np.std(excess)*np.sqrt(252) if excess else 1
    ir = np.mean(excess)*np.sqrt(252)/te if te>0 else 0
    excess_ann = ((1+excess_total)**(252/max(len(excess),1))-1) if excess else 0
    excess_sharpe = np.mean(excess)/np.std(excess)*np.sqrt(252) if np.std(excess)>0 else 0

    dd_nav = (np.array([n['nav'] for n in nav_history])/np.maximum.accumulate(np.array([n['nav'] for n in nav_history]))-1)*100
    dates_arr = [n['date'] for n in nav_history]
    mdd_i = np.argmin(dd_nav)
    dd_s=dates_arr[0]; dd_e=dates_arr[-1]
    for i in range(mdd_i,-1,-1):
        if dd_nav[i]>=-0.5: dd_s=dates_arr[i]; break
    for i in range(mdd_i,len(dd_nav)):
        if dd_nav[i]>=-0.5: dd_e=dates_arr[i]; break
    ex_dates = dates_arr[1:1+len(excess_nav)]
    ex_mdd_i = np.argmin(excess_dd)
    ex_s=ex_dates[0] if ex_dates else dates_arr[0]
    ex_e=ex_dates[-1] if ex_dates else dates_arr[-1]
    for i in range(ex_mdd_i,-1,-1):
        if excess_dd[i]>=-0.5: ex_s=ex_dates[i] if i<len(ex_dates) else dates_arr[0]; break
    for i in range(ex_mdd_i,len(excess_dd)):
        if excess_dd[i]>=-0.5: ex_e=ex_dates[i] if i<len(ex_dates) else dates_arr[-1]; break

    # 月度调仓记录
    end_date = engine.calendar['trade_date'].max()
    full_data = engine._prepare_data(end_date)
    trade_dates = sorted(full_data['trade_date'].unique())
    trade_dates = [d for d in trade_dates if d>=pd.Timestamp('2020-12-24')]
    date_groups = dict(tuple(full_data.groupby('trade_date')))
    rebalance_dates = trade_dates[::freq]
    monthly_trades, prev_symbols = [], set()
    nav_map = {ps['date']:ps['nav'] for ps in engine._position_snapshots}

    for d in rebalance_dates[:60]:
        if d<trade_dates[0]: continue
        today = date_groups.get(d)
        if today is None or len(today)==0: continue
        tradable = engine._filter_tradable(today)
        if len(tradable)==0: continue
        signals = fn(tradable)
        if signals is None or len(signals)==0: continue
        cur_symbols = set(signals['symbol'])
        added = cur_symbols-prev_symbols; removed = prev_symbols-cur_symbols
        price_dict = dict(zip(tradable['symbol'],tradable['close_adj']))
        date_str = d.strftime("%Y-%m-%d"); nav = nav_map.get(date_str,0)
        n = len(cur_symbols); w = 1.0/n if n>0 else 0
        def tn(syms,limit=99999):
            res=[]
            for s in list(syms)[:limit]:
                p=price_dict.get(s,0)
                if p>0 and nav>0:
                    rs=nav*w/p
                    if s.startswith('688'): shares=int(rs) if rs>=200 else 0
                    elif s.startswith('8'): shares=int(rs) if rs>=100 else 0
                    else: shares=int(rs/100)*100
                else: shares=0
                res.append({"symbol":s,"price":round(p,2),"shares":shares,"amount":round(shares*p,2)})
            return res
        monthly_trades.append({"date":d.strftime("%Y-%m-%d"),"n_holdings":len(cur_symbols),
            "n_added":len(added),"n_removed":len(removed),"top_added":tn(added),"top_removed":tn(removed)})
        prev_symbols = cur_symbols

    strategy = {
        "id": strat_id, "name": name, "source": "雷菱API + 自定义引擎",
        "start_date": nav_history[0]['date'], "end_date": nav_history[-1]['date'],
        "annual_return": round(ann_ret,2), "total_return": round(total_ret,2),
        "sharpe": round(sharpe,2), "max_drawdown": round(mdd,2), "calmar": round(calmar,2),
        "annual_vol": round(ann_vol,2), "win_rate": win_rate, "total_value_10k": total_value_10k,
        "rebalance": "semi-annual",
        "nav_history": nav_history, "benchmark_nav": bench_history,
        "monthly_trades": monthly_trades,
        "trade_log": list(engine._trade_log)[-200:],
        "position_snapshots": [{"date":s['date'],"nav":s['nav'],"holdings":s['holdings']} for s in engine._position_snapshots],
        "trade_stats": {"n_trades":n_trades,"n_wins":n_wins,"n_losses":n_losses,"win_rate":round(trade_win_rate,2),"profit_loss_ratio":round(pl_ratio,2)},
        "n_wins": n_wins, "n_losses": n_losses, "profit_loss_ratio": pl_ratio, "trade_win_rate": str(round(trade_win_rate,2)),
        "sortino": round(sortino,2), "daily_win_rate": round(daily_wr,4),
        "alpha": round(alpha_ann,4), "beta": round(beta,4), "info_ratio": round(ir,2),
        "bench_total_return": f"{bench_total_ret:.2f}", "bench_vol": f"{bench_vol:.2f}",
        "excess_total_return": round(excess_total*100,2), "excess_annual_return": round(excess_ann*100,2),
        "excess_sharpe": round(excess_sharpe,2), "excess_max_drawdown": round(abs(excess_mdd),2),
        "excess_dd_start": ex_s, "excess_dd_end": ex_e,
        "daily_excess_pct": round(np.mean(excess)*100,3),
        "nav_dd_start": dd_s, "nav_dd_end": dd_e,
    }

    with open(json_path,"w",encoding="utf-8") as f:
        json.dump({"strategies":[strategy],"generated_at":datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},f,ensure_ascii=False,indent=2)
    print(f"✅ {name}: 年化{ann_ret}% 夏普{sharpe} 回撤{mdd}% 1万→{total_value_10k}")

if __name__ == "__main__":
    run_and_save("dividend_yield_v5", fn_v5, "红利策略v5(稳定分红)", os.path.join(os.path.dirname(__file__),"..","output","dividend_yield_v5.json"), 126)
