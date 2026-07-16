# 回测数据更新 & 策略网站发布

## 目录
- `D:/bigquant/custom_engine/` — 回测引擎 + 策略
- `D:/bigquant/custom_engine/data/` — 数据(Parquet)
- `D:/bigquant/custom_engine/strategies/` — 策略模块
- `D:/bigquant/custom_engine/engine/` — 引擎核心
- `D:/bigquant/output/strategy.html` — 网页
- `D:/bigquant/output/*.json` — 策略数据

## 三步更新网站

### 1. 跑回测生成新数据
```bash
cd /d/bigquant/custom_engine

# 小市值 + 微盘股
python rerun_both.py

# 红利策略v6 (如果有修改)
python rerun_dividend_v6.py   # 需要先创建此脚本
# 或直接用:
python -c "
from engine.backtest import BacktestEngine
from strategies.dividend_yield_v6 import get_signals
e=BacktestEngine()
n,m=e.run_strategy(get_signals, '红利策略v6', 126)
# 然后用 rerun_dividend_v5.py 的模板生成JSON
"
```

### 2. 更新网页
```bash
cd /d/bigquant/custom_engine
python update_all_strats.py
```

### 3. 启动/刷新HTTP服务器
```bash
# 如果没启动:
cd /d/bigquant/output && python -m http.server 8091
# 浏览器访问: http://192.168.1.145:8091/strategy.html
```

## 添加新策略

1. 在 `strategies/` 下创建 `your_strategy.py`，实现 `get_signals(data) -> DataFrame`
2. 写一个类似 `rerun_dividend_v5.py` 的生成脚本
3. 通过 `update_all_strats.py` 或手动修改 HTML 中的 M3/DATES3/NAV3/PS3 数据
4. 更新 `sl` 数组（策略列表）和 `od()` 函数（详情页切换）

## 成本设置
在 `config.py` 中:
```python
TRADE_FEE_RATE = 0.0003  # 手续费万3 (双边)
SLIPPAGE = 0.001          # 滑点0.1%
ST_TAX_RATE = 0.001       # 印花税千1 (卖出)
```

## 数据源
- 雷菱API: `http://115.159.73.134:8765`
- 日K线: `ods_kline_1d` → `kline_1d.parquet`
- 股息率: 现金流量表 `CASH_PAY_DIST_DIV_PRO_INT` → 按负债率扣除利息
- 财务: 资产负债表 + 利润表

## 关键脚本
| 脚本 | 作用 |
|------|------|
| `engine/backtest.py` | 回测引擎核心 |
| `precompute_div_yield_v2.py` | 预计算股息率(修正版) |
| `rerun_both.py` | 小市值+微盘股回测 |
| `rerun_dividend_v5.py` | 红利v5回测 (含完整JSON生成) |
| `update_all_strats.py` | 替换HTML中的M1/M2/M3数据 |
| `add_portfolio_panel.py` | 组合配置面板(一次性) |

## 网页结构
- 4个视图: 策略列表、详情、持仓调仓、组合配置
- 3个策略: 小市值(M1)、微盘股(M2)、红利v6(M3)
- 数据硬编码在HTML里: NAV1/2/3, DATES1/2/3, PS1/2/3, TRADES1/2/3

## 对齐聚宽的注意事项
- 股息率要用 `dividend_yield_v2.parquet` (已扣除利息)
- 调仓频率126个交易日≈半年
- 板块取整规则: 688=200股起, 8xxxx=100股起, 其他=100股整数倍
- 聚宽成本: 万3双边+千1印花税+滑点0.1%
