"""
🚀 运行所有策略回测

用法:
  python run_all.py                       # 全量回测
  python run_all.py --freq 10            # 每10天调仓 (默认5)
  python run_all.py --name momentum      # 只跑特定策略
"""
import os, sys, argparse
sys.path.insert(0, os.path.dirname(__file__))

from config import STRATEGY_DIR
from engine.backtest import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量回测")
    parser.add_argument("--freq", type=int, default=5,
                        help="调仓频率 (交易日数, 默认5=周频)")
    args = parser.parse_args()

    main()
