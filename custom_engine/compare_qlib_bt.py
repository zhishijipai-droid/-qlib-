"""
对比 Qlib 回测 vs Backtrader 回测 (红利v6)
"""
import os, sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

def load_nav(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    s = d["strategies"][0] if "strategies" in d else d
    nav_list = s["nav_history"]
    dates = [p["date"] for p in nav_list]
    navs = [p["nav"] for p in nav_list]
    start_date = s.get("start_date", dates[0] if dates else "?")
    end_date = s.get("end_date", dates[-1] if dates else "?")
    kpis = {
        "annual_return": s.get("annual_return", 0),
        "sharpe": s.get("sharpe", 0),
        "max_drawdown": s.get("max_drawdown", 0),
        "annual_vol": s.get("annual_vol", 0),
        "total_return": s.get("total_return", 0),
    }
    return dates, navs, start_date, end_date, kpis

def compute_kpis(navs):
    if len(navs) < 2:
        return {}
    # 归一化到 1.0 起点
    base = navs[0]
    norm_navs = np.array(navs) / base
    daily_ret = norm_navs[1:] / norm_navs[:-1] - 1
    ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
    sharpe = float(np.mean(daily_ret) / np.std(daily_ret, ddof=1) * np.sqrt(252)) if ann_vol > 0 else 0
    peak = np.maximum.accumulate(norm_navs)
    mdd = float(np.min((norm_navs - peak) / peak)) * 100
    n_days = len(norm_navs)
    total_years = n_days / 252
    ann_ret = float(norm_navs[-1] ** (1 / total_years) - 1) * 100 if total_years > 0 else 0
    tot_ret = float((norm_navs[-1] - 1) * 100)
    return {
        "annual_return": round(ann_ret, 2),
        "total_return": round(tot_ret, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(abs(mdd), 2),
        "annual_vol": round(ann_vol * 100, 2),
    }

print("=" * 70)
print("  红利v6 回测对比: Qlib 引擎 vs Backtrader")
print("=" * 70)

# 加载数据
bt_json = os.path.join(OUTPUT_DIR, "dividend_yield_v6.json")
qlib_json = os.path.join(OUTPUT_DIR, "dividend_yield_v6_qlib.json")

if not os.path.exists(bt_json):
    print(f"Backtrader JSON 不存在: {bt_json}")
    exit(1)
if not os.path.exists(qlib_json):
    print(f"Qlib JSON 不存在: {qlib_json}")
    exit(1)

bt_dates, bt_navs, bt_start, bt_end, bt_kpis = load_nav(bt_json)
qlib_dates, qlib_navs, qlib_start, qlib_end, qlib_kpis = load_nav(qlib_json)

print(f"\n  数据范围:")
print(f"    Backtrader: {bt_start} → {bt_end}  ({len(bt_navs)} 天)")
print(f"    Qlib:       {qlib_start} → {qlib_end}  ({len(qlib_navs)} 天)")

# 重新计算 KPI 以确保公平对比
bt_kpi = compute_kpis(bt_navs)
qlib_kpi = compute_kpis(qlib_navs)

print(f"\n  性能指标对比:")
print(f"  {'指标':<16} {'Backtrader':>14} {'Qlib引擎':>14} {'差异':>14}")
print(f"  {'-'*60}")
for k in ["annual_return", "total_return", "sharpe", "max_drawdown", "annual_vol"]:
    bt_v = bt_kpi.get(k, 0)
    ql_v = qlib_kpi.get(k, 0)
    diff = ql_v - bt_v
    unit = "%" if k in ("annual_return", "total_return", "max_drawdown", "annual_vol") else ""
    label = {
        "annual_return": "年化收益",
        "total_return": "总收益",
        "sharpe": "夏普比率",
        "max_drawdown": "最大回撤",
        "annual_vol": "年化波动",
    }.get(k, k)
    print(f"  {label:<16} {bt_v:>13.2f}{unit} {ql_v:>13.2f}{unit} {diff:>+13.2f}{unit}")

# 对比净值曲线 (对齐到重叠区间)
bt_map = {d: v for d, v in zip(bt_dates, bt_navs)}
qlib_map = {d: v for d, v in zip(qlib_dates, qlib_navs)}
common_dates = sorted(set(bt_map.keys()) & set(qlib_map.keys()))
print(f"\n  重叠日期: {len(common_dates)} 天 ({common_dates[0]} → {common_dates[-1]})")

# 计算RMSE和相关性
bt_common = np.array([bt_map[d] for d in common_dates])
qlib_common = np.array([qlib_map[d] for d in common_dates])

# 归一化到同一起点
bt_norm = bt_common / bt_common[0]
qlib_norm = qlib_common / qlib_common[0]

rmse = np.sqrt(np.mean((bt_norm - qlib_norm) ** 2))
corr = np.corrcoef(bt_norm, qlib_norm)[0, 1]
print(f"  净值 RMSE: {rmse:.6f}  (越小越好)")
print(f"  净值相关性: {corr:.4f}  (越接近1越好)")

# 收益率相关性
bt_ret = bt_common[1:] / bt_common[:-1] - 1
qlib_ret = qlib_common[1:] / qlib_common[:-1] - 1
ret_corr = np.corrcoef(bt_ret, qlib_ret)[0, 1]
print(f"  日收益率相关性: {ret_corr:.4f}")

print("\n" + "=" * 70)
