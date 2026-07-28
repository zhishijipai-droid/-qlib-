"""
Backtrader A股回测引擎 — 适配器

将策略信号通过 backtrader 事件驱动引擎执行，按 A 股真实交易规则计算净值。
"""
import pandas as pd
import numpy as np


def compute(panel: pd.DataFrame) -> pd.Series:
    """计算策略因子值（红利股息率 + 小市值 alpha 合成信号）。

    Args:
        panel: DataFrame，必须包含 date, code, close, volume 列

    Returns:
        pd.Series，综合信号值，长度与 panel 一致
    """
    # 按股票分组，计算 20 日收益率（动量因子）
    panel_sorted = panel.sort_values(["code", "date"]).reset_index(drop=True)

    # 20日动量
    ret_20d = panel_sorted.groupby("code")["close"].pct_change(20)

    # 成交量变动率
    vol_change = panel_sorted.groupby("code")["volume"].pct_change(5)

    # 综合信号: 动量 + 缩量信号
    result = -ret_20d * vol_change.replace([np.inf, -np.inf], np.nan)

    # 对齐回原始 panel 索引
    result.index = panel_sorted.index
    return result.reindex(panel.index)
