"""
Qlib 回测 — 红利v6 策略

与 Backtrader 等价流程:
  1. 信号: 复用 dividend_yield_v6.get_signals() → signal_map
  2. 数据: kline_adj.parquet → Qlib 二进制格式 (存 D 盘)
  3. 撮合: Qlib Exchange + A股手数规则
  4. 输出: 相同 JSON 格式

Qlib 数据路径: D:/bigquant/qlib_data/div_v6/
Memory: 仅转换 91 只股票的 K 线 (~60MB)
"""

import sys, os, json, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from datetime import datetime
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
QLIB_DIR = "D:/bigquant/qlib_data/div_v6"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ============================================================
# Step 1: 转换 K 线为 Qlib 格式
# ============================================================

def _to_qlib_date(d):
    """datetime → yyyymmdd int"""
    if hasattr(d, 'strftime'):
        return int(d.strftime('%Y%m%d'))
    return int(str(d)[:10].replace('-', ''))


def _lot_size(code):
    """A股手数规则 (与bt_shared.py一致)"""
    s = str(code)
    if '688' in s:
        return 200, 1, 100000   # 科创板: 最小200, 1股递增, 限价上限10万
    if s.startswith('4') or s.startswith('8'):
        return 100, 1, 1000000  # 北交所: 最小100, 1股递增, 上限100万
    if '300' in s or '301' in s:
        return 100, 100, 300000 # 创业板: 最小100, 100股递增, 限价上限30万
    # 沪深主板
    return 100, 100, 1000000    # 最小100, 100股递增, 上限100万


def convert_to_qlib(stock_symbols, kline_path):
    """
    将指定股票的K线转为Qlib二进制格式

    Qlib目录结构:
      calendars/day.txt        — 交易日历
      instruments/all.txt      — 股票列表
      features/{stock}/
        open.day.bin, close.day.bin, high.day.bin, low.day.bin,
        volume.day.bin, amount.day.bin, adjfactor.day.bin
    """
    print("=" * 50)
    print("[Qlib] 转换数据格式...")
    
    # 清理旧数据
    if os.path.exists(QLIB_DIR):
        shutil.rmtree(QLIB_DIR)
    
    os.makedirs(f"{QLIB_DIR}/calendars", exist_ok=True)
    os.makedirs(f"{QLIB_DIR}/instruments", exist_ok=True)
    os.makedirs(f"{QLIB_DIR}/features", exist_ok=True)
    
    # 读取K线 (只读需要的列)
    cols = ['symbol', 'trade_date', 'open_adj', 'high_adj', 'low_adj', 
            'close_adj', 'volume', 'amount', 'adj_factor']
    df = pd.read_parquet(kline_path, columns=cols)
    if df['trade_date'].dtype.name == 'uint16':
        df['trade_date'] = pd.to_datetime(df['trade_date'], unit='D', origin='unix')
    
    # 过滤股票
    stock_set = set(stock_symbols)
    df = df[df['symbol'].isin(stock_set)].copy()
    df = df.sort_values(['symbol', 'trade_date'])
    
    print(f"  过滤后: {len(df)} 行, {df['symbol'].nunique()} 只")
    
    # 交易日历
    all_dates = sorted(df['trade_date'].unique())
    with open(f"{QLIB_DIR}/calendars/day.txt", "w") as f:
        for d in all_dates:
            f.write(f"{_to_qlib_date(d)}\n")
    print(f"  交易日历: {len(all_dates)} 天")
    
    # 股票列表 (3列格式: symbol start_date end_date)
    all_syms = sorted(df['symbol'].unique())
    first_date_str = all_dates[0].strftime('%Y-%m-%d') if hasattr(all_dates[0], 'strftime') else str(all_dates[0])[:10]
    last_date_str = all_dates[-1].strftime('%Y-%m-%d') if hasattr(all_dates[-1], 'strftime') else str(all_dates[-1])[:10]
    with open(f"{QLIB_DIR}/instruments/all.txt", "w") as f:
        for s in all_syms:
            f.write(f"{s}\t{first_date_str}\t{last_date_str}\n")
    print(f"  股票列表: {len(all_syms)} 只")
    
    # 逐股票写入特征 (OOM-safe) — Qlib 二进制格式
    date_to_idx = {d: i for i, d in enumerate(all_dates)}
    
    feature_names = ['open', 'high', 'low', 'close', 'volume', 'amount', 'adjfactor', 'factor']
    col_map = {
        'open': 'open_adj', 'high': 'high_adj', 'low': 'low_adj',
        'close': 'close_adj', 'volume': 'volume', 'amount': 'amount',
        'adjfactor': 'adj_factor',
        'factor': '_ones',  # factor=1 表示调整价≈名义价, 用于手数计算
    }
    
    for si, sym in enumerate(all_syms):
        stock_df = df[df['symbol'] == sym].set_index('trade_date')
        
        # 找到该股票在日历中的起始和结束索引
        stock_dates = set(stock_df.index)
        stock_indices = [date_to_idx[d] for d in stock_dates if d in date_to_idx]
        if not stock_indices:
            continue
        start_idx = min(stock_indices)
        end_idx = max(stock_indices)
        
        for feat_name, col_name in col_map.items():
            feat_dir = f"{QLIB_DIR}/features/{sym}"
            os.makedirs(feat_dir, exist_ok=True)
            
            # 只写有数据的区间 (Qlib 格式: [start_index] + float32 data)
            vals = np.full(end_idx - start_idx + 1, np.nan, dtype=np.float32)
            if col_name == '_ones':
                vals.fill(1.0)  # factor=1 表示调整价≈名义价
            else:
                for d, row in stock_df.iterrows():
                    idx = date_to_idx.get(d)
                    if idx is not None:
                        vals[idx - start_idx] = float(row[col_name])
            
            np.hstack([start_idx, vals]).astype("<f").tofile(f"{feat_dir}/{feat_name}.day.bin")
        
        if (si + 1) % 20 == 0:
            print(f"  转换进度: {si + 1}/{len(all_syms)}")
    
    print(f"  ✅ Qlib 数据已保存: {QLIB_DIR}")
    print(f"     大小: {_dir_size(QLIB_DIR):.1f} MB")
    
    del df
    return all_syms, all_dates


def _dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    return total / 1024 / 1024


# ============================================================
# Step 2: 信号生成 (复用现有策略)
# ============================================================

def generate_signals(kline):
    """复用红利v6信号生成"""
    from strategies.dividend_yield_v6 import get_signals as div_fn
    
    all_dates = sorted(kline['trade_date'].unique())
    
    # 调仓日
    rb_dates = []
    for d in all_dates:
        if d.month in (1, 7):
            if not rb_dates or d.month != rb_dates[-1].month or d.year != rb_dates[-1].year:
                rb_dates.append(d)
    
    print(f"  调仓日: {len(rb_dates)} 个")
    
    signal_map = {}
    sorted_dates = []
    for d in rb_dates:
        day_data = kline[kline['trade_date'] == d]
        if len(day_data) == 0:
            continue
        tradable_df = day_data[['symbol', 'trade_date']].copy()
        result = div_fn(tradable_df)
        if result is not None and len(result) > 0:
            weights = dict(zip(result['symbol'], result['weight']))
            date_str = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
            signal_map[date_str] = weights
            sorted_dates.append(date_str)
    
    return signal_map, sorted_dates


# ============================================================
# Step 3: Qlib 回测引擎
# ============================================================

def backtest_qlib(signal_map, sorted_dates, init_cash=1_000_000):
    """
    Qlib风格回测: 逐日模拟, 在信号日调仓, 尊重A股手数规则
    
    不使用 qlib.backtest.backtest() (太重), 自己写轻量循环,
    逻辑与 bt_shared.py 的 PortfolioStrategy.next() 一致。
    """
    print("=" * 50)
    print("[Qlib] 回测中...")
    
    # 加载 Qlib 数据 -> DataFrame
    features_dir = f"{QLIB_DIR}/features"
    
    # 读日历
    with open(f"{QLIB_DIR}/calendars/day.txt") as f:
        cal_dates_str = [line.strip() for line in f if line.strip()]
    cal_dates = [pd.Timestamp(d[:4] + '-' + d[4:6] + '-' + d[6:8]) for d in cal_dates_str]
    
    # 读股票列表
    stock_ids = []
    with open(f"{QLIB_DIR}/instruments/all.txt") as f:
        for line in f:
            parts = line.strip().split('\t')
            if parts:
                stock_ids.append(parts[0])
    
    # 加载close价格到DataFrame (索引=日期, 列=股票)
    all_closes = {}
    for sym in stock_ids:
        path = f"{features_dir}/{sym}/close.day.bin"
        arr = np.fromfile(path, dtype=np.float64)
        all_closes[sym] = arr
    
    close_df = pd.DataFrame(all_closes, index=cal_dates)
    
    # ── 关键修复: forward-fill NaN (停牌日沿用前一日收盘价) ──
    close_df = close_df.ffill().fillna(0.0)
    n_dates = len(cal_dates)
    
    # 对齐Backtrader: 从第一个信号日之前开始
    first_signal_date = pd.Timestamp(sorted_dates[0]) if sorted_dates else cal_dates[0]
    start_idx = 0
    for i, d in enumerate(cal_dates):
        if d >= first_signal_date:
            start_idx = max(0, i - 5)
            break
    
    print(f"  起始日期: {cal_dates[start_idx].date()} (信号始于 {first_signal_date.date()})")
    
    # ── 辅助函数: 获取安全价格 ──
    def safe_price(sym, idx, fallback_idx=None):
        """获取股票价格, NaN时回退到前一日"""
        if sym not in close_df.columns:
            return 0.0
        px = float(close_df.iloc[idx][sym])
        if np.isnan(px) or px <= 0:
            if fallback_idx is not None and fallback_idx >= start_idx:
                return safe_price(sym, fallback_idx)
            return 0.0
        return px
    
    # 初始化
    cash = float(init_cash)
    positions = {}  # {symbol: (qty, avg_cost)}
    navs = []
    nav_dates = []
    trade_log = []
    position_snapshots = []
    
    signal_idx = 0
    
    for i in range(start_idx, n_dates):
        trade_date = cal_dates[i]
        date_str = trade_date.strftime('%Y-%m-%d')
        
        # ── 信号日: 调仓 ──
        if signal_idx < len(sorted_dates) and date_str == sorted_dates[signal_idx]:
            target_weights = signal_map[date_str]
            
            # Step A: 计算当前总资产 (使用 safe_price, 不跳过任何持仓)
            total_value = cash
            for sym, (qty, _) in list(positions.items()):
                px = safe_price(sym, i, i - 1)
                if px > 0:
                    total_value += qty * px
            
            # Step B: 先卖后买（与 Backtrader 顺序一致）
            # 先对所有非目标股票挂卖出
            for sym, (qty, _) in list(positions.items()):
                if sym not in target_weights:
                    px = safe_price(sym, i, i - 1)
                    if px > 0:
                        cash += qty * px
                        trade_log.append({
                            'date': date_str, 'symbol': sym, 'side': 'SELL',
                            'qty': qty, 'price': round(px, 2),
                            'amount': round(qty * px, 2)
                        })
                        del positions[sym]
            
            # Step C: 重新计算总资产 (卖出后 cash 增加了)
            total_value = cash
            for sym, (qty, _) in positions.items():
                px = safe_price(sym, i, i - 1)
                if px > 0:
                    total_value += qty * px
            
            # Step D: 按目标权重重新分配
            #    先算每个目标的买入量
            buys = []  # [(sym, qty, px)]
            for sym, w in target_weights.items():
                tv = total_value * w
                px = safe_price(sym, i, i - 1)
                if px <= 0:
                    continue
                
                lot_min, lot_inc, lot_max = _lot_size(sym)
                target_qty_raw = tv / px
                target_qty = int(target_qty_raw // lot_inc) * lot_inc
                if target_qty < lot_min:
                    target_qty = 0
                target_qty = min(target_qty, lot_max)
                
                # 先卖出多余的 (partial reduce)
                if sym in positions:
                    current_qty = positions[sym][0]
                    if target_qty < current_qty:
                        sell_qty = current_qty - target_qty
                        cash += sell_qty * px
                        trade_log.append({
                            'date': date_str, 'symbol': sym, 'side': 'SELL',
                            'qty': sell_qty, 'price': round(px, 2),
                            'amount': round(sell_qty * px, 2)
                        })
                        if target_qty == 0:
                            del positions[sym]
                        else:
                            positions[sym] = (target_qty, px)
                
                # 计算实际需要买入的量
                if target_qty > 0:
                    current_qty = positions.get(sym, (0, 0))[0]
                    buy_qty = target_qty - current_qty
                    if buy_qty > 0:
                        buys.append((sym, buy_qty, px))
            
            # Step E: 按 original weights 比例分配剩余现金
            total_buy_cost = sum(bq * p for _, bq, p in buys)
            if total_buy_cost > 0 and total_buy_cost > cash:
                # 现金不够, 按比例缩减
                scale = cash / total_buy_cost
                scaled_buys = []
                for sym, bq, p in buys:
                    scaled_qty = int((bq * scale) // _lot_size(sym)[1]) * _lot_size(sym)[1]
                    if scaled_qty >= _lot_size(sym)[0]:
                        scaled_buys.append((sym, scaled_qty, p))
                buys = scaled_buys
            
            # Step F: 执行买入
            for sym, buy_qty, px in buys:
                if buy_qty <= 0:
                    continue
                cost = buy_qty * px
                if cost <= cash + 0.01:  # 容许浮点误差
                    cash -= cost
                    positions[sym] = (buy_qty + positions.get(sym, (0, 0))[0], px)
                    trade_log.append({
                        'date': date_str, 'symbol': sym, 'side': 'BUY',
                        'qty': buy_qty, 'price': round(px, 2),
                        'amount': round(cost, 2)
                    })
            
            signal_idx += 1
        
        # ── 计算当日净值 ──
        total_equity = cash
        pos_snapshot = {'date': date_str, 'holdings': []}
        for sym, (qty, cost) in positions.items():
            px = safe_price(sym, i, i - 1)
            if px > 0:
                total_equity += qty * px
                pos_snapshot['holdings'].append({
                    'symbol': sym, 'qty': qty, 'price': round(float(px), 2),
                    'cost': round(float(cost), 2)
                })
        
        navs.append(total_equity)
        nav_dates.append(date_str)
        
        if pos_snapshot['holdings']:
            position_snapshots.append(pos_snapshot)
    
    # 性能指标
    metrics = compute_metrics_qlib(navs, init_cash)
    
    print(f"  ✅ 终值: {navs[-1]:,.0f}  年化: {metrics['annual_return']:.2f}%  "
          f"夏普: {metrics['sharpe']:.2f}  回撤: {metrics['max_drawdown']:.2f}%")
    print(f"  交易: {len(trade_log)} 笔")
    
    return nav_dates, navs, trade_log, position_snapshots, metrics


def compute_metrics_qlib(navs, init_cash):
    """计算绩效指标 (与bt_shared.py一致)"""
    navs = np.array(navs)
    
    if len(navs) < 2:
        return {'annual_return': 0, 'sharpe': 0, 'max_drawdown': 0,
                'calmar': 0, 'sortino': 0, 'volatility': 0,
                'total_return': 0, 'win_rate': 0}
    
    rets = np.diff(navs) / navs[:-1]
    total_return = (navs[-1] / navs[0] - 1) * 100
    
    # 年化收益
    years = len(navs) / 252
    if years > 0:
        annual_return = ((navs[-1] / navs[0]) ** (1 / years) - 1) * 100
    else:
        annual_return = 0
    
    # 夏普
    if len(rets) > 0 and np.std(rets) > 0:
        sharpe = np.mean(rets) / np.std(rets) * np.sqrt(252)
    else:
        sharpe = 0
    
    # 最大回撤
    peak = np.maximum.accumulate(navs)
    dd = (navs - peak) / peak * 100
    max_drawdown = abs(float(np.min(dd)))
    
    # 波动率
    volatility = float(np.std(rets) * np.sqrt(252)) * 100 if len(rets) > 0 else 0
    
    # Calmar
    calmar = annual_return / max_drawdown if max_drawdown > 0 else 0
    
    # Sortino
    neg_rets = rets[rets < 0]
    if len(neg_rets) > 0 and np.std(neg_rets) > 0:
        sortino = np.mean(rets) / np.std(neg_rets) * np.sqrt(252)
    else:
        sortino = 0
    
    # 胜率
    if len(rets) > 0:
        win_rate = float(np.sum(rets > 0) / len(rets)) * 100
    else:
        win_rate = 0
    
    return {
        'annual_return': round(annual_return, 2),
        'sharpe': round(sharpe, 2),
        'max_drawdown': round(max_drawdown, 2),
        'calmar': round(calmar, 2),
        'sortino': round(sortino, 2),
        'volatility': round(volatility, 2),
        'total_return': round(total_return, 2),
        'win_rate': round(win_rate, 2),
    }


# ============================================================
# Main
# ============================================================

INITIAL_CASH = 1_000_000

if __name__ == "__main__":
    print("=" * 60)
    print("▶ Qlib 回测 — 红利v6 策略")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  数据盘: D:/  (不在C盘写入)")
    
    kline_path = f"{DATA_DIR}/kline_adj.parquet"
    
    # 加载K线
    kline = pd.read_parquet(kline_path, columns=['symbol', 'trade_date'])
    if kline['trade_date'].dtype.name == 'uint16':
        kline['trade_date'] = pd.to_datetime(kline['trade_date'], unit='D', origin='unix')
    print(f"  K线: {kline['trade_date'].min().date()} → {kline['trade_date'].max().date()}")
    
    # 生成信号
    signal_map, sorted_dates = generate_signals(kline)
    all_syms = set()
    for w in signal_map.values():
        all_syms.update(w.keys())
    print(f"  信号日: {len(sorted_dates)} 次调仓, 涉及 {len(all_syms)} 只股票")
    
    # 转换数据
    qlib_syms, qlib_dates = convert_to_qlib(list(all_syms), kline_path)
    del kline
    
    # Qlib 回测
    dates, navs, trade_log, positions, metrics = backtest_qlib(
        signal_map, sorted_dates, INITIAL_CASH
    )
    
    if not navs:
        print("❌ 无净值")
        exit(1)
    
    # 去重交易
    seen = set()
    deduped_trades = []
    for t in trade_log:
        key = (t['date'], t['symbol'], t['side'], t['price'], t['qty'])
        if key not in seen:
            seen.add(key)
            deduped_trades.append(t)
    
    # 输出JSON (与Backtrader格式一致)
    nav_history = [{"date": d, "nav": round(v, 2), "is_simulation": False}
                   for d, v in zip(dates, navs)]
    
    strategy = {
        "id": "dividend_yield_v6",
        "name": "红利策略v6(Qlib引擎)",
        "source": "Qlib A股引擎",
        "start_date": nav_history[0]['date'],
        "end_date": nav_history[-1]['date'],
        **metrics,
        "rebalance": "1月/7月",
        "nav_history": nav_history,
        "benchmark_nav": [1.0] * len(nav_history),
        "position_snapshots": positions,
        "trade_log": deduped_trades,
        "monthly_trades": [],
    }
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "dividend_yield_v6_qlib.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"strategies": [strategy], "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                   "engine": "qlib"},
                  f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存: {json_path}")
    
    # 对比
    print("\n" + "=" * 50)
    print("对比 Backtrader vs Qlib:")
    bt_json = os.path.join(OUTPUT_DIR, "dividend_yield_v6.json")
    if os.path.exists(bt_json):
        with open(bt_json, 'r', encoding='utf-8') as f:
            bt_data = json.load(f)
        bt_metrics = bt_data['strategies'][0]
        print(f"  Backtrader: 年化 {bt_metrics.get('annual_return','?')}%, "
              f"夏普 {bt_metrics.get('sharpe','?')}")
    print(f"  Qlib:       年化 {metrics['annual_return']}%, "
          f"夏普 {metrics['sharpe']}")
    
    print("\n✅ Qlib 回测完成!")
