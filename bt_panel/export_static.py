"""
导出脚本：从 SQLite 数据库生成静态 JSON 文件，供 GitHub Pages 使用

用法: python export_static.py
输出: server/static/api/*.json
      每次 daily_pipeline 运行后执行此脚本
"""
import os, sys, json, sqlite3
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "server", "bt_panel.db")
STATIC_DIR = os.path.join(HERE, "server", "static")
API_DIR = os.path.join(STATIC_DIR, "api")
os.makedirs(API_DIR, exist_ok=True)


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def save_json(path, data):
    """保存 JSON 文件（相对路径视作 api 子目录）"""
    filepath = os.path.join(API_DIR, path)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    size = len(json.dumps(data))
    print(f"  ✓ {path} ({size:,} bytes)")


def export_strategies():
    """GET /api/strategies"""
    db = get_db()
    rows = db.execute("SELECT id, name, tag, status, version FROM strategies WHERE id != 'folio' ORDER BY id").fetchall()

    strategies = []
    for r in rows:
        sid = r["id"]
        # 今日收益
        nav_row = db.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date DESC LIMIT 2", [sid]
        ).fetchall()
        today_ret = 0.0
        if len(nav_row) >= 2:
            today_ret = round(float(nav_row[0]["nav"]) / float(nav_row[1]["nav"]) - 1, 4)

        # KPI
        annual_ret = 0.0
        sharpe = 0.0
        kpi = db.execute("SELECT annual_return, sharpe FROM kpis WHERE strategy_id=?", [sid]).fetchone()
        if kpi:
            annual_ret = kpi["annual_return"]
            sharpe = kpi["sharpe"]

        # spark — 最近 30 个净值点
        spark_navs = db.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date ASC", [sid]
        ).fetchall()
        spark = []
        if len(spark_navs) >= 2:
            step = max(1, len(spark_navs) // 30)
            spark = [float(spark_navs[i]["nav"]) for i in range(0, len(spark_navs), step)][:30]

        strategies.append({
            "id": sid, "name": r["name"], "tag": r["tag"],
            "status": r["status"], "version": r["version"],
            "annualReturn": annual_ret, "sharpe": sharpe, "todayReturn": today_ret,
            "spark": spark,
        })

    save_json("strategies.json", strategies)
    db.close()
    return strategies


def export_overview():
    """GET /api/overview — 组合净值 + 个体策略"""
    db = get_db()

    # 查询所有策略 KPI
    rows = db.execute("""
        SELECT s.id, s.name, s.tag, s.status, s.version,
               COALESCE(k.annual_return,0) as annual_return,
               COALESCE(k.total_return,0) as total_return,
               COALESCE(k.sharpe,0) as sharpe,
               COALESCE(k.max_drawdown,0) as max_drawdown,
               COALESCE(k.volatility,0) as volatility
        FROM strategies s
        LEFT JOIN kpis k ON s.id = k.strategy_id
        WHERE s.id != 'folio'
        ORDER BY k.annual_return DESC
    """).fetchall()

    strategies = []
    all_strategy_ids = []
    for r in rows:
        sid = r["id"]
        all_strategy_ids.append(sid)
        # 今日收益
        nav_row = db.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date DESC LIMIT 2", [sid]
        ).fetchall()
        today_ret = 0.0
        if len(nav_row) >= 2:
            today_ret = round(float(nav_row[0]["nav"]) / float(nav_row[1]["nav"]) - 1, 4)

        # spark
        spark_navs = db.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date ASC", [sid]
        ).fetchall()
        spark = []
        if len(spark_navs) >= 2:
            step = max(1, len(spark_navs) // 30)
            spark = [float(spark_navs[i]["nav"]) for i in range(0, len(spark_navs), step)][:30]

        strategies.append({
            "id": sid, "name": r["name"], "tag": r["tag"],
            "status": r["status"], "version": r["version"],
            "annualReturn": r["annual_return"], "totalReturn": r["total_return"],
            "sharpe": r["sharpe"], "maxDrawdown": r["max_drawdown"],
            "volatility": r["volatility"], "todayReturn": today_ret, "spark": spark,
        })

    # Folio 净值（所有策略等权 / 逆波动率加权，简化版）
    folio_nav_map = {}
    for sid in all_strategy_ids:
        navs = db.execute(
            "SELECT date, nav FROM nav_series WHERE strategy_id=? ORDER BY date ASC", [sid]
        ).fetchall()
        for n in navs:
            d = n["date"][:10] if len(n["date"]) > 10 else n["date"]
            if d not in folio_nav_map:
                folio_nav_map[d] = {}
            folio_nav_map[d][sid] = float(n["nav"])

    # 计算等权组合净值
    dates = sorted(folio_nav_map.keys())
    folio_navs = []
    if len(dates) >= 2 and len(all_strategy_ids) >= 1:
        valid_ids = [sid for sid in all_strategy_ids if sid in folio_nav_map[dates[0]]]
        if valid_ids:
            nav_val = 1.0
            for i, d in enumerate(dates):
                if i > 0:
                    today_ret = 0.0
                    count = 0
                    for sid in valid_ids:
                        if d in folio_nav_map and sid in folio_nav_map[d] and sid in folio_nav_map[dates[i-1]]:
                            prev = folio_nav_map[dates[i-1]][sid]
                            curr = folio_nav_map[d][sid]
                            if prev > 0:
                                today_ret += (curr / prev - 1)
                                count += 1
                    if count > 0:
                        today_ret /= count
                        nav_val *= (1 + today_ret)
                folio_navs.append(nav_val)

    save_json("overview.json", {
        "folioDates": dates,
        "folioNavValues": folio_navs,
        "strategies": strategies,
    })
    db.close()


def export_strategy_detail(strategy_id):
    """GET /api/strategies/{id}"""
    db = get_db()

    # 净值序列
    nav_rows = db.execute(
        "SELECT date, nav, benchmark_nav, drawdown FROM nav_series WHERE strategy_id=? ORDER BY date ASC",
        [strategy_id]
    ).fetchall()

    nav_history = [
        {"date": r["date"][:10] if len(r["date"]) > 10 else r["date"],
         "nav": float(r["nav"]),
         "benchmark": float(r["benchmark_nav"]),
         "drawdown": float(r["drawdown"])}
        for r in nav_rows
    ]

    # KPI
    kpi = db.execute("SELECT * FROM kpis WHERE strategy_id=?", [strategy_id]).fetchone()
    kpis = {}
    if kpi:
        kpis = {
            "totalReturn": kpi["total_return"] or 0,
            "annualReturn": kpi["annual_return"] or 0,
            "sharpe": kpi["sharpe"] or 0,
            "maxDrawdown": kpi["max_drawdown"] or 0,
            "winRate": kpi["win_rate"] or 0,
            "volatility": kpi["volatility"] or 0,
            "alpha": kpi["alpha"] or 0,
            "beta": kpi["beta"] or 0,
            "sortino": kpi["sortino"] or 0,
            "calmar": kpi["calmar"] or 0,
        }

    # 持仓
    holdings_rows = db.execute(
        "SELECT * FROM holdings WHERE strategy_id=? ORDER BY weight DESC", [strategy_id]
    ).fetchall()
    holdings = [
        {"id": r["id"], "strategy_id": r["strategy_id"], "code": r["code"],
         "name": r["name"], "industry": r["industry"], "qty": r["qty"],
         "cost": r["cost"], "price": r["price"], "value": r["value"],
         "pnl": r["pnl"], "weight": r["weight"], "pnlPct": r["pnl_pct"]}
        for r in holdings_rows
    ]

    # 交易记录
    trades_rows = db.execute(
        "SELECT * FROM trades WHERE strategy_id=? ORDER BY time DESC LIMIT 50", [strategy_id]
    ).fetchall()
    trades = [
        {"id": r["id"], "strategy_id": r["strategy_id"], "time": r["time"],
         "code": r["code"], "name": r["name"], "side": r["side"],
         "price": r["price"], "qty": r["qty"], "amount": r["amount"], "fee": r["fee"]}
        for r in trades_rows
    ]

    result = {
        "navHistory": nav_history,
        "kpis": kpis,
        "holdings": holdings,
        "trades": trades,
    }
    save_json(f"strategies/{strategy_id}.json", result)
    db.close()


def export_strategy_source(strategy_id):
    """GET /api/strategies/{id}/source"""
    db = get_db()
    row = db.execute("SELECT source_code FROM strategies WHERE id=?", [strategy_id]).fetchone()
    source = row["source_code"] if row else ""
    save_json(f"strategies/{strategy_id}_source.json", {"source": source})
    db.close()


def export_trades():
    """GET /api/trades"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM trades ORDER BY time DESC LIMIT 100"
    ).fetchall()
    trades = [
        {"id": r["id"], "strategy_id": r["strategy_id"], "time": r["time"],
         "code": r["code"], "name": r["name"], "side": r["side"],
         "price": r["price"], "qty": r["qty"], "amount": r["amount"], "fee": r["fee"]}
        for r in rows
    ]
    save_json("trades.json", {"total": len(trades), "page": 1, "pageSize": 100, "rows": trades})
    db.close()


def export_positions():
    """GET /api/positions"""
    db = get_db()
    holdings = db.execute("""
        SELECT h.*, s.name as strategy_name FROM holdings h
        JOIN strategies s ON h.strategy_id = s.id
        ORDER BY h.value DESC
    """).fetchall()

    positions = []
    for r in holdings:
        positions.append({
            "code": r["code"], "name": r["name"], "industry": r["industry"],
            "strategy_id": r["strategy_id"], "strategy_name": r["strategy_name"],
            "qty": r["qty"], "price": r["price"], "value": r["value"],
            "weight": r["weight"], "pnl": r["pnl"], "pnlPct": r["pnl_pct"],
        })

    # 聚合统计
    industries = {}
    for p in positions:
        ind = p["industry"] or "其他"
        industries[ind] = industries.get(ind, 0) + (p["value"] or 0)

    save_json("positions.json", {
        "holdings": positions,
        "totalValue": sum(p["value"] or 0 for p in positions),
        "industryBreakdown": [{"name": k, "value": v} for k, v in sorted(industries.items(), key=lambda x: -x[1])],
    })
    db.close()


def export_risk():
    """GET /api/risk/overview"""
    db = get_db()

    # 所有策略的回撤和月度收益
    strategies = db.execute("SELECT id FROM strategies WHERE id != 'folio'").fetchall()
    risk_data = []
    for s in strategies:
        sid = s["id"]
        kpi = db.execute("SELECT * FROM kpis WHERE strategy_id=?", [sid]).fetchone()
        if not kpi:
            continue

        nav = db.execute(
            "SELECT date, nav FROM nav_series WHERE strategy_id=? ORDER BY date ASC", [sid]
        ).fetchall()
        navs = np.array([float(r["nav"]) for r in nav])
        daily_ret = navs[1:] / navs[:-1] - 1

        # 月度收益
        monthly = []
        current_month = None
        month_start_nav = 0
        for i, r in enumerate(nav):
            m = r["date"][:7]
            if m != current_month:
                if current_month is not None and month_start_nav > 0:
                    monthly.append({
                        "month": current_month,
                        "return": round(float(navs[i-1] / month_start_nav - 1), 4),
                    })
                current_month = m
                month_start_nav = float(r["nav"])

        if current_month is not None and month_start_nav > 0:
            monthly.append({
                "month": current_month,
                "return": round(float(navs[-1] / month_start_nav - 1), 4),
            })

        risk_data.append({
            "strategy_id": sid,
            "name": db.execute("SELECT name FROM strategies WHERE id=?", [sid]).fetchone()["name"],
            "maxDrawdown": kpi["max_drawdown"] or 0,
            "volatility": kpi["volatility"] or 0,
            "sharpe": kpi["sharpe"] or 0,
            "monthlyReturns": monthly[-24:],  # 最近24个月
        })

    save_json("risk_overview.json", {"strategies": risk_data, "maxDrawdownAlerts": []})
    db.close()


def export_portfolios():
    """GET /api/portfolios"""
    db = get_db()
    rows = db.execute("SELECT id, name, items FROM portfolios ORDER BY id").fetchall()
    portfolios = []
    for r in rows:
        try:
            items = json.loads(r["items"])
        except:
            items = []
        portfolios.append({"id": r["id"], "name": r["name"], "items": items})
    save_json("portfolios.json", portfolios)
    db.close()


def export_health():
    """GET /api/health"""
    db = get_db()
    count = db.execute("SELECT COUNT(*) as n FROM strategies WHERE id != 'folio'").fetchone()["n"]
    save_json("health.json", {"status": "ok", "strategyCount": count, "engine": "qlib+backtrader"})
    db.close()


def export_backtests():
    """GET /api/backtests (always empty on static site)"""
    save_json("backtests.json", {"total": 0, "jobs": []})


def main():
    print("=" * 50)
    print("[Export] 导出 API 数据为静态 JSON...")

    # 策略列表
    strategies = export_strategies()
    print(f"  策略: {len(strategies)} 个")

    # 总览
    export_overview()

    # 每个策略详情
    for s in strategies:
        sid = s["id"]
        export_strategy_detail(sid)
        export_strategy_source(sid)

    # 交易、持仓、风险
    export_trades()
    export_positions()
    export_risk()
    export_portfolios()
    export_health()
    export_backtests()

    print(f"\n✅ 全部导出到 {API_DIR}")
    print(f"   文件总计: {len(os.listdir(API_DIR))} 个")


if __name__ == "__main__":
    main()
