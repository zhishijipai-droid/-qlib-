"""
Backtrader 回测引擎测试
"""
import unittest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from factor import compute


class TestFactor(unittest.TestCase):
    def test_compute_on_synthetic_data(self):
        """用合成数据验证因子计算"""
        dates = pd.date_range("2024-01-01", periods=30, freq="B")
        records = []
        for code, base_price in [("000001", 10.0), ("000002", 20.0), ("000003", 30.0)]:
            for i, date in enumerate(dates):
                records.append({
                    "date": date,
                    "code": code,
                    "close": base_price * (1 + i * 0.01),
                    "open": base_price * (1 + i * 0.01 - 0.005),
                    "high": base_price * (1 + i * 0.01 + 0.01),
                    "low": base_price * (1 + i * 0.01 - 0.01),
                    "volume": 1000000 + i * 50000,
                    "amount": 10000000 + i * 500000,
                })

        panel = pd.DataFrame(records)
        result = compute(panel)

        self.assertEqual(len(result), len(panel))
        self.assertTrue(result.notna().sum() > 0, "因子至少应产生一些有效值")

    def test_no_crash_on_edge_cases(self):
        """边界情况不崩溃"""
        panel = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=3, freq="B"),
            "code": ["000001", "000001", "000001"],
            "close": [10.0, 10.5, 10.0],
            "open": [10.0, 10.0, 10.0],
            "high": [10.1, 10.6, 10.1],
            "low": [9.9, 10.4, 9.9],
            "volume": [1000000, 1000000, 1000000],
            "amount": [10000000, 10500000, 10000000],
        })

        result = compute(panel)
        self.assertEqual(len(result), 3)

    def test_all_null_on_short_data(self):
        """数据不足时返回全 NaN（不会崩溃）"""
        panel = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "code": ["000001"] * 5,
            "close": [10.0, 10.1, 10.2, 10.3, 10.4],
            "open": [10.0] * 5,
            "high": [10.1] * 5,
            "low": [9.9] * 5,
            "volume": [1000000] * 5,
            "amount": [10000000] * 5,
        })

        result = compute(panel)
        self.assertEqual(len(result), 5)


if __name__ == "__main__":
    unittest.main()
