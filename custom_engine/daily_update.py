"""
每日数据更新 + 今日信号发布 + 策略回测 全套流水线
每日 16:00 (ETL 15:30 完成后) 执行:
  1. 从 sim API 拉最新 K线/因子/市值
  2. 合并到本地 Parquet
  3. 如果有新的CSV信号文件 → 生成今日信号
  4. 跑全部策略回测 (小市值/微盘/红利v5)
  5. 更新网站 (M1/M2/M3 + 今日信号)
"""
import os, sys, glob, json, subprocess
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ===== 配置 =====
DATA_DIR = "D:/bigquant/custom_engine/data"
OUTPUT_DIR = "D:/bigquant/output"
CSV_WATCH_DIR = "C:/Users/86133/Downloads"
CUSTOM_ENGINE = "D:/bigquant/custom_engine"
BASE = "http://115.159.73.134:8765"

def _run(cmd, cwd=None):
    """执行命令并返回输出"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd or CUSTOM_ENGINE)
    if result.returncode != 0:
        print(f"  ⚠️ 命令失败: {cmd[:80]}...")
        print(f"     {result.stderr[:200]}")
    return result.stdout

# ===== Step 1: 更新 K线数据 (从 sim API) =====
def update_kline():
    """从 sim API 拉取最新 K 线并合并"""
    print("\n[1/5] 更新 K 线数据...")
    
    kline_path = os.path.join(DATA_DIR, "kline_1d.parquet")
    if os.path.exists(kline_path):
        old = pd.read_parquet(kline_path)
        if old['trade_date'].dtype == 'uint16':
            old['trade_date'] = pd.to_datetime(old['trade_date'], unit='D', origin='unix')
        last_date = old['trade_date'].max()
        print(f"  本地已有数据: 截至 {last_date.date()}, {len(old)} 行")
    else:
        old = pd.DataFrame()
        last_date = pd.Timestamp("2020-01-01")
    
    try:
        s = _sim("/sim/summary")
        latest = s['kline']['latest_date']
        print(f"  服务器最新: {latest}")
        
        if last_date >= pd.Timestamp(latest):
            # 检查是否完整: 最新一天应有5000只左右
            latest_day = old[old['trade_date'] == last_date]
            if len(latest_day) >= 4000:
                print(f"  数据已最新且完整 ({len(latest_day)} 只), 跳过")
                return True
            else:
                print(f"  日期最新但数据不完整 ({len(latest_day)} 只), 重新下载...")
        
        days = (pd.Timestamp(latest) - last_date).days + 5
        if days > 60: days = 60
        
        # sim API 有 50000 行上限, 分多次拉取
        batch_days = min(days, 5)  # 每批最多5天
        
        all_new = []
        dates_to_fetch = list(pd.date_range(end=pd.Timestamp(latest), periods=days, freq='B'))
        # 分批: 每5天一批
        for i in range(0, len(dates_to_fetch), batch_days):
            chunk_start = dates_to_fetch[max(0, i-batch_days)]
            chunk_end = dates_to_fetch[i+batch_days-1] if i+batch_days-1 < len(dates_to_fetch) else dates_to_fetch[-1]
            print(f"  拉取 {chunk_start.date()} ~ {chunk_end.date()}...")
            try:
                data = _sim("/sim/kline", {"days": batch_days+2, "limit": 50000})
                if data.get('data'):
                    df = pd.DataFrame(data['data'])
                    df['trade_date'] = pd.to_datetime(df['trade_date'])
                    df['symbol'] = df['symbol'].str.replace('.XSHG','.SH').str.replace('.XSHE','.SZ')
                    all_new.append(df)
                    print(f"    → {len(df)} 行")
            except Exception as e:
                print(f"    ⚠️ {e}")
        
        if not all_new:
            print("  无新数据")
            return True
        new_df = pd.concat(all_new).drop_duplicates(subset=['symbol', 'trade_date'])
        
        # 检查下载完整性: 和前一天比股票数不应该大幅减少
        dates = sorted(new_df['trade_date'].unique())
        for d in dates:
            cnt = len(new_df[new_df['trade_date'] == d])
            prev = old[old['trade_date'] == d - pd.Timedelta(days=7)]
            if len(prev) > 0 and cnt < len(prev) * 0.5:
                print(f"  ⚠️ {d.date()} 只有 {cnt} 只 (预期 ≈{len(prev)}), 跳过这天")
                new_df = new_df[new_df['trade_date'] != d]
        
        if not old.empty:
            combined = pd.concat([old, new_df]).drop_duplicates(subset=['symbol', 'trade_date']).sort_values('trade_date')
        else:
            combined = new_df
        
        combined.to_parquet(kline_path, index=False)
        print(f"✅ K线已更新: {len(combined)} 行, 截至 {combined['trade_date'].max().date()}")
        return True
    except Exception as e:
        print(f"  ⚠️ sim API 不可达: {e}, 跳过更新")
        return False

def _sim(path, params=None, timeout=30):
    r = requests.get(f"{BASE}{path}", params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

# ===== Step 2: 检查新 CSV 信号 =====
def find_latest_signal():
    print("\n[2/5] 检查新信号文件...")
    files = glob.glob(os.path.join(CSV_WATCH_DIR, "*四个股票池*"))
    if not files:
        print("  未找到信号文件")
        return None
    latest = max(files, key=os.path.getmtime)
    mod_time = datetime.fromtimestamp(os.path.getmtime(latest))
    print(f"  最新: {os.path.basename(latest)} ({mod_time.strftime('%m-%d %H:%M')})")
    return latest

# ===== Step 3: 今日信号发布 =====
def publish_signal(csv_path):
    print("\n[3/5] 发布今日信号...")
    if csv_path is None:
        print("  跳过")
        return
    
    out = _run("python gen_signal_json.py")
    if "✅" in out:
        out2 = _run("python add_signal_strat.py")
        if "✅" in out2:
            print("✅ 今日信号已更新")
        else:
            print("  ❌ add_signal_strat.py 失败")
    else:
        print("  ❌ gen_signal_json.py 失败")

# ===== Step 4: 跑回测 =====
def run_backtests():
    print("\n[4/5] 跑策略回测...")
    
    # 小市值 + 微盘股
    print("  ▶ 小市值 + 微盘股...")
    out = _run("python rerun_both.py")
    if "全部完成" in out or "✅" in out:
        print("  ✅ 小市值/微盘完成")
    else:
        print(f"  输出: {out[-200:]}")
    
    # 红利v5
    print("  ▶ 红利策略v5...")
    out = _run("python rerun_dividend_v5.py")
    if "✅" in out:
        print("  ✅ 红利v5完成")
    else:
        print(f"  输出: {out[-200:]}")

# ===== Step 5: 更新网站 =====
def update_website():
    print("\n[5/5] 更新网站...")
    out = _run("python update_all_strats.py")
    if "✅" in out:
        print("✅ M1/M2/M3 已更新")
    else:
        print(f"  update输出: {out}")

# ===== Main =====
if __name__ == "__main__":
    print(f"=== 每日全套流水线 === {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    update_kline()
    csv_file = find_latest_signal()
    publish_signal(csv_file)
    run_backtests()
    update_website()
    
    print("\n✅ 全套流水线完成")

