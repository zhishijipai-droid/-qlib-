# A股量化策略监控面板

A股量化回测引擎 + 可视化 Dashboard。支持多策略回测对比、持仓分析、调仓明细、实时网页展示。

## 快速开始

```bash
# 安装依赖
pip install pandas numpy

# 跑回测
cd qlib_sim
python rerun_both.py

# 启动网页
cd ../output
python -m http.server 8091
```

访问 http://localhost:8091/strategy.html

## 项目结构

```
qlib_sim/
├── engine/backtest.py   # 回测引擎（ST/退市过滤、滑点、手续费、板块取整规则）
├── strategies/          # 策略（small_cap.py, micro_cap.py）
├── rerun_both.py        # 跑两个策略回测 + 生成JSON数据
├── config.py            # 配置（手续费万6、滑点0.1%、印花税千1）
└── data/                # Parquet数据文件（需自行下载）

output/
├── strategy.html        # 监控面板（单页HTML，数据内嵌）
└── stock_names.json     # 股票名称映射
```

## 交易规则
- 主板/创业板：100股整数倍
- 科创板：200股起，超200可1股递增
- 北交所：100股起，超100可1股递增
- 手续费万6（双边）、滑点0.1%、印花税千1（卖出）
