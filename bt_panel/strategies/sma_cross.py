"""BT Panel 示例策略: 均线交叉"""
import backtrader as bt


class SmaCross(bt.Strategy):
    params = (
        ('fast', 5),
        ('slow', 20),
    )

    def __init__(self):
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.cross = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        self.trades = []

    def next(self):
        if not self.position:
            if self.cross > 0:
                self.buy()
                self.trades.append({
                    'date': str(self.data.datetime.date()),
                    'symbol': self.data._name,
                    'action': 'BUY',
                    'price': round(self.data.close[0], 2),
                })
        elif self.cross < 0:
            self.sell()
