"""添加今日信号到strategy.html作为第4个策略"""
import json

html_path = "D:/bigquant/output/strategy.html"
signal_path = "D:/bigquant/output/current_signal.json"

with open(signal_path, encoding="utf-8") as f:
    signal = json.load(f)['strategies'][0]

with open(html_path, encoding="utf-8") as f:
    html = f.read()

# 从信号数据构建M4对象
sig = signal
M4 = {
    "id": "current_signal",
    "name": "今日信号",
    "description": f"日池+周池, {sig['n_holdings']}只",
    "annual_return": sig.get('annual_return', 0),
    "total_return": sig.get('total_return', 0),
    "sharpe": sig.get('sharpe', 0),
    "sortino": sig.get('sortino', 0),
    "max_drawdown": sig.get('max_drawdown', 0),
    "calmar": sig.get('calmar', 0),
    "annual_vol": sig.get('annual_vol', 0),
    "win_rate": sig.get('win_rate', 0),
    "daily_win_rate": sig.get('daily_win_rate', 0),
    "total_value_10k": sig.get('total_value_10k', 0),
    "rebalance": "每日更新",
    "n_wins": 0, "n_losses": 0, "profit_loss_ratio": 0, "trade_win_rate": "0",
    "signal_holdings": sig['holdings'],
}
M4_STR = json.dumps(M4, ensure_ascii=False)

# 删除已有的PS4/TL4/STRAT_CODE4 (防止重复插入)
for var_name in ['var PS4=', 'var TL4=', 'var STRAT_CODE4=', 'var DATES4=', 'var NAV4=', 'var M4=', 'var TRADES4=', 'var BENCH4=', 'var LOGIC4=']:
    while True:
        idx = html.find(var_name)
        if idx < 0:
            break
        end = html.find(';', idx) + 1
        # 对于PS4=[]这种数组, 找到对应的];
        if var_name == 'var PS4=' or var_name == 'var TRADES4=':
            end = html.find('];', idx) + 2
        elif var_name == 'var M4=':
            end = html.find('};', idx) + 2
        html = html[:idx] + html[end:]

# 找到插入点 (在M3之后)
m3_end = html.find('var M3=')
m3_end = html.find(';', m3_end)
insert_point = m3_end + 1

before = html[:insert_point]
after = html[insert_point:]

dates_str = json.dumps(signal.get('dates', [signal['date']]))
navs_str = json.dumps(signal.get('navs', [1.0]))

new_block = f"""
var DATES4={dates_str};
var NAV4={navs_str};
var M4={M4_STR};
var TRADES4=[];
var BENCH4={json.dumps([round(n, 4) for n in signal.get('navs', [1.0])])};
var LOGIC4="日池+周池信号,基于CSV的交易信号生成,{signal['n_holdings']}只持仓,等权/按信号权重分配";
var PS4=[{{"date":"{signal['date']}","nav":1000000,"holdings":""" + json.dumps([{
    "symbol": h['symbol'],
    "name": h.get('name', ''),
    "weight": h['weight'],
    "shares": h.get('shares', 0),
    "price": h.get('price', 0),
    "cost_price": h.get('cost_price', 0),
    "value": h.get('value', 0),
    "cost_value": h.get('cost_value', 0),
    "pnl": h.get('pnl', 0),
    "pnl_pct": h.get('pnl_pct', 0)
} for h in signal['holdings']], ensure_ascii=False) + """}];
var TL4=[];
var STRAT_CODE4="";
"""

html = before + new_block + after

# 更新sl数组: 添加第4个策略
old_sl = 'ann:0,tot:0,sharpe:0,mdd:0,cal:0,vol:0,wr:0,val:0,reb:"每日更新"}]'
new_sl = 'ann:M4.annual_return,tot:M4.total_return,sharpe:M4.sharpe,mdd:M4.max_drawdown,cal:M4.calmar,vol:M4.annual_vol,wr:M4.win_rate,val:M4.total_value_10k,reb:"每日更新"}]'
html = html.replace(old_sl, new_sl)

# 更新od()函数: 添加第4组数据
old_od = 'var n=[NAV1,NAV2,NAV3],d=[DATES1,DATES2,DATES3],t=[TRADES1,TRADES2,TRADES3],m=[M1,M2,M3],l=[LOGIC1,LOGIC2,LOGIC3],b=[BENCH1,BENCH2,BENCH3];'
new_od = 'var n=[NAV1,NAV2,NAV3,NAV4],d=[DATES1,DATES2,DATES3,DATES4],t=[TRADES1,TRADES2,TRADES3,TRADES4],m=[M1,M2,M3,M4],l=[LOGIC1,LOGIC2,LOGIC3,LOGIC4],b=[BENCH1,BENCH2,BENCH3,BENCH4];'
html = html.replace(old_od, new_od)

# 更新hvRenderPS()
old_ps = 'var pss=[PS1,PS2,PS3];'
new_ps = 'var pss=[PS1,PS2,PS3,PS4];'
html = html.replace(old_ps, new_ps)

# 更新toggleCode()
old_tc = "el.textContent=[STRAT_CODE||'',STRAT_CODE2||'',STRAT_CODE3||''][curStrat];"
new_tc = "el.textContent=[STRAT_CODE||'',STRAT_CODE2||'',STRAT_CODE3||'',STRAT_CODE4||''][curStrat];"
html = html.replace(old_tc, new_tc)

# 更新exportReport切换
# 更新pfInit中的sl引用 (组合配置)
# 这些是动态的, 通过sl.length自动处理, 不需要改

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ 今日信号已添加到策略面板 (第4个策略)")
print(f"   持仓: {signal['n_holdings']} 只")
