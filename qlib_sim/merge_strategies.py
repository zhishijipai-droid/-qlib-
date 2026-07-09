"""Merge micro-cap strategy into strategy.html"""
import json, os

# Load data
with open('../output/small_cap_100yi.json') as f:
    s1 = json.load(f)['strategies'][0]
with open('../output/micro_cap_400.json') as f:
    s2 = json.load(f)['strategies'][0]

with open('../output/strategy.html', 'r', encoding='utf-8') as f:
    h = f.read()

# Build JS data strings
def js_arr(s): return json.dumps([round(n['nav']/1000000,6) for n in s['nav_history']])
def js_dates(s): return json.dumps([n['date'] for n in s['nav_history']])
def js_trades(s): return json.dumps(s['monthly_trades'])
def js_bench(s): return json.dumps(s['benchmark_nav'])
def js_metrics(s): return json.dumps({
    'total_return':s['total_return'],'annual_return':s['annual_return'],
    'annual_vol':s['annual_vol'],'sharpe':s['sharpe'],
    'max_drawdown':s['max_drawdown'],'calmar':s['calmar'],
    'win_rate':s['win_rate'],'total_value_10k':s['total_value_10k']
})

with open('strategies/small_cap.py','r') as f:
    code1 = json.dumps(f.read())
with open('strategies/micro_cap.py','r') as f:
    code2 = json.dumps(f.read())

logic1 = json.dumps('全A股市值<100亿的股票,等权每月调仓.\n1.每月末获取全部A股\n2.剔除ST/停牌/市值缺失\n3.筛市值<100亿\n4.等权1/N\n5.持有至月末', ensure_ascii=False)
logic2 = json.dumps('全A股市值最小的400只,等权每月调仓.\n参考:米筐微盘股指数866006.RI\n1.每月末获取全部A股\n2.剔除ST/停牌/市值缺失\n3.按市值排序取最小400只\n4.等权1/N\n5.持有至月末', ensure_ascii=False)

# Find script boundaries
# We have: <head>...<script src="chart.js"> -> Chart.js script (first script)
# Then maybe an empty <script></script>? No, we should have 2 script tags: Chart.js + our inline
# HTML structure: <head>...<script src=Chart.js> ... </head><body>...<script>data+logic</script></body>
# Find the last <script> tag - that's our data+logic script

first_script_tag = h.find('<script>')
# Skip Chart.js script if it uses src= 
chart_script_close = h.find('</script>') + 9
# Second <script> is our data script
second_start = h.find('<script>', chart_script_close)
last_script_close = h.rfind('</script>')

# Replace everything between second_start and last_script_close+9
new_script = '''<script>
var STRAT_CODE=''' + code1 + ''';
var STRAT_CODE2=''' + code2 + ''';
var NAV1=''' + js_arr(s1) + ''',DATES1=''' + js_dates(s1) + ''',TRADES1=''' + js_trades(s1) + ''',M1=''' + js_metrics(s1) + ''',LOGIC1=''' + logic1 + ''',BENCH1=''' + js_bench(s1) + ''';
var NAV2=''' + js_arr(s2) + ''',DATES2=''' + js_dates(s2) + ''',TRADES2=''' + js_trades(s2) + ''',M2=''' + js_metrics(s2) + ''',LOGIC2=''' + logic2 + ''',BENCH2=''' + js_bench(s2) + ''';
var curStrat=0,NAV=NAV1,DATES=DATES1,TRADES=TRADES1,M=M1,STRAT_LOGIC=LOGIC1,BENCH=BENCH1;
var peak=1,DD=[];for(var i=0;i<NAV.length;i++){if(NAV[i]>peak)peak=NAV[i];DD.push(+((NAV[i]-peak)/peak*100).toFixed(2));}
document.getElementById("tradeCount").textContent=TRADES.length+" 次调仓";
var sl=[{id:"s1",name:"<100亿小市值",ann:M1.annual_return,tot:M1.total_return,sharpe:M1.sharpe,mdd:M1.max_drawdown,cal:M1.calmar,vol:M1.annual_vol,wr:M1.win_rate,val:M1.total_value_10k,reb:"monthly"},{id:"s2",name:"微盘股(最小400)",ann:M2.annual_return,tot:M2.total_return,sharpe:M2.sharpe,mdd:M2.max_drawdown,cal:M2.calmar,vol:M2.annual_vol,wr:M2.win_rate,val:M2.total_value_10k,reb:"monthly"}];
function rl(){document.getElementById("listTbody").innerHTML=sl.map(function(s,i){return '<tr onclick="od('+i+')"><td class=name>'+s.name+'</td><td class=up>+'+s.ann.toFixed(2)+'%</td><td class=up>+'+s.tot.toFixed(1)+'%</td><td>'+s.sharpe.toFixed(2)+'</td><td class=down>-'+s.mdd.toFixed(2)+'%</td><td>'+s.cal.toFixed(2)+'</td><td>'+s.vol.toFixed(2)+'%</td><td>'+s.wr.toFixed(1)+'%</td><td>¥'+s.val.toLocaleString()+'</td><td>'+s.reb+'</td></tr>'}).join("");}
function od(idx){curStrat=idx;var n=[NAV1,NAV2],d=[DATES1,DATES2],t=[TRADES1,TRADES2],m=[M1,M2],l=[LOGIC1,LOGIC2],b=[BENCH1,BENCH2];NAV=n[idx];DATES=d[idx];TRADES=t[idx];M=m[idx];STRAT_LOGIC=l[idx];BENCH=b[idx];peak=1;DD=[];for(var i=0;i<NAV.length;i++){if(NAV[i]>peak)peak=NAV[i];DD.push(+((NAV[i]-peak)/peak*100).toFixed(2));}
document.getElementById("detailView").querySelector("h1").textContent="📊 "+sl[idx].name;
document.getElementById("mainView").style.display="none";document.getElementById("detailView").classList.add("active");
document.getElementById("tradeCount").textContent=TRADES.length+" 次调仓";rdc();dnv();ddc();rt();
var ce=document.getElementById("strategyCode"),bt=document.getElementById("codeToggleBtn");if(ce){ce.textContent="";ce.style.display="none";if(bt)bt.textContent="显示代码";}}
function backToList(){document.getElementById("detailView").classList.remove("active");document.getElementById("mainView").style.display="block";}
function rdc(){document.getElementById("dtCards").innerHTML='<div class=card><div class=lbl>总收益率</div><div class="val up">+'+M.total_return.toFixed(2)+'%</div></div><div class=card><div class=lbl>年化收益</div><div class="val up">+'+M.annual_return.toFixed(2)+'%</div></div><div class=card><div class=lbl>年化波动</div><div class=val>'+M.annual_vol.toFixed(2)+'%</div></div><div class=card><div class=lbl>夏普比率</div><div class="val up">'+M.sharpe+'</div></div><div class=card><div class=lbl>最大回撤</div><div class="val down">-'+M.max_drawdown.toFixed(2)+'%</div></div><div class=card><div class=lbl>卡尔玛</div><div class="val up">'+M.calmar+'</div></div><div class=card><div class=lbl>日胜率</div><div class="val up">'+M.win_rate+'%</div></div><div class=card><div class=lbl>1万→</div><div class="val up">¥'+M.total_value_10k.toLocaleString()+'</div></div>';
document.getElementById("dtLegend").innerHTML='<div class=legend-item onclick="tl(0)"><div class=legend-dot style=background:#60a5fa></div>策略</div><div class=legend-item onclick="tl(1)"><div class=legend-dot style=background:#64748b></div>等权基准</div>';
document.getElementById("strategyLogic").innerHTML=STRAT_LOGIC.replace(/\\n/g,"<br>");}
var vl=[true,true],nc=null,dcChart=null;
function tl(i){vl[i]=!vl[i];var e=document.querySelectorAll("#dtLegend .legend-item");if(e[i])e[i].style.opacity=vl[i]?1:0.4;dnv();}
function dnv(){if(nc)nc.destroy();if(NAV.length===0)return;var ds=[];if(vl[0])ds.push({label:"策略",data:NAV,borderColor:"#60a5fa",backgroundColor:"rgba(96,165,250,0.08)",fill:true,borderWidth:2,pointRadius:0,tension:0.2});if(vl[1]&&BENCH.length>0)ds.push({label:"基准",data:BENCH,borderColor:"#64748b",borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:0.2});
try{nc=new Chart(document.getElementById("navChart"),{type:"line",data:{labels:DATES,datasets:ds},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{mode:"index",intersect:false,backgroundColor:"#1e293b",titleColor:"#e2e8f0",bodyColor:"#94a3b8",borderColor:"#334155",borderWidth:1,padding:8,bodyFont:{size:12}}},scales:{x:{ticks:{color:"#64748b",maxTicksLimit:10,font:{size:10}},grid:{color:"#1e293b"}},y:{ticks:{color:"#64748b",callback:function(v){return v.toFixed(2)+"M"}},grid:{color:"#1e293b"}}},interaction:{mode:"index",intersect:false}}});}catch(e){console.error("Chart error:",e);}}
function ddc(){if(dcChart)dcChart.destroy();if(DD.length===0)return;try{dcChart=new Chart(document.getElementById("ddChart"),{type:"line",data:{labels:DATES,datasets:[{label:"回撤",data:DD,borderColor:"#ef4444",backgroundColor:"rgba(239,68,68,0.12)",fill:true,borderWidth:1.5,pointRadius:0,tension:0.2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#64748b",maxTicksLimit:6,font:{size:9}},grid:{color:"#1e293b"}},y:{ticks:{color:"#64748b",callback:function(v){return v.toFixed(1)+"%"}},grid:{color:"#1e293b"}}}}});}catch(e){console.error("DDChart error:",e);}}
var cp=0,ps=20;
function rt(){if(TRADES.length===0)return;var s=cp*ps,e=Math.min(s+ps,TRADES.length),p=TRADES.slice(s,e),h="";for(var i=0;i<p.length;i++){var t=p[i];var a=t.top_added.map(function(x){return x.symbol}).join(", ");var r=t.top_removed.map(function(x){return x.symbol}).join(", ");h+='<tr onclick="sd('+(s+i)+')"><td>'+t.date+'</td><td>'+t.n_holdings+'</td><td class=up>+'+t.n_added+'</td><td class=down>-'+t.n_removed+'</td><td style=font-size:10px;color:#22c55e>'+a+'</td><td style=font-size:10px;color:#ef4444>'+r+'</td></tr>';}
document.getElementById("tradeTbody").innerHTML=h;document.getElementById("pageInfo").textContent=(s+1)+"-"+e+" / "+TRADES.length;document.getElementById("prevPage").disabled=(cp===0);document.getElementById("nextPage").disabled=(e>=TRADES.length);}
function rpage(d){cp+=d;if(cp<0)cp=0;if(cp*ps>=TRADES.length)cp=Math.max(0,Math.ceil(TRADES.length/ps)-1);rt();}
function filterTrades(){var q=document.getElementById("searchTrade").value.toLowerCase();if(!q){cp=0;rt();return;}var h="";for(var i=0;i<TRADES.length;i++){var t=TRADES[i];var all=t.top_added.concat(t.top_removed).map(function(x){return x.symbol.toLowerCase()});if(all.some(function(s){return s.indexOf(q)>=0})){h+='<tr onclick="sd('+i+')"><td>'+t.date+'</td><td>'+t.n_holdings+'</td><td class=up>+'+t.n_added+'</td><td class=down>-'+t.n_removed+'</td><td style=font-size:10px;color:#22c55e>'+t.top_added.map(function(x){return x.symbol}).join(", ")+'</td><td style=font-size:10px;color:#ef4444>'+t.top_removed.map(function(x){return x.symbol}).join(", ")+'</td></tr>';}}}
document.getElementById("tradeTbody").innerHTML=h||'<tr><td colspan=6 style=text-align:center;color:var(--dim)>无匹配</td></tr>';document.getElementById("pageInfo").textContent="搜索结果";}
function sd(idx){var t=TRADES[idx];if(!t)return;document.getElementById("detailTitle").textContent="调仓日: "+t.date;document.getElementById("detailSummary").innerHTML="<span>持仓 "+t.n_holdings+"只</span><span class=up>新增 "+t.n_added+"只</span><span class=down>剔除 "+t.n_removed+"只</span>";var vps=Math.round(1000000/t.n_holdings);var rows=[];t.top_added.forEach(function(a){if(a.price>0){var s=Math.max(100,Math.floor(vps/(a.price*1.001)));rows.push({d:"buy",sym:a.symbol,shares:s,price:a.price,val:Math.round(s*a.price)})}});t.top_removed.forEach(function(r){if(r.price>0){var s=Math.max(100,Math.floor(vps/(r.price*0.999)));rows.push({d:"sell",sym:r.symbol,shares:s,price:r.price,val:Math.round(s*r.price)})}});document.getElementById("detailTbody").innerHTML=rows.map(function(r){return '<tr><td style=color:'+(r.d==="buy"?"#22c55e":"#ef4444")+'>'+(r.d==="buy"?"买入":"卖出")+'</td><td>'+r.sym+'</td><td>'+r.shares.toLocaleString()+'</td><td>¥'+r.price.toFixed(2)+'</td><td>¥'+r.val.toLocaleString()+'</td></tr>'}).join("");document.getElementById("detailOverlay").classList.add("active");}
function closeDetail(){document.getElementById("detailOverlay").classList.remove("active");}
document.addEventListener("keydown",function(e){if(e.key==="Escape")closeDetail();});
function toggleCode(){var el=document.getElementById("strategyCode"),btn=document.getElementById("codeToggleBtn");if(!el||!btn)return;if(el.style.display==="block"){el.style.display="none";btn.textContent="显示代码";}else{el.style.display="block";btn.textContent="隐藏代码";if(!el.textContent||el.textContent.length<10)el.textContent=[STRAT_CODE,STRAT_CODE2][curStrat];}}
rl();
</script>'''

h = h[:second_start] + new_script + h[last_script_close+9:]

with open('../output/strategy.html', 'w', encoding='utf-8') as f:
    f.write(h)

print(f'OK: {len(h)/1024:.0f}KB')
print(f'Script tags: {h.count("<script>")}')
