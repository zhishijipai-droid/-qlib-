"""
Qlib 红利v6 回测 — 使用真实 Qlib backtest() 引擎

架构:
  1. qlib.init() 注册本地数据
  2. 从现有策略生成 signal_map (date → {symbol: weight})
  3. 构建 WeightStrategyBase 子类 DivV6Strategy
  4. 调用 qlib.backtest.backtest() 执行回测
  5. 输出与 Backtrader 相同的 JSON 格式
"""
import sys, os, json, copy
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import qlib
from qlib.config import REG_CN
from qlib.backtest import backtest
from qlib.backtest.decision import TradeDecisionWO, Order
from qlib.contrib.strategy.signal_strategy import WeightStrategyBase
from qlib.contrib.strategy.order_generator import OrderGenWOInteract

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
QLIB_DIR = "D:/bigquant/qlib_data/div_v6"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

# ============================================================
# Step 1: 初始化 Qlib
# ============================================================
print("=" * 50)
print("[Qlib] 初始化...")
# Windows 下禁用 joblib 多进程 (需 __main__ guard), 改用 threading
qlib.init(provider_uri=QLIB_DIR, region=REG_CN, kernels=1,
           joblib_backend="threading", maxtasksperchild=None)
from qlib.data import D

cal = D.calendar()
print(f"  日历: {len(cal)} 天, {cal[0].date()} → {cal[-1].date()}")

# ============================================================
# Step 2: 生成信号 (复用现有策略)
# ============================================================
print("\n[Qlib] 生成信号...")
kline = pd.read_parquet(os.path.join(DATA_DIR, "kline_adj.parquet"), 
                        columns=['symbol', 'trade_date'])
from strategies.dividend_yield_v6 import get_signals as div_fn

all_dates = sorted(kline['trade_date'].unique())
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
    result = div_fn(day_data[['symbol', 'trade_date']])
    if result is not None and len(result) > 0:
        weights = dict(zip(result['symbol'], result['weight']))
        date_str = d.strftime('%Y-%m-%d')
        signal_map[date_str] = weights
        sorted_dates.append(date_str)

print(f"  有效信号日: {len(sorted_dates)} 个")
print(f"  范围: {sorted_dates[0]} → {sorted_dates[-1]}")

# ============================================================
# Step 3: 构建 Qlib Signal
# ============================================================
# Qlib Signal 格式: MultiIndex(datetime, instrument) → value
signal_records = []
for date_str, weights in signal_map.items():
    dt = pd.Timestamp(date_str)
    for sym, w in weights.items():
        signal_records.append({'datetime': dt, 'instrument': sym, 'weight': w})

signal_series = pd.DataFrame(signal_records).set_index(['datetime', 'instrument'])['weight']
print(f"\n  信号: {len(signal_series)} 条, {signal_series.index.get_level_values('instrument').nunique()} 只股票")

# ============================================================
# Step 4: 自定义策略
# ============================================================
class DivV6Strategy(WeightStrategyBase):
    """红利v6策略 — 半年度调仓, 按目标权重买入"""
    
    def __init__(self, *, rebalance_dates, signal_map, **kwargs):
        super().__init__(
            signal=signal_series,
            order_generator_cls_or_obj=OrderGenWOInteract,
            **kwargs
        )
        self.rebalance_dates = set(rebalance_dates)
        self._signal_map = signal_map
    
    def generate_target_weight_position(self, score, current, trade_start_time, trade_end_time):
        """将信号分数转为目标权重 (我们的分数就是权重)"""
        if score is None or len(score) == 0:
            return {}
        return score.to_dict()
    
    def generate_trade_decision(self, execute_result=None):
        """只在调仓日生成订单"""
        trade_step = self.trade_calendar.get_trade_step()
        trade_start_time, trade_end_time = self.trade_calendar.get_step_time(trade_step)
        date_str = trade_start_time.strftime('%Y-%m-%d')
        
        if date_str not in self.rebalance_dates:
            return TradeDecisionWO([], self)
        
        # 在调仓日当天使用信号 (shift=0)
        pred_score = self.signal.get_signal(start_time=trade_start_time, end_time=trade_end_time)
        if pred_score is None:
            return TradeDecisionWO([], self)
        
        current_temp = copy.deepcopy(self.trade_position)
        
        target_weight_position = self.generate_target_weight_position(
            score=pred_score, current=current_temp, 
            trade_start_time=trade_start_time, trade_end_time=trade_end_time
        )
        
        order_list = self.order_generator.generate_order_list_from_target_weight_position(
            current=current_temp,
            trade_exchange=self.trade_exchange,
            risk_degree=self.get_risk_degree(trade_step),
            target_weight_position=target_weight_position,
            pred_start_time=trade_start_time,
            pred_end_time=trade_end_time,
            trade_start_time=trade_start_time,
            trade_end_time=trade_end_time,
        )
        return TradeDecisionWO(order_list, self)

# ============================================================
# Step 5: 运行回测
# ============================================================
print("\n" + "=" * 50)
print("[Qlib] 回测中...")

# 将信号日期的第一个往前挪几天，确保 Exchange 能初始化
start_dt = pd.Timestamp(sorted_dates[0])
end_dt = pd.Timestamp(sorted_dates[-1])

# 回测参数 (匹配 Backtrader)
INIT_CASH = 1_000_000.0

# 使用第一个可用股票作为benchmark, SH000300 不在我们的数据中
benchmark = sorted(signal_map.get(sorted_dates[0], {}).keys())[0] if signal_map else None
portfolio_dict, indicator_dict = backtest(
    start_time=start_dt,
    end_time=end_dt,
    strategy=DivV6Strategy(rebalance_dates=sorted_dates, signal_map=signal_map),
    executor={
        "class": "SimulatorExecutor",
        "module_path": "qlib.backtest.executor",
        "kwargs": {
            "time_per_step": "day",
            "generate_portfolio_metrics": True,
        }
    },
    benchmark=benchmark,
    account=INIT_CASH,
    exchange_kwargs={
        "freq": "day",
        "codes": "all",
        "deal_price": "$close",
        "limit_threshold": 0.1,
        "open_cost": 0.0005,    # 买入成本 0.05%
        "close_cost": 0.0015,   # 卖出成本 0.15% (含印花税)
        "min_cost": 5.0,
        "trade_unit": 100,      # A股手数
    },
    pos_type="Position",
)

print(f"  回测完成!")
print(f"  portfolio_dict keys: {list(portfolio_dict.keys())}")
print(f"  indicator_dict keys: {list(indicator_dict.keys())}")

# ============================================================
# Step 6: 提取结果
# ============================================================
assert "1day" in portfolio_dict, f"Expected '1day' in portfolio_dict, got keys: {list(portfolio_dict.keys())}"
port_df, port_info = portfolio_dict["1day"]

print(f"\n  Portfolio columns: {list(port_df.columns)}")
print(f"  Portfolio shape: {port_df.shape}")
print(f"  Portfolio info: {port_info}")

# 提取净值曲线
if "total_value" in port_df.columns:
    nav_series = port_df["total_value"]
elif "value" in port_df.columns:
    nav_series = port_df["value"]
else:
    print(f"  Columns: {list(port_df.columns)}")
    nav_series = port_df.iloc[:, 0]  # fallback

nav_list = []
for idx, val in nav_series.items():
    # idx is a pd.Timestamp if portfolio_df uses datetime index
    if hasattr(idx, 'strftime'):
        date_str = idx.strftime('%Y-%m-%d')
    else:
        date_str = str(idx)[:10]
    nav_list.append({
        "date": date_str,
        "nav": round(float(val), 2),
    })

print(f"  NAV points: {len(nav_list)}")
print(f"  首日 NAV: {nav_list[0]['nav']}, 末日 NAV: {nav_list[-1]['nav']}")

# 计算 KPI
navs = np.array([p["nav"] for p in nav_list])
if len(navs) >= 2:
    daily_ret = navs[1:] / navs[:-1] - 1
    ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
    ann_ret = float(navs[-1] / navs[0]) ** (252.0 / len(navs)) - 1
    sharpe = float(np.mean(daily_ret) / np.std(daily_ret, ddof=1) * np.sqrt(252)) if ann_vol > 0 else 0
    peak = np.maximum.accumulate(navs)
    mdd = float(np.min((navs - peak) / peak))
else:
    ann_vol, ann_ret, sharpe, mdd = 0, 0, 0, 0

print(f"\n  年化收益: {ann_ret*100:.2f}%")
print(f"  夏普比率: {sharpe:.2f}")
print(f"  最大回撤: {mdd*100:.2f}%")
print(f"  年化波动: {ann_vol*100:.2f}%")

# 提取交易记录
ind_df, ind_obj = indicator_dict.get("1day", (pd.DataFrame(), None))
trades = []
if ind_df is not None and len(ind_df) > 0:
    print(f"\n  Trade indicators: {len(ind_df)} rows")
    print(f"  Indicator columns: {list(ind_df.columns)}")

# ============================================================
# Step 7: 输出 JSON
# ============================================================
output = {
    "strategies": [{
        "id": "dividend_yield_v6_qlib",
        "name": "红利策略v6(Qlib引擎)",
        "source": "Qlib backtest engine",
        "start_date": nav_list[0]["date"],
        "end_date": nav_list[-1]["date"],
        "annual_return": round(ann_ret * 100, 2),
        "total_return": round((navs[-1] / navs[0] - 1) * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(abs(mdd) * 100, 2),
        "annual_vol": round(ann_vol * 100, 2),
        "initial_cash": INIT_CASH,
        "rebalance": "semi_annual",
        "nav_history": nav_list,
        "benchmark_nav": [],
        "position_snapshots": [],
        "trade_log": trades,
        "monthly_trades": [],
    }]
}

json_path = os.path.join(OUTPUT_DIR, "dividend_yield_v6_qlib.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n  ✅ JSON saved: {json_path}")

print("\n✅ Qlib 回测完成!")
