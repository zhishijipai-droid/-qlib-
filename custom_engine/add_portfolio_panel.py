"""
向 strategy.html 添加策略组合面板功能
"""
import os

path = "D:/bigquant/output/strategy.html"
with open(path, encoding="utf-8") as f:
    html = f.read()

# ====== 1. 添加导航链接 ======
old_nav = '<div class="nav"><a href="./">📈 资产排名</a><a href="factors.html">📐 因子监控</a><a href="strategy.html" class="active">📊 策略监控</a></div>'
new_nav = '<div class="nav"><a href="./">📈 资产排名</a><a href="factors.html">📐 因子监控</a><a href="#" onclick="showMainView()" class="active">📊 策略监控</a><a href="#" onclick="showPortfolioView()">🔀 组合配置</a></div>'
html = html.replace(old_nav, new_nav)

# ====== 2. 在 details-overlay 前添加组合配置视图 ======
portfolio_html = '''
<!-- === 组合配置视图 === -->
<div class="detail-view" id="portfolioView">
<button class="back-btn" onclick="showMainView()">← 返回策略列表</button>
<h1 style="font-size:22px;margin-bottom:16px">🔀 策略组合配置</h1>
<div class="meta" style="font-size:12px">
选择2~3个策略并分配权重（总和100%），生成组合净值曲线。
</div>
<div id="pfConfigArea" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-bottom:20px"></div>
<div style="display:flex;gap:12px;margin-bottom:20px">
  <button class="back-btn" onclick="pfGenerate()" style="background:var(--blue);color:white;border:none;padding:8px 24px;font-size:14px">📊 生成组合</button>
  <span id="pfError" style="color:var(--red);font-size:13px;align-self:center"></span>
</div>
<div id="pfResultArea" style="display:none">
  <div class="chart-box"><h3>累计净值曲线对比</h3><div class="legend" id="pfLegend"></div><div class="chart-wrap"><canvas id="pfNavChart"></canvas></div></div>
  <div class="section-label">📈 组合表现</div>
  <div class="cards" id="pfCards"></div>
  <div class="chart-box"><h3>组合回撤曲线</h3><div class="chart-wrap-sm"><canvas id="pfDdChart"></canvas></div></div>
  <button class="back-btn" onclick="pfExport()">📄 导出报告</button>
</div>
</div>
'''
old_marker = '<div class="detail-overlay" id="detailOverlay">'
html = html.replace(old_marker, portfolio_html + '\n' + old_marker)

# ====== 3. 修改 rl() 函数和导航, 添加 showMainView / showPortfolioView ======
# 在 rl() 调用前添加新的函数
new_funcs = '''
function showMainView(){hideAll();document.getElementById("mainView").style.display="block";var a=document.querySelectorAll(".nav a");a[0].classList.remove("active");a[1].classList.remove("active");a[2].classList.add("active");a[3].classList.remove("active");}
function showPortfolioView(){hideAll();document.getElementById("portfolioView").classList.add("active");var a=document.querySelectorAll(".nav a");a[0].classList.remove("active");a[1].classList.remove("active");a[2].classList.remove("active");a[3].classList.add("active");pfInit();}
function hideAll(){document.getElementById("mainView").style.display="none";document.getElementById("detailView").classList.remove("active");document.getElementById("holdingsView").classList.remove("active");document.getElementById("portfolioView").classList.remove("active");document.getElementById("pfResultArea").style.display="none";}
var pfChart=null,pfDdChart=null,pfData=null,pfDates=null;
function pfInit(){
  var area=document.getElementById("pfConfigArea");
  var colors=["#60a5fa","#22c55e","#f59e0b"];
  var h="";
  for(var i=0;i<sl.length;i++){
    h+='<div style="background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px">';
    h+='<label style="display:flex;align-items:center;gap:8px;margin-bottom:10px;cursor:pointer">';
    h+='<input type="checkbox" id="pfCb'+i+'" checked onchange="pfCheckWarn()" style="width:16px;height:16px">';
    h+='<span style="color:'+colors[i%3]+';font-weight:600;font-size:14px">'+sl[i].name+'</span></label>';
    h+='<div style="margin-bottom:6px"><span style="color:var(--dim);font-size:11px">年化 </span><span class=up>+'+sl[i].ann+'%</span>';
    h+='<span style="color:var(--dim);font-size:11px;margin-left:10px">夏普 </span><span>'+sl[i].sharpe+'</span>';
    h+='<span style="color:var(--dim);font-size:11px;margin-left:10px">回撤 </span><span class=down>-'+sl[i].mdd+'%</span></div>';
    h+='<div style="display:flex;align-items:center;gap:8px">';
    h+='<span style="color:var(--dim);font-size:12px;min-width:40px">权重</span>';
    h+='<input type="range" id="pfWt'+i+'" min="0" max="100" value="'+(i===0?50:i===1?50:0)+'" oninput="pfSync('+i+')" style="flex:1;height:6px">';
    h+='<input type="number" id="pfWtNum'+i+'" min="0" max="100" value="'+(i===0?50:i===1?50:0)+'" onchange="pfSyncNum('+i+')" style="width:55px;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:2px 4px;border-radius:4px;font-size:12px;text-align:center">';
    h+='<span style="color:var(--dim);font-size:11px">%</span></div></div>';
  }
  area.innerHTML=h;
  document.getElementById("pfError").textContent="";
}
function pfSync(i){
  var inp=document.getElementById("pfWt"+i),num=document.getElementById("pfWtNum"+i);
  num.value=inp.value;pfCheckWarn();
}
function pfSyncNum(i){
  var inp=document.getElementById("pfWt"+i),num=document.getElementById("pfWtNum"+i);
  var v=Math.max(0,Math.min(100,parseInt(num.value)||0));
  inp.value=v;num.value=v;pfCheckWarn();
}
function pfCheckWarn(){
  var total=0,cnt=0;
  for(var i=0;i<sl.length;i++){
    var cb=document.getElementById("pfCb"+i);
    if(cb&&cb.checked){cnt++;total+=parseInt(document.getElementById("pfWtNum"+i).value||0);}
  }
  var err=document.getElementById("pfError");
  if(cnt<2){err.textContent="请至少选择2个策略";return false;}
  if(total!==100){err.textContent="权重总和必须为100%（当前"+total+"%）";return false;}
  err.textContent="";return true;
}
function pfGenerate(){
  if(!pfCheckWarn())return;
  // Collect selected strategies with their normalized navs
  var selected=[];var navArrays=[];
  for(var i=0;i<sl.length;i++){
    var cb=document.getElementById("pfCb"+i);
    if(!cb||!cb.checked)continue;
    var wt=parseInt(document.getElementById("pfWtNum"+i).value||0)/100;
    var nav=[NAV1,NAV2,NAV3][i];
    var dates=[DATES1,DATES2,DATES3][i];
    selected.push({idx:i,weight:wt,nav:nav,dates:dates});
  }
  if(selected.length<2)return;
  
  // Find common dates (intersection)
  var commonDates=selected[0].dates.filter(function(d){
    for(var j=1;j<selected.length;j++){
      if(selected[j].dates.indexOf(d)<0)return false;
    }
    return true;
  });
  if(commonDates.length<10){document.getElementById("pfError").textContent="公共交易日不足";return;}
  
  // Build aligned navs and combined nav (normalized to 1.0)
  var pfDates=commonDates;
  var alignedNavs=[];var weights=[];
  for(var j=0;j<selected.length;j++){
    var navMap={};var s=selected[j];
    for(var k=0;k<s.dates.length;k++)navMap[s.dates[k]]=s.nav[k];
    var aligned=[];
    for(var k=0;k<commonDates.length;k++)aligned.push(navMap[commonDates[k]]||1.0);
    alignedNavs.push(aligned);
    weights.push(s.weight);
  }
  
  // Combined nav: normalized to 1.0, then weighted sum
  var combined=[];
  for(var k=0;k<commonDates.length;k++){
    var val=1.0;
    for(var j=0;j<selected.length;j++){
      var base=alignedNavs[j][0]||1.0;
      val+=weights[j]*(alignedNavs[j][k]/base-1);
    }
    combined.push(val);
  }
  
  pfData={selected:selected,weights:weights,aligned:alignedNavs,combined:combined,dates:commonDates};
  pfDates=commonDates;
  
  // Compute metrics
  var totalRet=(combined[combined.length-1]/combined[0]-1)*100;
  var nDays=combined.length-1;var nYears=nDays/252;
  var annRet=((1+totalRet/100)**(1/nYears)-1)*100;
  var dailyRets=[];
  for(var k=1;k<combined.length;k++)dailyRets.push(combined[k]/combined[k-1]-1);
  var avgRet=dailyRets.reduce(function(a,b){return a+b;},0)/dailyRets.length;
  var varRet=dailyRets.reduce(function(a,b){return a+(b-avgRet)**2;},0)/dailyRets.length;
  var annVol=Math.sqrt(varRet)*Math.sqrt(252)*100;
  var sharpe=annVol>0?(annRet/annVol):0;
  
  // MDD
  var peak=combined[0];var mdd=0;var ddStart=0,ddEnd=0,ddPeakIdx=0;
  for(var k=0;k<combined.length;k++){
    if(combined[k]>peak){peak=combined[k];ddPeakIdx=k;}
    var dd=(combined[k]/peak-1)*100;
    if(dd<mdd){mdd=dd;ddStart=combined[ddPeakIdx]>0?pfDates[ddPeakIdx]:pfDates[0];ddEnd=pfDates[k];}
  }
  mdd=Math.abs(mdd);
  var calmar=annRet/mdd;
  var dailyWr=dailyRets.filter(function(r){return r>0;}).length/dailyRets.length*100;
  var val10k=Math.round(10000*combined[combined.length-1]/combined[0]);
  
  // Show result
  document.getElementById("pfResultArea").style.display="block";
  
  // Cards
  document.getElementById("pfCards").innerHTML=
    '<div class=card><div class=lbl>总收益率</div><div class="val up">+'+totalRet.toFixed(2)+'%</div></div>'+
    '<div class=card><div class=lbl>年化收益</div><div class="val up">+'+annRet.toFixed(2)+'%</div></div>'+
    '<div class=card><div class=lbl>年化波动</div><div class=val>'+annVol.toFixed(2)+'%</div></div>'+
    '<div class=card><div class=lbl>夏普比率</div><div class="val up">'+sharpe.toFixed(2)+'</div></div>'+
    '<div class=card><div class=lbl>最大回撤</div><div class="val down">-'+mdd.toFixed(2)+'%</div><div class=subval>'+ddStart+' ~ '+ddEnd+'</div></div>'+
    '<div class=card><div class=lbl>卡玛比率</div><div class="val up">'+calmar.toFixed(2)+'</div></div>'+
    '<div class=card><div class=lbl>日胜率</div><div class="val up">'+dailyWr.toFixed(1)+'%</div></div>'+
    '<div class=card><div class=lbl>1万→</div><div class="val up">¥'+val10k.toLocaleString()+'</div></div>';
  
  // Legend
  var legColors=["#60a5fa","#22c55e","#f59e0b","#ef4444"];
  var legHtml='<div class=legend-item><div class=legend-dot style=background:'+legColors[0]+'></div>组合</div>';
  for(var j=0;j<selected.length;j++){
    legHtml+='<div class=legend-item><div class=legend-dot style=background:'+legColors[j+1]+'></div>'+selected[j].idx+'. '+sl[selected[j].idx].name+'</div>';
  }
  document.getElementById("pfLegend").innerHTML=legHtml;
  
  pfRenderChart();
}
function pfRenderChart(){
  if(pfChart)pfChart.destroy();
  if(pfDdChart)pfDdChart.destroy();
  if(!pfData)return;
  var colors=["#60a5fa","#22c55e","#f59e0b","#ef4444"];
  
  // Main NAV chart
  var ds=[];
  ds.push({label:"组合",data:pfData.combined,borderColor:colors[0],backgroundColor:"rgba(96,165,250,0.08)",fill:true,borderWidth:2,pointRadius:0,tension:0.2});
  for(var j=0;j<pfData.selected.length;j++){
    var base=pfData.aligned[j][0]||1.0;
    var norm=pfData.aligned[j].map(function(v){return v/base;});
    ds.push({label:sl[pfData.selected[j].idx].name+" ("+(pfData.weights[j]*100).toFixed(0)+"%)",data:norm,borderColor:colors[j+1],borderWidth:1.5,borderDash:[4,3],pointRadius:0,tension:0.2});
  }
  
  pfChart=new Chart(document.getElementById("pfNavChart"),{
    type:"line",data:{labels:pfData.dates,datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{mode:"index",intersect:false,backgroundColor:"#1e293b",titleColor:"#e2e8f0",bodyColor:"#94a3b8",borderColor:"#334155",borderWidth:1,padding:8,bodyFont:{size:12}}},
      scales:{x:{ticks:{color:"#64748b",maxTicksLimit:10,font:{size:10}},grid:{color:"#1e293b"}},
              y:{ticks:{color:"#64748b",font:{size:10}},grid:{color:"#1e293b"}}},
      interaction:{mode:"index",intersect:false}}
  });
  
  // Drawdown chart
  var peakDd=pfData.combined[0];var ddVals=[];
  for(var k=0;k<pfData.combined.length;k++){
    if(pfData.combined[k]>peakDd)peakDd=pfData.combined[k];
    ddVals.push(+((pfData.combined[k]/peakDd-1)*100).toFixed(2));
  }
  pfDdChart=new Chart(document.getElementById("pfDdChart"),{
    type:"line",data:{labels:pfData.dates,datasets:[{label:"回撤",data:ddVals,borderColor:"#ef4444",backgroundColor:"rgba(239,68,68,0.12)",fill:true,borderWidth:1.5,pointRadius:0,tension:0.2}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
      scales:{x:{ticks:{color:"#64748b",maxTicksLimit:6,font:{size:9}},grid:{color:"#1e293b"}},
              y:{ticks:{color:"#64748b",callback:function(v){return v.toFixed(1)+"%"}},grid:{color:"#1e293b"}}}}
  });
}
function pfExport(){
  if(!pfData)return;
  var line=Array(50).join("=");
  var s="年化: "+document.querySelector("#pfCards .card:nth-child(2) .val").textContent;
  var r="组合配置报告\\n"+line+"\\n";
  for(var j=0;j<pfData.selected.length;j++){
    r+="  "+(j+1)+". "+sl[pfData.selected[j].idx].name+": "+(pfData.weights[j]*100).toFixed(0)+"%\\n";
  }
  r+=line+"\\n";
  var cards=document.querySelectorAll("#pfCards .card");
  for(var i=0;i<cards.length;i++){
    var lbl=cards[i].querySelector(".lbl").textContent;
    var val=cards[i].querySelector(".val").textContent;
    r+="  "+lbl+": "+val+"\\n";
  }
  r+=line+"\\n生成: "+new Date().toLocaleString();
  document.getElementById("reportTitle").textContent="📄 组合报告";
  document.getElementById("reportBody").textContent=r;
  document.getElementById("reportModal").classList.add("active");
}
'''
# 在 rl(); 之前插入
old_rl = 'rl();\n</script>'
html = html.replace(old_rl, new_funcs + '\nrl();\n</script>')

# ====== 4. 修改 backToList 函数 ======
old_bl = 'function backToList(){document.getElementById("detailView").classList.remove("active");document.getElementById("holdingsView").classList.remove("active");document.getElementById("mainView").style.display="block";}'
new_bl = 'function backToList(){hideAll();document.getElementById("mainView").style.display="block";var a=document.querySelectorAll(".nav a");if(a[2])a[2].classList.add("active");if(a[3])a[3].classList.remove("active");}'
html = html.replace(old_bl, new_bl)

with open(path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ 组合面板已添加。文件大小: {len(html)/1024:.0f} KB")
