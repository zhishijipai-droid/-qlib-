"""
实时更新模拟 v2 — 直接用已有的回测结果，跳过全量重跑

用法:
  python simulate_realtime_v2.py                     # 2021-03-11 → 数据结束
  python simulate_realtime_v2.py --start 2021-06-01 --interval 5
"""
import os, sys, time, argparse, shutil, json, glob
from datetime import datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from config import RESULTS_DIR


def simulate(start_date, interval):
    # 读取所有策略的净值CSV（从之前跑好的全量结果）
    nav_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "2026-07-07", "*_nav.csv")))
    if not nav_files:
        print("没有找到净值文件，请先运行 python run_all.py")
        return

    # 加载所有策略的净值
    all_nav = {}
    for nf in nav_files:
        name = os.path.basename(nf).replace("_nav.csv", "")
        df = pd.read_csv(nf, index_col=0, parse_dates=True)
        # 只保留 start_date 之后的数据
        all_nav[name] = df[df.index >= pd.Timestamp(start_date)]

    # 取所有交易日，排序
    all_dates = sorted(set.union(*[set(n.index) for n in all_nav.values()]))
    all_dates = [d for d in all_dates if d >= pd.Timestamp(start_date)]
    print(f"交易日: {len(all_dates)} ({all_dates[0].date()} → {all_dates[-1].date()})")
    print(f"策略: {list(all_nav.keys())}")
    print(f"推进间隔: {interval}秒")
    print("=" * 50)

    # 清理
    latest_dir = os.path.join(RESULTS_DIR, "latest")
    os.makedirs(latest_dir, exist_ok=True)

    # HTML模板
    html_template = _build_html_template()

    for step, current_date in enumerate(all_dates):
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"[{step+1}/{len(all_dates)}] {date_str}")

        # 对每个策略截取到当前日期
        partial_strategies = []
        dates_use = []
        for name, nav_df in all_nav.items():
            partial = nav_df[nav_df.index <= current_date].copy()
            if len(partial) < 2:
                continue

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
            nav_series = (partial['nav'] / partial['nav'].iloc[0]).round(4).tolist()
            dates_list = partial.index.strftime('%Y-%m-%d').tolist()

            dd_series = (dd * 100).round(2).tolist()  # 转百分比

            calmar_str = "∞" if mdd >= 0 else f"{calmar:.2f}"

            partial_strategies.append({
                'name': name, 'nav_series': nav_series, 'dd_series': dd_series,
                'total_return': f"{total_ret:.2%}",
                'annual_return': f"{ann_ret:.2%}",
                'annual_vol': f"{ann_vol:.2%}",
                'sharpe': f"{sharpe:.2f}",
                'max_drawdown': f"{mdd:.2%}",
                'calmar': calmar_str,
                'win_rate': f"{win_rate:.2%}",
                'days': n_days,
                'total_ret_val': round(total_ret, 4),
                'ann_ret_val': round(ann_ret, 4),
                'ann_vol_val': round(ann_vol, 4),
                'sharpe_val': round(sharpe, 4),
                'mdd_val': round(mdd, 4),
            })
            dates_use = dates_list  # 最后一个策略的日期

        if not partial_strategies:
            print(f"  ⏭ 跳过 (无数据)")
            if step < len(all_dates) - 1:
                time.sleep(interval)
            continue

        # 生成HTML
        html = html_template.replace("__DATA__", json.dumps(partial_strategies, ensure_ascii=False))
        html = html.replace("__DATES__", json.dumps(dates_use))
        html = html.replace("__DATE_RANGE__", f"{dates_use[0]} ~ {dates_use[-1]} ({len(dates_use)}个交易日)")

        with open(os.path.join(latest_dir, "report.html"), "w", encoding="utf-8") as f:
            f.write(html)

        if (step + 1) % 20 == 0:
            print(f"  —— 已推进 {step+1} 天")

        if step < len(all_dates) - 1:
            time.sleep(interval)

    print(f"\n✅ 完成! 共推进 {len(all_dates)} 个交易日")
    print(f"打开: http://localhost:8082/")


def _build_html_template():
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
.strat-group { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; margin-bottom:12px; display:flex; align-items:center; gap:16px; }
.strat-group .sg-name { font-size:16px; font-weight:600; min-width:120px; color:#f0f6fc; }
.strat-group .sg-metrics { display:flex; gap:20px; flex-wrap:wrap; }
.strat-group .sg-item { text-align:center; }
.strat-group .sg-item .sg-lbl { font-size:11px; color:#8b949e; }
.strat-group .sg-item .sg-val { font-size:15px; font-weight:500; }
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
    <div class="date" id="reportDate"></div>
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
document.getElementById('reportDate').textContent = '__DATE_RANGE__';

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
document.getElementById('summaryCards').innerHTML = cards.map(function(c){
  return '<div class="card"><div class="lbl">'+c[0]+'</div><div class="val '+(c[2]?'green':'red')+'">'+c[1]+'</div></div>';
}).join('');

const active = {};
DATA.forEach(function(s,i){ active[s.name]=true; });
document.getElementById('chartLegend').innerHTML = DATA.map(function(s,i){
  return '<div class="legend-item" onclick="toggle('+i+')" data-i="'+i+'">'+
    '<div class="legend-dot" style="background:'+COLORS[i%COLORS.length]+'"></div>'+s.name+'</div>';
}).join('');
function toggle(i){ var s=DATA[i]; active[s.name]=!active[s.name];
  document.querySelector('.legend-item[data-i="'+i+'"]').style.opacity=active[s.name]?1:0.3; updateChart(); }

var nc;
function initNavChart(){
  nc=new Chart(document.getElementById('navChart'),{type:'line',data:{labels:DATES,datasets:[]},
  options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
    animation:{duration:300},
    plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return ctx.raw.toFixed(4);}}}},
    scales:{x:{ticks:{maxTicksLimit:15,color:'#8b949e'},grid:{color:'#21262d'}},
            y:{min:0,ticks:{color:'#8b949e',callback:function(v){return v.toFixed(2);}},grid:{color:'#21262d'}}}}});
}
function updateChart(){
  var ds=[];
  DATA.forEach(function(s,i){ if(!active[s.name]) return;
    ds.push({label:s.name,data:s.nav_series,borderColor:COLORS[i%COLORS.length],
      backgroundColor:COLORS_RGB[i%COLORS_RGB.length]+'0.1)',borderWidth:2,pointRadius:0,tension:0.1,fill:false});
  });
  nc.data.datasets=ds; nc.update();
}

function initDDChart(){
  if(!s0||!s0.dd_series) return;
  window.ddChart = new Chart(document.getElementById('ddChart'),{type:'line',data:{labels:DATES,datasets:[{
    label:s0.name+' 回撤',data:s0.dd_series,borderColor:'#f85149',backgroundColor:'rgba(248,81,73,0.15)',
    borderWidth:1.5,pointRadius:0,fill:true,tension:0.1}]},
    options:{responsive:true,maintainAspectRatio:false,animation:{duration:300},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return ctx.raw.toFixed(2)+'%';}}}},
      scales:{x:{ticks:{maxTicksLimit:10,color:'#8b949e'},grid:{color:'#21262d'}},
              y:{ticks:{color:'#8b949e',callback:function(v){return v.toFixed(1)+'%';}},grid:{color:'#21262d'}}}}});
}

// 点击最大回撤切换回撤图
function showDD(idx){
  var s=DATA[idx];
  if(!s||!s.dd_series) return;
  window.ddChart.data.datasets[0].label=s.name+' 回撤';
  window.ddChart.data.datasets[0].data=s.dd_series;
  window.ddChart.update();
}

var FIELDS=[['name','策略名','left'],['total_return','总收益率'],['annual_return','年化收益'],
  ['annual_vol','年化波动'],['sharpe','夏普比率'],['max_drawdown','最大回撤|click'],
  ['calmar','卡尔玛'],['win_rate','日胜率'],['days','交易日数']];
document.getElementById('metricsHeader').innerHTML=FIELDS.map(function(f,fi){
  var label=f[1], isClick=label.indexOf('|click')>0;
  if(isClick){label=label.replace('|click','');return '<th style="text-align:'+(f[2]||'right')+';cursor:pointer;color:#58a6ff" onclick="showDD(0)">'+label+' ↺</th>';}
  return '<th style="text-align:'+(f[2]||'right')+'">'+label+'</th>';
}).join('');
document.getElementById('metricsBody').innerHTML=DATA.map(function(s,idx){
  return '<tr>'+FIELDS.map(function(f,fi){
    var fn=f[0], label=f[1], isClick=label.indexOf('|click')>0, v=s[fn]||'-', cls='';
    if(isClick){label=label.replace('|click','');}
    if(fn!=='name'&&fn!=='days'){var n=parseFloat(String(v).replace(/[^0-9.\-]/g,''));cls=n>=0?'green':'red';}
    if(isClick){return '<td class="'+cls+'" style="cursor:pointer;text-decoration:underline dotted" onclick="showDD('+idx+')">'+(v==='inf'?'∞':v)+'</td>';}
    return '<td class="'+cls+'">'+(v==='inf'?'∞':v)+'</td>';
  }).join('')+'</tr>';
}).join('');

initNavChart(); updateChart(); initDDChart();
</script>
</body>
</html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2021-03-11", help="起始日期")
    parser.add_argument("--interval", type=int, default=10, help="推进间隔(秒)")
    args = parser.parse_args()
    simulate(args.start, args.interval)
