"""
实时更新模拟 — 先一次跑完全部回测，然后每分钟「揭开」一天

效果: 网页上曲线逐日增长，像实盘一样

用法:
  python simulate_realtime.py
  python simulate_realtime.py --start 2021-03-11 --end 2022-01-01 --interval 60
"""
import os, sys, time, argparse, shutil, json
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import DATA_DIR, RESULTS_DIR, BACKTEST_YEARS, INIT_CAPITAL


def simulate(args):
    # ── 1. 一次性跑完全量回测 ──
    print("=" * 50)
    print(f"阶段1: 全量回测 ({args.start} → {args.end})")
    print("=" * 50)

    from engine.backtest import BacktestEngine
    from strategies import discover_strategies

    strategies = discover_strategies()
    if args.strategy:
        strategies = {k: v for k, v in strategies.items() if args.strategy in k}

    engine = BacktestEngine()

    # 截断日历到模拟结束日期
    engine.calendar = engine.calendar[engine.calendar['trade_date'] <= args.end_date].copy()

    # 跑所有策略，保存完整nav
    all_nav = {}
    all_metrics = {}
    for name, fn in strategies.items():
        print(f"\n  回测: {name}")
        nav_df, metrics = engine.run_strategy(fn, name, rebalance_freq=5)
        all_nav[name] = nav_df
        all_metrics[name] = metrics
        print(f"    净值点数: {len(nav_df)}")

    # 获取所有交易日
    all_dates = sorted(set.union(*[set(n.index) for n in all_nav.values()]))
    all_dates = [d for d in all_dates if args.start_date <= d <= args.end_date]
    print(f"\n总交易日: {len(all_dates)} ({all_dates[0].date()} → {all_dates[-1].date()})")

    # ── 2. 每分钟推进一个交易日 ──
    print("\n" + "=" * 50)
    print(f"阶段2: 逐日推进 (每{args.interval}秒)")
    print("=" * 50)

    # 准备模板 HTML
    html_template = _build_html_template(strategies)

    for step, current_date in enumerate(all_dates):
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"\n[{step+1}/{len(all_dates)}] {date_str}", end=' ', flush=True)

        # 截取每个策略到当前日期的净值
        partial_strategies = []
        for name in strategies:
            nav = all_nav[name]
            partial = nav[nav.index <= current_date].copy()
            if len(partial) == 0:
                continue

            # 计算指标
            daily_ret = partial['nav'].pct_change().dropna()
            n_days = len(daily_ret)
            n_years = n_days / 252 if n_days > 0 else 0
            total_ret = partial['nav'].iloc[-1] / partial['nav'].iloc[0] - 1
            ann_ret = (1 + abs(total_ret)) ** (1 / n_years) - 1 if n_years > 0 else 0
            if total_ret < 0:
                ann_ret = -ann_ret
            ann_vol = daily_ret.std() * np.sqrt(252) if n_days > 0 else 0
            sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
            cummax = partial['nav'].cummax()
            dd = partial['nav'] / cummax - 1
            mdd = dd.min()
            calmar = ann_ret / abs(mdd) if mdd < 0 else float('inf')
            win_rate = (daily_ret > 0).mean() if n_days > 0 else 0

            # 归一化净值
            nav_series = (partial['nav'] / partial['nav'].iloc[0]).round(4).tolist()

            partial_strategies.append({
                'name': name,
                'nav_series': nav_series,
                'total_return': f"{total_ret:.2%}",
                'annual_return': f"{ann_ret:.2%}",
                'annual_vol': f"{ann_vol:.2%}",
                'sharpe': f"{sharpe:.2f}",
                'max_drawdown': f"{mdd:.2%}",
                'calmar': f"{calmar:.2f}",
                'win_rate': f"{win_rate:.2%}",
                'days': n_days,
                'total_ret_val': round(total_ret, 4),
                'ann_ret_val': round(ann_ret, 4),
                'ann_vol_val': round(ann_vol, 4),
                'sharpe_val': round(sharpe, 4),
                'mdd_val': round(mdd, 4),
            })

        # 日期列表
        dates = [d.strftime('%Y-%m-%d') for d in partial.index.tolist()
                 for partial in [next(s for s in partial_strategies if True)]]

        # 用partial_strategies里第一个的日期
        if partial_strategies:
            dates = [d.strftime('%Y-%m-%d') for d in
                     all_nav[list(strategies.keys())[0]][all_nav[list(strategies.keys())[0]].index <= current_date].index]

        strategies_json = json.dumps(partial_strategies, ensure_ascii=False)
        dates_json = json.dumps(dates)

        # 生成HTML
        html = html_template.replace("__DATA__", strategies_json).replace("__DATES__", dates_json)

        # 保存到 latest
        latest_dir = os.path.join(RESULTS_DIR, "latest")
        os.makedirs(latest_dir, exist_ok=True)
        with open(os.path.join(latest_dir, "report.html"), "w", encoding="utf-8") as f:
            f.write(html)

        if (step + 1) % 10 == 0:
            print(f"—— 已推进 {step+1} 天")

        # 等待下一分钟
        if step < len(all_dates) - 1:
            time.sleep(args.interval)

    print(f"\n✅ 模拟完成! 共推进 {len(all_dates)} 个交易日")
    print(f"最新: http://localhost:8081/results/latest/report.html")


def _build_html_template(strategies):
    """构建HTML模板 (和数据无关的部分)"""
    return r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>实时回测模拟</title>
<meta http-equiv="refresh" content="10">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#0d1117; color:#c9d1d9; padding:20px; }
.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; }
.header h1 { font-size:24px; color:#f0f6fc; }
.header .date { color:#8b949e; font-size:14px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:24px; }
.card { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; }
.card .lbl { font-size:12px; color:#8b949e; margin-bottom:4px; }
.card .val { font-size:22px; font-weight:600; }
.chart-box { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:20px; margin-bottom:24px; }
.chart-box h3 { font-size:16px; margin-bottom:12px; color:#f0f6fc; }
.chart-wrap { position:relative; height:350px; }
.chart-wrap-sm { position:relative; height:180px; }
table { width:100%; border-collapse:collapse; background:#161b22; border-radius:8px; overflow:hidden; }
th { background:#21262d; color:#8b949e; font-weight:500; font-size:12px; padding:12px 16px; text-align:right; }
th:first-child { text-align:left; }
td { padding:12px 16px; text-align:right; border-top:1px solid #21262d; font-size:14px; }
td:first-child { text-align:left; font-weight:500; color:#f0f6fc; }
tr:hover td { background:#1c2128; }
.green { color:#3fb950; }
.red { color:#f85149; }
.legend { display:flex; flex-wrap:wrap; gap:16px; margin-bottom:12px; }
.legend-item { display:flex; align-items:center; gap:6px; font-size:13px; cursor:pointer; }
.legend-dot { width:12px; height:12px; border-radius:3px; }
.tag { display:inline-block; background:#238636; color:#fff; font-size:11px; padding:2px 8px; border-radius:4px; margin-left:8px; }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>📊 实时模拟 <span class="tag">LIVE</span></h1>
    <div class="date" id="reportDate">加载中...</div>
  </div>
</div>

<div class="cards" id="summaryCards"></div>

<div class="chart-box">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
    <h3>累计净值曲线</h3>
    <div class="legend" id="chartLegend"></div>
  </div>
  <div class="chart-wrap"><canvas id="navChart"></canvas></div>
</div>

<div class="chart-box">
  <h3>回撤曲线</h3>
  <div class="chart-wrap-sm"><canvas id="ddChart"></canvas></div>
</div>

<div class="chart-box">
  <h3>绩效指标对比</h3>
  <table>
    <thead><tr id="metricsHeader"></tr></thead>
    <tbody id="metricsBody"></tbody>
  </table>
</div>

<script>
const DATA = __DATA__;
const DATES = __DATES__;
const COLORS = ['#3fb950','#58a6ff','#d29922','#f85149','#bc8cff','#f0883e','#79c0ff','#ff7b72'];
const COLORS_RGB = ['rgba(63,185,80,','rgba(88,166,255,','rgba(210,153,34,','rgba(248,81,73,','rgba(188,140,255,','rgba(240,136,62,','rgba(121,192,255,','rgba(255,123,114,'];

const s0 = DATA[0] || {};
document.getElementById('reportDate').textContent =
  (DATES[0]||'')+' ~ '+(DATES[DATES.length-1]||'')+'  (共'+DATES.length+'个交易日)';

// 指标卡片
const cards = [
  ['总收益率', s0.total_return||'-', s0.total_ret_val>=0],
  ['年化收益', s0.annual_return||'-', s0.ann_ret_val>=0],
  ['年化波动', s0.annual_vol||'-', false],
  ['夏普比率', s0.sharpe||'-', s0.sharpe_val>=0],
  ['最大回撤', s0.max_drawdown||'-', false],
  ['卡尔玛', s0.calmar||'-', (s0.calmar||'inf')!=='inf'&&parseFloat(s0.calmar||0)>=0],
  ['日胜率', s0.win_rate||'-', true],
  ['交易日', s0.days||0, true],
];
document.getElementById('summaryCards').innerHTML = cards.map(c =>
  '<div class="card"><div class="lbl">'+c[0]+'</div><div class="val '+(c[2]?'green':'red')+'">'+c[1]+'</div></div>'
).join('');

// 图例
const active = {};
DATA.forEach(function(s,i){ active[s.name]=true; });
document.getElementById('chartLegend').innerHTML = DATA.map(function(s,i){
  return '<div class="legend-item" onclick="toggle('+i+')" data-i="'+i+'">'+
    '<div class="legend-dot" style="background:'+COLORS[i%COLORS.length]+'"></div>'+s.name+'</div>';
}).join('');
function toggle(i) {
  const s = DATA[i]; active[s.name]=!active[s.name];
  document.querySelector('.legend-item[data-i="'+i+'"]').style.opacity = active[s.name]?1:0.3;
  updateChart();
}

// 净值曲线
let nc;
function initNavChart() {
  nc = new Chart(document.getElementById('navChart'), {
    type:'line', data:{labels:DATES,datasets:[]},
    options: {
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      animation:{duration:300},
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:function(ctx){return ctx.raw.toFixed(4);}}}},
      scales: {
        x:{ticks:{maxTicksLimit:15,color:'#8b949e'},grid:{color:'#21262d'}},
        y:{min:0, ticks:{color:'#8b949e',callback:function(v){return v.toFixed(2);}},grid:{color:'#21262d'}}
      }
    }
  });
}
function updateChart() {
  const ds = [];
  DATA.forEach(function(s,i){
    if(!active[s.name]) return;
    ds.push({
      label:s.name, data:s.nav_series,
      borderColor:COLORS[i%COLORS.length],
      backgroundColor:COLORS_RGB[i%COLORS_RGB.length]+'0.1)',
      borderWidth:2, pointRadius:0, tension:0.1, fill:false
    });
  });
  nc.data.datasets = ds;
  nc.update();
}

// 回撤图
let dc;
function initDDChart() {
  if(!s0||!s0.nav_series) return;
  let cm = s0.nav_series[0];
  const dd = s0.nav_series.map(function(v){ cm=Math.max(cm,v); return v/cm-1; });
  dc = new Chart(document.getElementById('ddChart'), {
    type:'line', data:{labels:DATES,datasets:[{
      label:s0.name+' 回撤', data:dd,
      borderColor:'#f85149', backgroundColor:'rgba(248,81,73,0.15)',
      borderWidth:1.5, pointRadius:0, fill:true, tension:0.1
    }]},
    options:{
      responsive:true, maintainAspectRatio:false,
      animation:{duration:300},
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:function(ctx){return (ctx.raw*100).toFixed(2)+'%';}}}},
      scales:{
        x:{ticks:{maxTicksLimit:10,color:'#8b949e'},grid:{color:'#21262d'}},
        y:{ticks:{color:'#8b949e',callback:function(v){return (v*100).toFixed(0)+'%';}},grid:{color:'#21262d'}}
      }
    }
  });
}

// 指标表
const fields = [
  ['name','策略名','left'],['total_return','总收益率'],['annual_return','年化收益'],
  ['annual_vol','年化波动'],['sharpe','夏普比率'],['max_drawdown','最大回撤'],
  ['calmar','卡尔玛'],['win_rate','日胜率'],['days','交易日数']
];
document.getElementById('metricsHeader').innerHTML = fields.map(function(f){
  return '<th style="text-align:'+(f[2]||'right')+'">'+f[1]+'</th>';
}).join('');
document.getElementById('metricsBody').innerHTML = DATA.map(function(s){
  return '<tr>'+fields.map(function(f){
    var v = s[f[0]]||'-', cls='';
    if(f[0]!=='name'&&f[0]!=='days'){
      var num = parseFloat(String(v).replace(/[^0-9.\-]/g,''));
      cls = num>=0?'green':'red';
    }
    return '<td class="'+cls+'">'+v+'</td>';
  }).join('')+'</tr>';
}).join('');

initNavChart(); updateChart(); initDDChart();
</script>
</body>
</html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实时更新模拟")
    parser.add_argument("--start", default="2021-03-11", help="起始日期")
    parser.add_argument("--end", default="2022-01-01", help="结束日期")
    parser.add_argument("--interval", type=int, default=60, help="推进间隔(秒)")
    parser.add_argument("--strategy", default=None, help="只跑特定策略名")
    args = parser.parse_args()
    args.start_date = pd.Timestamp(args.start)
    args.end_date = pd.Timestamp(args.end)
    simulate(args)
