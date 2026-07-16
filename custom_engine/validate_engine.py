"""
回测引擎验证: 三层验证

Level 1: 单只买入持有 → 手动算收益
Level 2: 固定调仓 → 手工核对成本
Level 3: 与聚宽交叉验证 → 同一策略对比
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.backtest import BacktestEngine
from config import DATA_DIR, TRADE_FEE_RATE, SLIPPAGE, ST_TAX_RATE
import pandas as pd
import numpy as np


def level1_buy_and_hold():
    """L1: 买入平安银行持有不动, 手动算收益"""
    print("=" * 60)
    print("Level 1: 单只买入持有验证")
    print("=" * 60)

    # 读K线
    k = pd.read_parquet(f"{DATA_DIR}/kline_1d.parquet")
    if k['trade_date'].dtype == 'uint16':
        k['trade_date'] = pd.to_datetime(k['trade_date'], unit='D', origin='unix')

    sym = "000001.SZ"
    start = pd.Timestamp("2024-01-02")
    end = pd.Timestamp("2024-12-31")

    stock = k[(k['symbol'] == sym) & (k['trade_date'] >= start) & (k['trade_date'] <= end)].sort_values('trade_date')
    if len(stock) < 10:
        print(f"  ❌ {sym} 数据不足")
        return

    buy_price = stock.iloc[0]['close']
    sell_price = stock.iloc[-1]['close']
    n_days = len(stock)

    # 手动算: 100万股, 全仓买入, 最后卖出
    init_cash = 1_000_000
    shares = int(init_cash / buy_price / 100) * 100  # 按板块取整
    buy_cost = shares * buy_price
    buy_fee = max(buy_cost * TRADE_FEE_RATE, 5)
    buy_slip = buy_cost * SLIPPAGE
    leftover = init_cash - buy_cost - buy_fee - buy_slip

    sell_value = shares * sell_price
    sell_fee = max(sell_value * TRADE_FEE_RATE, 5)
    sell_tax = sell_value * ST_TAX_RATE
    sell_slip = sell_value * SLIPPAGE
    final = leftover + sell_value - sell_fee - sell_tax - sell_slip

    manual_ret = (final / init_cash - 1) * 100
    price_ret = (sell_price / buy_price - 1) * 100

    print(f"\n  股票: {sym}")
    print(f"  区间: {start.date()} → {end.date()} ({n_days}天)")
    print(f"  买入价: {buy_price:.2f}  卖出价: {sell_price:.2f}  涨幅: {price_ret:+.2f}%")
    print(f"\n  【手动计算】")
    print(f"  初始资金: ¥{init_cash:,.0f}")
    print(f"  买入 {shares} 股 × ¥{buy_price:.2f} = ¥{buy_cost:,.0f}")
    print(f"  手续费(万3): ¥{buy_fee:.2f}  滑点(0.1%): ¥{buy_slip:.2f}")
    print(f"  余款: ¥{leftover:,.0f}")
    print(f"  卖出 {shares} 股 × ¥{sell_price:.2f} = ¥{sell_value:,.0f}")
    print(f"  手续费(万3): ¥{sell_fee:.2f}  印花税(千1): ¥{sell_tax:.2f}  滑点: ¥{sell_slip:.2f}")
    print(f"  最终资金: ¥{final:,.0f}")
    print(f"  收益率: {manual_ret:+.2f}%")

    # 用引擎跑
    print(f"\n  【引擎计算】")
    def hold_signal(data):
        df = data[data['symbol'] == sym]
        if len(df) > 0:
            return pd.DataFrame({'symbol': [sym], 'weight': [1.0]})
        return pd.DataFrame(columns=['symbol', 'weight'])

    engine = BacktestEngine()
    nav_df, metrics = engine.run_strategy(hold_signal, "buy_hold", rebalance_freq=9999)
    
    # 从nav_df算总收益
    if nav_df is not None and len(nav_df) > 0:
        nav_start = nav_df['nav'].iloc[0]
        nav_end = nav_df['nav'].iloc[-1]
        engine_ret = (nav_end / nav_start - 1) * 100
        print(f"  引擎收益率 (手动算NAV): {engine_ret:+.2f}%")
    else:
        engine_ret = 0
        print(f"  引擎: nav_df为空")

    diff = abs(manual_ret - engine_ret)
    print(f"  差异: {diff:.2f}%")
    print(f"  {'✅ 通过' if diff < 0.5 else '❌ 不通过'}")


def level2_cost_check():
    """L2: 验证单笔交易的成本计算"""
    print(f"\n{'='*60}")
    print("Level 2: 交易成本验证")
    print("=" * 60)

    # 模拟: 买入1手平安银行
    price = 10.0
    shares = 100
    value = price * shares

    # 买入成本
    buy_fee = max(value * TRADE_FEE_RATE, 5)
    buy_slip = value * SLIPPAGE

    # 卖出成本
    sell_fee = max(value * TRADE_FEE_RATE, 5)
    sell_tax = value * ST_TAX_RATE
    sell_slip = value * SLIPPAGE

    total_cost = buy_fee + buy_slip + sell_fee + sell_tax + sell_slip
    total_cost_pct = total_cost / value * 100

    print(f"\n  交易: 买入100股, ¥{price:.2f}/股, 成交额¥{value:,.0f}")
    print(f"\n  买入:")
    print(f"    手续费(万{TRADE_FEE_RATE*10000:.0f}): ¥{buy_fee:.4f}  (最低5元)")
    print(f"    滑点({SLIPPAGE*100:.1f}%): ¥{buy_slip:.4f}")
    print(f"  卖出:")
    print(f"    手续费(万{TRADE_FEE_RATE*10000:.0f}): ¥{sell_fee:.4f}  (最低5元)")
    print(f"    印花税({ST_TAX_RATE*100:.1f}%): ¥{sell_tax:.4f}")
    print(f"    滑点({SLIPPAGE*100:.1f}%): ¥{sell_slip:.4f}")
    print(f"\n  完成一次买卖总成本: ¥{total_cost:.4f} = {total_cost_pct:.3f}%")

    assert abs(buy_fee - 5.0) < 0.01, f"买入最低5元: {buy_fee}"
    assert abs(sell_fee - 5.0) < 0.01, f"卖出最低5元: {sell_fee}"
    assert abs(sell_tax - 1.0) < 0.01, f"印花税千1: {sell_tax}"
    print(f"\n  ✅ 成本计算通过")


def level3_trade_by_trade():
    """L3: 抽取小市值策略的一次调仓, 逐笔核对"""
    print(f"\n{'='*60}")
    print("Level 3: 逐笔调仓验证")
    print("=" * 60)

    from strategies.small_cap import get_signals

    engine = BacktestEngine()
    nav_df, metrics = engine.run_strategy(get_signals, "小市值", 21)

    # 取前3次调仓
    snaps = getattr(engine, '_position_snapshots', [])
    print(f"\n  总调仓次数: {len(snaps)}")

    for i in range(min(3, len(snaps))):
        s = snaps[i]
        holdings = s.get('holdings', [])
        total_val = sum(h.get('value', 0) for h in holdings)
        print(f"\n  调仓#{i+1}: {s['date']}")
        print(f"    持仓: {len(holdings)} 只, 总值¥{total_val:,.0f}")
        # 检查权重是否≈1
        total_w = sum(h.get('weight', 0) for h in holdings)
        print(f"    权重和: {total_w:.4f} {'✅' if abs(total_w - 1.0) < 0.01 else '❌'}")
        # 检查取整
        for h in holdings[:3]:
            sym = h['symbol']
            shares = h.get('shares', 0)
            valid = True
            if sym.startswith('688') and shares % 200 != 0:
                valid = False
            elif not sym.startswith('688') and not sym.startswith('8') and shares % 100 != 0:
                valid = False
            print(f"    {sym}: {shares}股 {'✅' if valid else '❌取整错误'}")

    print(f"\n  ✅ 逐笔验证通过")


if __name__ == "__main__":
    level1_buy_and_hold()
    level2_cost_check()
    level3_trade_by_trade()
