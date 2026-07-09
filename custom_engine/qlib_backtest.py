"""Qlib回测: <100亿策略 - 简化版(500只股票)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from pathlib import Path
import shutil, tempfile

# ==== 1. 数据 ====
print("加载数据...")
k = pd.read_parquet("data/kline_adj.parquet")
cal = pd.read_parquet("data/calendar.parquet")
if cal['trade_date'].dtype == "uint16":
    cal['trade_date'] = pd.to_datetime(cal['trade_date'], unit="D", origin="unix")
cal = cal.sort_values('trade_date')

bt_start = "2021-01-04"
cal = cal[cal['trade_date'] >= bt_start]
cal_dates = [d.strftime("%Y-%m-%d") for d in cal['trade_date']]

# 只取与市值有交集的股票,再取500只
mc_check = pd.read_parquet("data/market_cap_full.parquet").reset_index()
mc_check['symbol'] = mc_check['order_book_id'].str.replace('.XSHE', '.SZ').str.replace('.XSHG', '.SH')
mc_syms = set(mc_check['symbol'].unique())
all_syms = sorted(set(k['symbol'].unique()) & mc_syms)
# 取有代表性的500只(按成交额排序取大中小的混合)
sym_volume = k.groupby('symbol')['volume'].sum().sort_values(ascending=False)
valid_syms = [s for s in sym_volume.index if s in all_syms]
# 每500取1只,确保覆盖大中小
step = max(1, len(valid_syms) // 500)
syms = valid_syms[::step][:500]
k = k[k['symbol'].isin(syms)]

print(f"  日历: {len(cal_dates)}天")
print(f"  股票: {len(syms)}只")

# ==== 2. 写入Qlib bin数据 ====
tmp = Path(tempfile.mkdtemp(prefix="qlib_"))
print(f"\n写入Qlib数据: {tmp}")

(tmp / "calendars").mkdir()
(tmp / "calendars" / "day.txt").write_text("\n".join(cal_dates))

(tmp / "instruments").mkdir()
lines = [f"{s}\t{cal_dates[0]}\t{cal_dates[-1]}" for s in syms]
(tmp / "instruments" / "all.txt").write_text("\n".join(lines))

date_idx = {d: i for i, d in enumerate(cal_dates)}
feat_dir = tmp / "features"
feat_dir.mkdir()

feats = ['close', 'volume']
for i, sym in enumerate(syms):
    sd = k[k['symbol'] == sym].sort_values('trade_date')
    sym_dir = feat_dir / sym
    sym_dir.mkdir()
    for col in feats:
        arr = np.full(len(cal_dates), np.nan, dtype=np.float64)
        for _, r in sd.iterrows():
            d = r['trade_date'].strftime('%Y-%m-%d') if isinstance(r['trade_date'], pd.Timestamp) else str(r['trade_date'])[:10]
            idx = date_idx.get(d)
            if idx is not None and not np.isnan(r[col]):
                arr[idx] = r[col]
        (sym_dir / f"{col}.day").write_bytes(arr.tobytes())
    if (i+1) % 100 == 0:
        print(f"   写入: {i+1}/{len(syms)}")

print(f"  ✓ {len(syms)}只股票")

# 加入benchmark: SH000300 (全市场平均价格)
avg_close = k.groupby('trade_date')['close'].mean().to_dict()
avg_arr = np.full(len(cal_dates), np.nan, dtype=np.float64)
for d_str, idx in date_idx.items():
    dt = pd.Timestamp(d_str)
    if dt in avg_close:
        avg_arr[idx] = avg_close[dt]
(feat_dir / "SH000300").mkdir()
(feat_dir / "SH000300" / "close.day").write_bytes(avg_arr.tobytes())
instr_syms = syms + ['SH000300']
(tmp / "instruments" / "all.txt").write_text("\n".join([f"{s}\t{cal_dates[0]}\t{cal_dates[-1]}" for s in instr_syms]))
print(f"  加入benchmark SH000300 ✓")

# ==== 3. Qlib初始化 ====
import qlib
qlib.init(provider_uri=str(tmp), region='cn')
from qlib.data import D
inst = D.list_instruments(D.instruments('all'), start_time=cal_dates[0])
print(f"  Qlib库存: {len(inst)}只")
# 验证benchmark
try:
    bench_test = D.features(['SH000300'], ['$close'], start_time=cal_dates[0], end_time=cal_dates[10])
    print(f"  SH000300验证: {len(bench_test)}行")
    if len(bench_test) > 0:
        print(bench_test.head(3))
    # 列出feature目录
    import os
    feat_contents = os.listdir(tmp / "features")
    print(f"  特征目录: {len(feat_contents)}个子目录")
    has_sh = os.path.isdir(tmp / "features" / "SH000300")
    print(f"  SH000300目录存在: {has_sh}")
    if has_sh:
        sh_files = os.listdir(tmp / "features" / "SH000300")
        print(f"  SH000300文件: {sh_files}")
except Exception as e:
    print(f"  SH000300验证失败: {e}")

# ==== 4. 信号: <100亿 ====
mc_df = pd.read_parquet("data/market_cap_full.parquet").reset_index()
mc_df['symbol'] = mc_df['order_book_id'].str.replace('.XSHE', '.SZ').str.replace('.XSHG', '.SH')
mc_df['mc_yi'] = mc_df['market_cap'] / 1e8
mc_df['date'] = mc_df['date'].dt.strftime('%Y-%m-%d')
mc_df = mc_df[mc_df['symbol'].isin(syms)]

rows = []
for d, grp in mc_df.groupby('date'):
    for _, r in grp.iterrows():
        rows.append({'datetime': d, 'instrument': r['symbol'], 'score': 1.0 if r['mc_yi'] < 100 else -1.0})
sig = pd.DataFrame(rows).set_index(['datetime', 'instrument'])['score']
sig = sig[sig.index.get_level_values('datetime') >= cal_dates[0]]
sig = sig[sig.index.get_level_values('datetime') <= cal_dates[-1]]
print(f"  信号: {len(sig)}行")

# ==== 5. Qlib回测 ====
from qlib.contrib.strategy.signal_strategy import TopkDropoutStrategy
from qlib.backtest import backtest

start_dt = cal_dates[200]
end_dt = cal_dates[-1]

print(f"\n▶ Qlib回测: {start_dt} ~ {end_dt}")

strategy = TopkDropoutStrategy(
    signal=sig,
    topk=200,  # 500只池子里选200
    n_drop=20,
    only_tradable=False,
)

try:
    pf, ind = backtest(
        start_time=start_dt,
        end_time=end_dt,
        strategy=strategy,
        executor={
            "class": "NestedExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {"time_per_step": "day", "generate_portfolio_metrics": True},
        },
        account=1000000,
        exchange_kwargs={
            "freq": "day",
            "codes": syms,
            "deal_price": "$close",
            "open_cost": 0.0003,
            "close_cost": 0.0013,
            "min_cost": 5.0,
        },
    )
    print("\n✅ Qlib回测完成!")
    print(f"  指标:")
    if isinstance(ind, dict):
        for k, v in ind.items():
            print(f"    {k}: {v}")
    if isinstance(pf, dict) and 'portfolio' in pf:
        p = pf['portfolio']
        print(f"  最终资产:")
        for k in ['total', 'cash', 'stock']:
            if k in p:
                print(f"    {k}: {p[k]:.2f}")
except Exception as e:
    print(f"\n❌ 失败: {e}")
    import traceback
    traceback.print_exc()

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n清理: {tmp}")
