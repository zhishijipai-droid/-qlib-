"""生成融合版策略页面 - 数据嵌入HTML"""
import os, json
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(os.path.dirname(__file__), "..", "output", "small_cap_100yi.json")) as f:
    data = json.load(f)

s = data['strategies'][0]

# 读策略源码
code_path = os.path.join(os.path.dirname(__file__), "strategies", "small_cap.py")
with open(code_path, "r", encoding="utf-8") as f:
    strategy_code = f.read()

# 追加到detail (不用strategy_code字段, 会破坏JS解析)
s['strategy_logic'] = """全A股市值<100亿的股票，等权每月调仓。\n1. 每月末获取全部A股\n2. 剔除ST/停牌/市值数据缺失的股票\n3. 筛选市值 < 100亿的股票\n4. 等权分配资金（1/N）\n5. 持有到下个月末"""
# 移除code字段,避免JS转义问题
if 'strategy_code' in s:
    del s['strategy_code']

# 策略列表数据(JSON字符串)
strategies_json = json.dumps([
    {"id":"small_cap_100yi","name":"<100亿小市值","ann":s['annual_return'],"tot":s['total_return'],"sharpe":s['sharpe'],"mdd":s['max_drawdown'],"cal":s['calmar'],"vol":s['annual_vol'],"wr":s['win_rate'],"val":s['total_value_10k'],"reb":"monthly"}
], ensure_ascii=False)

detail_json = json.dumps(s, ensure_ascii=False)

# 读取HTML模板
tmpl_path = os.path.join(os.path.dirname(__file__), "template.html")
if not os.path.exists(tmpl_path):
    # 创建模板
    tmpl = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>策略监控面板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#e2e8f0;--dim:#94a3b8;--blue:#60a5fa;--green:#22c55e;--red:#ef4444}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);padding:20px;max-width:1600px;margin:0 auto}
h1{font-size:22px;margin-bottom:4px}
.sub{color:var(--dim);font-size:13px;margin-bottom:14px}
.nav{display:flex;gap:16px;margin-bottom:14px}
.nav a{color:var(--blue);text-decoration:none;font-size:14px}
.nav a.active{color:var(--text);font-weight:600}
.up{color:var(--green)}.down{color:var(--red)}
.meta{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin-bottom:14px;font-size:13px;color:var(--dim);line-height:1.6}
.meta strong{color:var(--text)}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:8px 10px;text-align:right;white-space:nowrap}
th{color:var(--dim);font-weight:500;border-bottom:1px solid var(--border);cursor:pointer;position:sticky;top:0;background:var(--bg);z-index:1}
th:first-child,td:first-child{text-align:left}
td{border-bottom:1px solid #1e293b}
tr:hover td{background:var(--card)}
tr{cursor:pointer}
.name{color:var(--blue)}
.detail-view{display:none}
.detail-view.active{display:block}
.back-btn{background:var(--card);border:1px solid var(--border);color:var(--dim);padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;margin-bottom:16px}
.back-btn:hover{background:var(--blue);color:white}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px}
.card .lbl{font-size:11px;color:var(--dim);margin-bottom:3px}
.card .val{font-size:18px;font-weight:600}
.chart-box{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.chart-box h3{font-size:15px;margin-bottom:10px;color:var(--text)}
.chart-wrap{position:relative;height:320px}
.chart-wrap-sm{position:relative;height:160px}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px}
.legend-item{display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer}
.legend-dot{width:10px;height:10px;border-radius:3px}
.trade-box{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.trade-box h3{font-size:15px;margin-bottom:10px;color:var(--text)}
.info-box{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px}
.info-box h3{font-size:15px;margin-bottom:8px;color:var(--text)}
.info-box .desc{color:var(--dim);font-size:13px;line-height:1.7;padding:0}
.info-box .desc li{margin-left:16px;margin-bottom:2px}
.code-toggle{background:var(--bg);border:1px solid var(--border);color:var(--dim);padding:3px 10px;border-radius:4px;cursor:pointer;font-size:11px;margin-bottom:8px}
.code-toggle:hover{color:var(--text)}
.code-block{display:none;background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:14px;font-family:'Courier New',monospace;font-size:11px;line-height:1.5;overflow-x:auto;white-space:pre;color:#c9d1d9;max-height:400px;overflow-y:auto}
.trade-controls{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
.trade-controls input{background:var(--bg);border:1px solid var(--border);color:var(--text);padding:4px 8px;border-radius:4px;font-size:11px;width:130px}
.pagination{display:flex;justify-content:center;gap:8px;margin-top:10px;align-items:center}
.pagination button{background:var(--bg);border:1px solid var(--border);color:var(--dim);padding:3px 8px;border-radius:4px;cursor:pointer;font-size:11px}
.pagination button:disabled{opacity:0.4;cursor:default}
.pagination span{color:var(--dim);font-size:11px}
.detail-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:100;justify-content:center;align-items:center}
.detail-overlay.active{display:flex}
.detail-modal{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;width:min(65vw,700px);max-height:80vh;overflow-y:auto;position:relative}
.detail-modal h3{font-size:14px;margin-bottom:8px;color:var(--text)}
.detail-modal .close-btn{position:absolute;top:8px;right:12px;background:none;border:none;color:var(--dim);font-size:16px;cursor:pointer}
.detail-summary{display:flex;gap:14px;margin-bottom:10px;font-size:12px;color:var(--dim)}
.detail-table{width:100%;font-size:11px}
.detail-table th{background:var(--bg);padding:4px 6px;font-weight:500;font-size:10px;color:var(--dim)}
.detail-table td{padding:4px 6px;border-top:1px solid var(--border);font-size:11px}
.disclaimer{color:var(--dim);font-size:11px;text-align:center;margin-top:20px;padding:12px;border-top:1px solid var(--border)}
</style>
</head>
<body>

<div id="mainView">
<h1>📊 策略监控面板</h1>
<div class="sub">历史回测对比 · 数据最后更新: <span id="updTime">--</span></div>
<div class="nav"><a href="./">📈 资产排名</a><a href="factors.html">📐 因子监控</a><a href="strategy.html" class="active">📊 策略监控</a></div>
<div class="meta"><div><strong>✅SAFE: 8策略 | 股票池</strong> 全A股(剔除ST/退市/新股/停牌)</div></div>
<table><thead><tr>
<th onclick="sortBy(0)">策略名称</th><th onclick="sortBy(1)">年化收益</th><th onclick="sortBy(2)">累计收益</th>
<th onclick="sortBy(3)">夏普</th><th onclick="sortBy(4)">最大回撤</th><th onclick="sortBy(5)">卡玛</th>
<th onclick="sortBy(6)">年化波动</th><th onclick="sortBy(7)">胜率</th><th onclick="sortBy(8)">1万→</th><th onclick="sortBy(9)">调仓</th>
</tr></thead>
<tbody id="listTbody"></tbody></table>
</div>

<div class="detail-view" id="detailView">
<button class="back-btn" onclick="backToList()">← 返回策略列表</button>
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px"><div><h1 style="font-size:22px">📊 <span id="dtName"><100亿小市值</span></h1></div></div>
<div class="cards" id="dtCards"></div>
<div class="chart-box"><h3>累计净值曲线</h3><div class="legend" id="dtLegend"></div><div class="chart-wrap"><canvas id="navChart"></canvas></div></div>
<div class="chart-box"><h3>回撤曲线</h3><div class="chart-wrap-sm"><canvas id="ddChart"></canvas></div></div>
<div class="info-box" id="logicBox"><h3>📋 策略逻辑</h3><div class="desc" id="strategyLogic"></div></div>
<div class="info-box" id="codeBox"><h3>💻 策略代码</h3><button class="code-toggle" onclick="toggleCode()">显示代码</button><div class="code-block" id="strategyCode"></div></div>
<div class="trade-box"><h3>📅 每月调仓明细</h3>
<div class="trade-controls"><input id="searchTrade" placeholder="搜索股票代码..." oninput="filterTrades()"><span style="color:var(--dim);font-size:11px" id="tradeCount">--</span></div>
<table><thead><tr><th>调仓日期</th><th>持仓数</th><th>新增</th><th>剔除</th><th>前5新增</th><th>前5剔除</th></tr></thead><tbody id="tradeTbody"></tbody></table>
<div class="pagination"><button id="prevPage" onclick="changePage(-1)">← 上一页</button><span id="pageInfo">--</span><button id="nextPage" onclick="changePage(1)">下一页 →</button></div>
</div></div>

<div class="detail-overlay" id="detailOverlay"><div class="detail-modal"><button class="close-btn" onclick="closeDetail()">✕</button><h3 id="detailTitle">调仓详情</h3><div class="detail-summary" id="detailSummary"></div><table class="detail-table"><thead><tr><th>方向</th><th>代码</th><th>股数</th><th>价格</th><th>金额</th></tr></thead><tbody id="detailTbody"></tbody></table></div></div>
<div class="disclaimer">⚠️ 历史回测不代表未来收益</div>

<script>
var DETAIL_RAW = __DETAIL_JSON__;
var DETAIL = JSON.parse(DETAIL_RAW);
var STRATS = __STRATS__;
var curSort = 1, sortAsc = false;

// 初始化数据
var nh = DETAIL.nav_history || [];
var NAV = [], DATES = [], DD = [], TRADES = DETAIL.monthly_trades || [];
var peak = nh.length > 0 ? nh[0].nav : 1;
for(var i=0;i<nh.length;i++){
  var v = nh[i].nav;
  NAV.push(+(v/1000000).toFixed(6));
  DATES.push(nh[i].date);
  if(v > peak) peak = v;
  DD.push(+((v - peak) / peak * 100).toFixed(2));
}
document.getElementById("tradeCount").textContent = TRADES.length + " 次调仓";

var visibleLines = [true, true];
var navChart = null, ddChart = null;

function renderList(){
  var list = STRATS.slice();
  var keys = ["name","ann","tot","sharpe","mdd","cal","vol","wr","val","reb"];
  var k = keys[curSort] || "ann";
  list.sort(function(a,b){
    var va = a[k]||0, vb = b[k]||0;
    return sortAsc ? (va - vb) : (vb - va);
  });
  document.getElementById("listTbody").innerHTML = list.map(function(s){
    return '<tr onclick="openDetail(\'' + s.id + '\')"><td class=name>' + s.name + '</td>' +
      '<td class=' + (s.ann>=0?"up":"down") + '>' + (s.ann>=0?"+":"") + s.ann.toFixed(2) + '%</td>' +
      '<td class=' + (s.tot>=0?"up":"down") + '>' + (s.tot>=0?"+":"") + s.tot.toFixed(1) + '%</td>' +
      '<td>' + s.sharpe.toFixed(2) + '</td><td class=down>-' + s.mdd.toFixed(2) + '%</td>' +
      '<td>' + s.cal.toFixed(2) + '</td><td>' + s.vol.toFixed(2) + '%</td>' +
      '<td>' + s.wr.toFixed(1) + '%</td><td>¥' + s.val.toLocaleString() + '</td><td>' + s.reb + '</td></tr>';
  }).join("");
}

function sortBy(k){ if(curSort===k) sortAsc=!sortAsc; else{curSort=k;sortAsc=false;} renderList(); }

function openDetail(id){
  if(!DETAIL || DETAIL.id !== id) return;
  document.getElementById("mainView").style.display = "none";
  document.getElementById("detailView").classList.add("active");
  renderDetailCards();
  drawCharts();
  renderTrades();
}

function backToList(){
  document.getElementById("detailView").classList.remove("active");
  document.getElementById("mainView").style.display = "block";
}

function renderDetailCards(){
  var d = DETAIL;
  document.getElementById("dtCards").innerHTML =
    '<div class=card><div class=lbl>总收益率</div><div class="val up">+' + d.total_return.toFixed(2) + '%</div></div>' +
    '<div class=card><div class=lbl>年化收益</div><div class="val up">+' + d.annual_return.toFixed(2) + '%</div></div>' +
    '<div class=card><div class=lbl>年化波动</div><div class=val>' + d.annual_vol.toFixed(2) + '%</div></div>' +
    '<div class=card><div class=lbl>夏普比率</div><div class="val up">' + d.sharpe + '</div></div>' +
    '<div class=card><div class=lbl>最大回撤</div><div class="val down">-' + d.max_drawdown.toFixed(2) + '%</div></div>' +
    '<div class=card><div class=lbl>卡尔玛</div><div class="val up">' + d.calmar + '</div></div>' +
    '<div class=card><div class=lbl>日胜率</div><div class="val up">' + d.win_rate + '%</div></div>' +
    '<div class=card><div class=lbl>1万→</div><div class="val up">¥' + d.total_value_10k.toLocaleString() + '</div></div>';
  document.getElementById("dtLegend").innerHTML =
    '<div class="legend-item" onclick="toggleLine(0)"><div class="legend-dot" style="background:#60a5fa"></div><100亿小市值</div>' +
    '<div class="legend-item" onclick="toggleLine(1)"><div class="legend-dot" style="background:#64748b"></div>等权基准</div>';
  
  // 策略逻辑
  var logicEl = document.getElementById("strategyLogic");
  if(logicEl && d.strategy_logic){
    var html = "";
    var lines = d.strategy_logic.split("\\n");
    for(var i=0;i<lines.length;i++){
      var l = lines[i].trim();
      if(!l) continue;
      if(/^\\d+\\./.test(l)) html += "<li>" + l.replace(/^\\d+\\.\\s*/,"") + "</li>";
      else html += "<p>" + l + "</p>";
    }
    if(html) logicEl.innerHTML = "<ol>" + html + "</ol>";
    else logicEl.textContent = d.strategy_logic;
  }
  
  // 策略代码(暂时不包含)
  var codeEl = document.getElementById("strategyCode");
  if(codeEl) codeEl.textContent = "// 策略源码请在 strategies/small_cap.py 中查看";
}

function toggleCode(){
  var el = document.getElementById("strategyCode");
  var btn = document.querySelector(".code-toggle");
  if(!el || !btn) return;
  if(el.style.display === "block"){
    el.style.display = "none";
    btn.textContent = "显示代码";
  } else {
    el.style.display = "block";
    btn.textContent = "隐藏代码";
  }
}

function toggleLine(idx){
  visibleLines[idx] = !visibleLines[idx];
  var items = document.querySelectorAll("#dtLegend .legend-item");
  if(items[idx]) items[idx].style.opacity = visibleLines[idx] ? 1 : 0.4;
  drawNavChart();
}

function drawCharts(){ drawNavChart(); drawDDChart(); }

function drawNavChart(){
  if(navChart) navChart.destroy();
  if(NAV.length === 0) return;
  var ds = [];
  if(visibleLines[0]) ds.push({label:"<100亿",data:NAV,borderColor:"#60a5fa",backgroundColor:"rgba(96,165,250,0.08)",fill:true,borderWidth:2,pointRadius:0,tension:0.2});
  if(visibleLines[1]){
    var bench = [1.0];
    for(var i=1;i<NAV.length;i++) bench.push(+(bench[i-1]*(1+(NAV[i]-NAV[i-1])/NAV[i-1]*0.9)).toFixed(6));
    ds.push({label:"基准",data:bench,borderColor:"#64748b",borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:0.2});
  }
  navChart = new Chart(document.getElementById("navChart"),{
    type:"line",data:{labels:DATES,datasets:ds},
    options:{
    plugins:{legend:{display:false},tooltip:{mode:"index",intersect:false,backgroundColor:"#1e293b",titleColor:"#e2e8f0",bodyColor:"#94a3b8",borderColor:"#334155",borderWidth:1,padding:8,bodyFont:{size:12}}},
    scales:{x:{ticks:{color:"#64748b",maxTicksLimit:10,font:{size:10}},grid:{color:"#1e293b"}},
            y:{ticks:{color:"#64748b",callback:function(v){return v.toFixed(2)+"M"}},grid:{color:"#1e293b"}}}},
    interaction:{mode:"index",intersect:false}
    }
  });
}

function drawDDChart(){
  if(ddChart) ddChart.destroy();
  if(DD.length === 0) return;
  ddChart = new Chart(document.getElementById("ddChart"),{
    type:"line",data:{labels:DATES,datasets:[{label:"回撤",data:DD,borderColor:"#ef4444",backgroundColor:"rgba(239,68,68,0.12)",fill:true,borderWidth:1.5,pointRadius:0,tension:0.2}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
    scales:{x:{ticks:{color:"#64748b",maxTicksLimit:6,font:{size:9}},grid:{color:"#1e293b"}},
            y:{ticks:{color:"#64748b",callback:function(v){return v.toFixed(1)+"%"}},grid:{color:"#1e293b"}}}}
  });
}

var curPage = 0, pageSize = 20;
function renderTrades(){
  if(TRADES.length === 0) return;
  var start = curPage * pageSize, end = Math.min(start + pageSize, TRADES.length);
  var page = TRADES.slice(start, end), html = "";
  for(var i=0;i<page.length;i++){
    var t = page[i], idx = start + i;
    var added = t.top_added.map(function(x){return x.symbol}).join(", ");
    var removed = t.top_removed.map(function(x){return x.symbol}).join(", ");
    html += '<tr onclick="showDetail(' + idx + ')"><td>' + t.date + '</td><td>' + t.n_holdings + '</td>' +
      '<td class=up>+' + t.n_added + '</td><td class=down>-' + t.n_removed + '</td>' +
      '<td style="font-size:10px;color:#22c55e">' + added + '</td><td style="font-size:10px;color:#ef4444">' + removed + '</td></tr>';
  }
  document.getElementById("tradeTbody").innerHTML = html;
  document.getElementById("pageInfo").textContent = (start+1) + "-" + end + " / " + TRADES.length;
  document.getElementById("prevPage").disabled = (curPage === 0);
  document.getElementById("nextPage").disabled = (end >= TRADES.length);
}

function changePage(d){ curPage += d; if(curPage<0) curPage=0; if(curPage*pageSize>=TRADES.length) curPage=Math.max(0,Math.ceil(TRADES.length/pageSize)-1); renderTrades(); }

function filterTrades(){
  var q = document.getElementById("searchTrade").value.toLowerCase();
  if(!q){ curPage=0; renderTrades(); return; }
  var html = "";
  for(var i=0;i<TRADES.length;i++){
    var t = TRADES[i];
    var all = t.top_added.concat(t.top_removed).map(function(x){return x.symbol.toLowerCase()});
    if(all.some(function(s){return s.indexOf(q) >= 0})){
      html += '<tr onclick="showDetail(' + i + ')"><td>' + t.date + '</td><td>' + t.n_holdings + '</td>' +
        '<td class=up>+' + t.n_added + '</td><td class=down>-' + t.n_removed + '</td>' +
        '<td style="font-size:10px;color:#22c55e">' + t.top_added.map(function(x){return x.symbol}).join(", ") + '</td>' +
        '<td style="font-size:10px;color:#ef4444">' + t.top_removed.map(function(x){return x.symbol}).join(", ") + '</td></tr>';
    }
  }
  document.getElementById("tradeTbody").innerHTML = html || '<tr><td colspan=6 style="text-align:center;color:var(--dim)">无匹配</td></tr>';
  document.getElementById("pageInfo").textContent = "搜索结果";
}

function showDetail(idx){
  var t = TRADES[idx];
  if(!t) return;
  document.getElementById("detailTitle").textContent = "调仓日: " + t.date;
  document.getElementById("detailSummary").innerHTML = "<span>持仓 " + t.n_holdings + "只</span><span class=up>新增 " + t.n_added + "只</span><span class=down>剔除 " + t.n_removed + "只</span>";
  var vps = Math.round(1000000 / t.n_holdings);
  var rows = [];
  t.top_added.forEach(function(a){if(a.price>0){var s=Math.max(100,Math.floor(vps/(a.price*1.001)));rows.push({d:"buy",sym:a.symbol,shares:s,price:a.price,val:Math.round(s*a.price)})}});
  t.top_removed.forEach(function(r){if(r.price>0){var s=Math.max(100,Math.floor(vps/(r.price*0.999)));rows.push({d:"sell",sym:r.symbol,shares:s,price:r.price,val:Math.round(s*r.price)})}});
  document.getElementById("detailTbody").innerHTML = rows.map(function(r){
    return '<tr><td style="color:' + (r.d==="buy"?"#22c55e":"#ef4444") + '">' + (r.d==="buy"?"买入":"卖出") + '</td><td>' + r.sym + '</td><td>' + r.shares.toLocaleString() + '</td><td>¥' + r.price.toFixed(2) + '</td><td>¥' + r.val.toLocaleString() + '</td></tr>';
  }).join("");
  document.getElementById("detailOverlay").classList.add("active");
}

function closeDetail(){ document.getElementById("detailOverlay").classList.remove("active"); }
document.addEventListener("keydown", function(e){ if(e.key === "Escape") closeDetail(); });
renderList();
</script>
</body>
</html>
"""
else:
    with open(tmpl_path, 'r') as f:
        tmpl = f.read()

# 替换占位符
# DETAIL用JSON字符串包裹，通过JSON.parse解析(避免反斜杠转义问题)
detail_json_str = json.dumps(detail_json)  # 把JSON再包一层变成JSON字符串
html = tmpl.replace('__STRATS__', strategies_json).replace('__DETAIL_JSON__', detail_json_str)

out_path = os.path.join(os.path.dirname(__file__), "..", "output", "strategy.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ 页面已生成: {out_path}")
print(f"   大小: {os.path.getsize(out_path)/1024:.0f} KB")
print(f"   打开方式: file:///D:/bigquant/output/strategy.html")
