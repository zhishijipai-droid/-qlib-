"""
给两个策略JSON补充计算型指标（Alpha/Beta/Sortino/信息比率等）
"""
import json, os, math
import numpy as np
from datetime import datetime

def calc_metrics(nav_history, bench_history):
    """从净值序列和基准序列计算衍生指标"""
    navs = [n['nav'] for n in nav_history]
    # 策略日收益率
    strat_rets = []
    for i in range(1, len(navs)):
        r = (navs[i] - navs[i-1]) / navs[i-1]
        strat_rets.append(r)
    
    # 基准日收益率
    bench_rets = []
    for i in range(1, len(bench_history)):
        r = (bench_history[i] - bench_history[i-1]) / bench_history[i-1]
        bench_rets.append(r)
    
    n = len(strat_rets)
    if n == 0:
        return {}
    
    strat_rets = np.array(strat_rets)
    bench_rets = np.array(bench_rets)
    
    # 超额收益序列
    excess_rets = strat_rets - bench_rets
    
    # 累计超额收益
    cum_excess = float(np.prod(1 + excess_rets) - 1)
    
    # 日均超额收益
    avg_excess = float(np.mean(excess_rets))
    daily_excess_pct = round(avg_excess * 100, 2)
    
    # 年化超额收益
    ann_excess = round((1 + avg_excess) ** 252 - 1, 4)
    
    # Alpha / Beta (线性回归)
    # Beta = cov(S, B) / var(B)
    cov = np.cov(strat_rets, bench_rets)[0][1]
    var_b = np.var(bench_rets)
    beta = float(cov / var_b) if var_b > 0 else 0
    # Alpha = E(S) - beta * E(B)
    alpha = float(np.mean(strat_rets) - beta * np.mean(bench_rets))
    # 年化Alpha
    alpha_ann = round(alpha * 252, 4)
    
    # 波动率
    strat_vol = float(np.std(strat_rets, ddof=1) * math.sqrt(252))
    bench_vol = float(np.std(bench_rets, ddof=1) * math.sqrt(252))
    
    # 夏普比率 (假设无风险利率=0)
    sharpe = round(np.mean(strat_rets) / np.std(strat_rets, ddof=1) * math.sqrt(252), 3) if np.std(strat_rets, ddof=1) > 0 else 0
    
    # 索提诺比率
    downside = strat_rets[strat_rets < 0]
    downside_std = float(np.std(downside, ddof=1) * math.sqrt(252)) if len(downside) > 1 else strat_vol
    sortino = round((np.mean(strat_rets) * 252) / downside_std, 3) if downside_std > 0 else 0
    
    # 信息比率 = 年化超额收益 / 跟踪误差
    tracking_error = float(np.std(excess_rets, ddof=1) * math.sqrt(252))
    info_ratio = round(ann_excess / tracking_error, 3) if tracking_error > 0 else 0
    
    # 超额收益最大回撤
    peak = 1.0
    excess_dd = 0
    excess_dd_start = ""
    excess_dd_end = ""
    cum_excess_series = np.cumprod(1 + excess_rets)
    dd_start_idx = 0
    for i, v in enumerate(cum_excess_series):
        if v > peak:
            peak = v
            dd_start_idx = i + 1
        dd_pct = (peak - v) / peak * 100
        if dd_pct > excess_dd:
            excess_dd = dd_pct
            excess_dd_start = nav_history[dd_start_idx]['date']
            excess_dd_end = nav_history[i + 1]['date']
    
    # 策略最大回撤区间
    nav_peak = navs[0]
    nav_dd = 0
    nav_dd_start = ""
    nav_dd_end = ""
    ndd_start_idx = 0
    for i, v in enumerate(navs):
        if v > nav_peak:
            nav_peak = v
            ndd_start_idx = i
        dd_pct = (nav_peak - v) / nav_peak * 100
        if dd_pct > nav_dd:
            nav_dd = dd_pct
            nav_dd_start = nav_history[ndd_start_idx]['date']
            nav_dd_end = nav_history[i]['date']
    
    # 日胜率 (按天计)
    daily_win = float(np.mean(strat_rets > 0))
    daily_win_rate = round(daily_win, 3)
    
    # 超额收益夏普
    excess_sharpe = round(np.mean(excess_rets) / np.std(excess_rets, ddof=1) * math.sqrt(252), 3) if np.std(excess_rets, ddof=1) > 0 else 0
    
    # 总收益率 (从NAV算)
    total_return = round((navs[-1] / navs[0] - 1) * 100, 2)
    # 基准总收益
    bench_total_return = round((bench_history[-1] / bench_history[0] - 1) * 100, 2)
    # 超额收益(总)
    excess_total = round(total_return - bench_total_return, 2)
    
    return {
        "total_return": total_return,
        "annual_return": round((navs[-1] / navs[0]) ** (252 / len(navs)) - 1, 4),
        "bench_total_return": bench_total_return,
        "excess_total_return": excess_total,
        "excess_annual_return": round(ann_excess * 100, 2),
        "alpha": alpha_ann,
        "beta": round(beta, 3),
        "sharpe": sharpe,
        "sortino": sortino,
        "daily_excess_pct": daily_excess_pct,
        "excess_max_drawdown": round(excess_dd, 2),
        "excess_dd_start": excess_dd_start,
        "excess_dd_end": excess_dd_end,
        "excess_sharpe": excess_sharpe,
        "daily_win_rate": daily_win_rate,
        "info_ratio": info_ratio,
        "strat_vol": round(strat_vol * 100, 2),
        "bench_vol": round(bench_vol * 100, 2),
        "nav_dd_start": nav_dd_start,
        "nav_dd_end": nav_dd_end,
    }


# ===== 处理两个策略 =====
output_dir = os.path.join(os.path.dirname(__file__), "..", "output")

for fname in ["small_cap_100yi.json", "micro_cap_400.json"]:
    path = os.path.join(output_dir, fname)
    if not os.path.exists(path):
        print(f"⚠️ 跳过 {fname} (不存在)")
        continue
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    s = data["strategies"][0]
    nav_history = s["nav_history"]
    bench_history = s.get("benchmark_nav", [])
    
    if len(bench_history) != len(nav_history):
        print(f"⚠️ {fname}: 基准长度({len(bench_history)}) != 净值长度({len(nav_history)}), 跳过")
        continue
    
    metrics = calc_metrics(nav_history, bench_history)
    s["extra_metrics"] = metrics
    
    # 更新主要指标（用更精确的计算替换引擎的）
    s["total_return"] = metrics["total_return"]
    s["annual_return"] = round(metrics["annual_return"] * 100, 2)
    # sharpe, mdd 等保留引擎值
    s["max_drawdown"] = round(float(s.get("max_drawdown", 0)), 2)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ {fname}:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"   {k}: {v:.4f}")
        else:
            print(f"   {k}: {v}")

print("\n完成!")
