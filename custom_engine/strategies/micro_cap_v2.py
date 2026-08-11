"""
微盘股 v2 — 股息率加权版

与 v1 的区别:
  v1: 市值最小 400 只, 等权
  v2: 市值最小 500 只 → 股息率筛选 → 取最高 100 只 → 按股息率加权

计算逻辑 (经典小盘价值):
  1. 全市场按市值升序, 取最小 500 只
  2. 从中筛选有股息率的股票
  3. 按股息率降序, 取前 100 只
  4. 权重 = 个股股息率 / 总和（股息率越高权重越大）

调仓频率: 月频 (每 21 个交易日)
"""

import os
import pandas as pd
import numpy as np

STRATEGY_NAME = "微盘股v2(股息加权)"

# 模块级缓存
_MC_DATE_MAP = None
_DY_MAP = None  # {date_str: {symbol: div_yield}}


def _load_market_cap():
    """加载市值数据索引"""
    global _MC_DATE_MAP
    if _MC_DATE_MAP is not None:
        return _MC_DATE_MAP

    path = os.path.join(os.path.dirname(__file__), "..", "data", "market_cap_full.parquet")
    if not os.path.exists(path):
        print(f"  [微盘v2] 市值数据不存在: {path}")
        return None

    df = pd.read_parquet(path)
    df = df.reset_index()
    df['symbol'] = df['order_book_id'].str.replace('.XSHE', '.SZ').str.replace('.XSHG', '.SH')
    df['mc_yi'] = df['market_cap'] / 1e8
    date_map = {
        str(d): dict(zip(grp['symbol'], grp['mc_yi']))
        for d, grp in df.groupby(df['date'].dt.strftime('%Y-%m-%d'))
    }
    _MC_DATE_MAP = date_map
    print(f"  [微盘v2] 市值数据已加载: {len(date_map)}天")
    return date_map


def _load_dividend():
    """加载股息率数据索引"""
    global _DY_MAP
    if _DY_MAP is not None:
        return _DY_MAP

    path = os.path.join(os.path.dirname(__file__), "..", "data", "dividend_yield_v2.parquet")
    if not os.path.exists(path):
        path2 = os.path.join(os.path.dirname(__file__), "..", "data", "dividend_yield.parquet")
        if not os.path.exists(path2):
            print(f"  [微盘v2] 股息率数据不存在")
            return None
        dy = pd.read_parquet(path2)
    else:
        dy = pd.read_parquet(path)

    dy['date'] = pd.to_datetime(dy['date'])
    _DY_MAP = {}
    for d, grp in dy.groupby('date'):
        _DY_MAP[str(d.date())] = dict(zip(grp['symbol'], grp['div_yield']))
    print(f"  [微盘v2] 股息率数据已加载: {len(_DY_MAP)}天")
    return _DY_MAP


def get_signals(data):
    """
    微盘股 v2 股息率加权策略

    data: DataFrame with columns ['symbol', 'trade_date']
    返回: DataFrame with columns ['symbol', 'weight']
    """
    mc_map = _load_market_cap()
    dy_map = _load_dividend()
    if mc_map is None or dy_map is None:
        return pd.DataFrame(columns=['symbol', 'weight'])

    trade_date = str(data['trade_date'].iloc[0])[:10]
    symbols = data['symbol'].tolist()

    # ── 1. 获取市值, 取最小 500 只 ──
    dates = sorted(mc_map.keys())
    if trade_date < dates[0]:
        return pd.DataFrame(columns=['symbol', 'weight'])
    valid_dates = [d for d in dates if d <= trade_date]
    latest_date = valid_dates[-1] if valid_dates else dates[-1]
    date_mc = mc_map[latest_date]

    mc_rows = []
    for sym in symbols:
        mc = date_mc.get(sym)
        if mc is not None and mc > 0:
            mc_rows.append({'symbol': sym, 'market_cap': mc})

    if len(mc_rows) < 500:
        return pd.DataFrame(columns=['symbol', 'weight'])

    mc_df = pd.DataFrame(mc_rows).sort_values('market_cap').head(500)
    small_syms = set(mc_df['symbol'])

    # ── 2. 获取股息率 ──
    dy_dates = sorted(dy_map.keys())
    valid_dy = [d for d in dy_dates if d <= trade_date]
    if not valid_dy:
        return pd.DataFrame(columns=['symbol', 'weight'])
    latest_dy_date = valid_dy[-1]
    date_dy = dy_map[latest_dy_date]

    # ── 3. 微盘 ∩ 有股息率 ──
    rows = []
    for sym in small_syms:
        dy_val = date_dy.get(sym)
        if dy_val is not None and dy_val > 0:
            rows.append({'symbol': sym, 'div_yield': dy_val})

    if len(rows) < 30:
        # 股息率覆盖不够, 回退到等权
        print(f"  [微盘v2] 股息率候选不足 ({len(rows)}只), 回退等权")
        result = mc_df.head(400)
        n = len(result)
        return pd.DataFrame({
            'symbol': result['symbol'].values,
            'weight': 1.0 / n,
        })

    result = pd.DataFrame(rows)

    # ── 4. 取股息率最高的 100 只 ──
    result = result.sort_values('div_yield', ascending=False).head(100)

    # ── 5. 按股息率加权 ──
    total_dy = result['div_yield'].sum()
    weights = result['div_yield'] / total_dy

    return pd.DataFrame({
        'symbol': result['symbol'].values,
        'weight': weights,
    })
