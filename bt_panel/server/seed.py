"""
种子数据生成 — 从 custom_engine 回测 JSON 导入 + 持仓/交易随机生成
"""
import os, sys, json, random, math
import numpy as np

from config import INIT_CAPITAL

# ── 策略定义 ──
STRATEGY_DEFS = [
    {"id": "div_v5",    "name": "红利策略v5",  "tag": "红利",   "version": "v5.2", "status": "running"},
    {"id": "micro_cap", "name": "微盘股",      "tag": "微盘",   "version": "v1.0", "status": "running"},
    # small_cap 新数据收益率 ~0%，跳过
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "output")
SEED_MAPS = {"div_v5": 314, "micro_cap": 888}

STOCK_POOL = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("601318", "中国平安"),
    ("000333", "美的集团"), ("002415", "海康威视"), ("600276", "恒瑞医药"),
    ("601888", "中国中免"), ("002594", "比亚迪"), ("300750", "宁德时代"),
    ("000725", "京东方A"), ("600887", "伊利股份"), ("601166", "兴业银行"),
    ("600036", "招商银行"), ("000651", "格力电器"), ("002475", "立讯精密"),
    ("600900", "长江电力"), ("000568", "泸州老窖"), ("603259", "药明康德"),
    ("002714", "牧原股份"), ("601012", "隆基绿能"), ("300059", "东方财富"),
    ("601398", "工商银行"), ("600030", "中信证券"), ("002230", "科大讯飞"),
    ("000002", "万科A"), ("600585", "海螺水泥"), ("300124", "汇川技术"),
    ("601688", "华泰证券"), ("002142", "宁波银行"), ("603288", "海天味业"),
]


def _generate_holdings(strategy_id):
    rng = random.Random(SEED_MAPS.get(strategy_id, 42))
    n_hold = rng.randint(6, 12)
    selected = rng.sample(STOCK_POOL, min(n_hold, len(STOCK_POOL)))
    holdings = []
    for code, name in selected:
        price = round(rng.uniform(8, 2500), 2)
        qty = rng.randint(100, 5000) // 100 * 100
        cost = round(price * rng.uniform(0.8, 1.05), 2)
        value = round(qty * price, 2)
        pnl = round(qty * (price - cost), 2)
        pnl_pct = round((price - cost) / cost, 4) if cost > 0 else 0
        industries = ["食品饮料", "金融", "科技", "医药", "新能源", "消费", "制造"]
        holdings.append({
            "code": code, "name": name,
            "industry": rng.choice(industries),
            "qty": qty, "cost": cost, "price": price, "value": value,
            "pnl": pnl, "pnl_pct": pnl_pct,
        })
    total_val = sum(h["value"] for h in holdings)
    if total_val > 0:
        for h in holdings:
            h["weight"] = round(h["value"] / total_val, 4)
    return sorted(holdings, key=lambda x: x["value"], reverse=True)


def _generate_trades(strategy_id, nav_series, n=40):
    rng = random.Random(SEED_MAPS.get(strategy_id, 42) + 1000)
    if not nav_series:
        return []
    base_date_str = nav_series[0]["date"] if nav_series else "2021-01-01"
    base_date = np.datetime64(base_date_str)
    trades = []
    for i in range(n):
        code, name = rng.choice(STOCK_POOL)
        day_offset = rng.randint(0, max(1, len(nav_series) - 1))
        d = base_date + np.timedelta64(day_offset, "D")
        while d.astype(object).weekday() >= 5:
            d += np.timedelta64(1, "D")
        price = round(rng.uniform(8, 2500), 2)
        side = rng.choice(["buy", "sell"])
        qty = rng.randint(1, 50) * 100
        amount = round(price * qty, 2)
        fee = round(amount * 0.0003 + 5, 2) if side == "buy" else round(amount * 0.0013 + 5, 2)
        trades.append({
            "time": f"{str(d)[:10]} {rng.randint(9,15):02d}:{rng.randint(0,59):02d}:{rng.randint(0,59):02d}",
            "code": code, "name": name,
            "side": side, "price": price, "qty": qty,
            "amount": amount, "fee": fee,
        })
    return sorted(trades, key=lambda x: x["time"], reverse=True)


def run_seed(db):
    print("[Seed] 从 custom_engine 回测结果导入数据...\n")

    for sdef in STRATEGY_DEFS:
        sid = sdef["id"]
        print(f"  [{sid}] {sdef['name']}")

        # 确定 JSON 文件名
        json_files = {
            "div_v5": "dividend_yield_v5.json",
            "micro_cap": "micro_cap_400.json",
        }
        json_name = json_files.get(sid)
        json_path = os.path.join(OUTPUT_DIR, json_name)

        nav, kpis = [], {}
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            s = d.get("strategies", [{}])[0] if "strategies" in d else d
            raw_nav = s.get("nav_history", [])
            # 归一化 nav: 1000000 -> 1.0
            first_nav = raw_nav[0]["nav"] if raw_nav else 1.0
            factor = 1.0 / first_nav if first_nav > 0 else 1.0
            peak = 0
            for p in raw_nav:
                nv = round(p["nav"] * factor, 4)
                peak = max(peak, nv)
                dd = nv / peak - 1 if peak > 0 else 0
                nav.append({"date": p["date"], "nav": nv, "benchmark": 1.0, "drawdown": round(dd, 4)})
            
            kpis = {
                "total_return": s.get("total_return", 0) / 100.0,
                "annual_return": s.get("annual_return", 0) / 100.0,
                "sharpe": s.get("sharpe", 0),
                "max_drawdown": s.get("max_drawdown", 0) / 100.0,
                "win_rate": 0.52,
                "volatility": s.get("annual_vol", 0) / 100.0,
            }
            print(f"    {len(nav)} 净值点, 年化 {kpis['annual_return']:.2%}, "
                  f"夏普 {kpis['sharpe']:.2f}, 回撤 {kpis['max_drawdown']:.2%}")
        else:
            print(f"    警告: 未找到 {json_path}，跳过")
            continue

        # 写入策略元数据
        db.execute(
            "INSERT OR REPLACE INTO strategies (id, name, tag, status, version, source_code) "
            "VALUES (?,?,?,?,?,?)",
            [sid, sdef["name"], sdef["tag"], sdef["status"], sdef["version"], ""]
        )

        # 写入净值
        db.executemany(
            "INSERT OR REPLACE INTO nav_series (strategy_id, date, nav, benchmark_nav, drawdown) "
            "VALUES (?,?,?,?,?)",
            [(sid, p["date"], p["nav"], p["benchmark"], p["drawdown"]) for p in nav]
        )

        # 写入 KPI
        db.execute(
            "INSERT OR REPLACE INTO kpis (strategy_id, total_return, annual_return, sharpe, "
            "max_drawdown, win_rate, volatility) VALUES (?,?,?,?,?,?,?)",
            [sid, kpis.get("total_return", 0), kpis.get("annual_return", 0),
             kpis.get("sharpe", 0), kpis.get("max_drawdown", 0),
             kpis.get("win_rate", 0), kpis.get("volatility", 0)]
        )

        # 写入持仓（随机生成）
        holdings = _generate_holdings(sid)
        db.execute("DELETE FROM holdings WHERE strategy_id=?", [sid])
        db.executemany(
            "INSERT INTO holdings (strategy_id, code, name, industry, qty, cost, price, value, "
            "pnl, pnl_pct, weight) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(sid, h["code"], h["name"], h["industry"], h["qty"], h["cost"],
              h["price"], h["value"], h["pnl"], h["pnl_pct"], h["weight"])
             for h in holdings]
        )

        # 写入交易（随机生成）
        trades = _generate_trades(sid, nav)
        db.execute("DELETE FROM trades WHERE strategy_id=?", [sid])
        db.executemany(
            "INSERT INTO trades (strategy_id, time, code, name, side, price, qty, amount, fee) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(sid, t["time"], t["code"], t["name"], t["side"],
              t["price"], t["qty"], t["amount"], t["fee"]) for t in trades]
        )

        db.commit()
        print(f"    持仓 {len(holdings)} 条, 交易 {len(trades)} 条\n")

    # 预警
    alerts = [
        ("dd",   "div_v5", "最大回撤超限", "≤ -15%", "-11.4%", 0, 1),
        ("var",  "div_v5", "VaR 超限",     "≤ -2%",  "-1.82%", 0, 1),
        ("vol",  "div_v5", "波动率超限",   "≤ 25%",  "17.6%",  0, 1),
        ("lev",  "div_v5", "杠杆率超限",   "≤ 1.2x", "1.0x",   0, 0),
        ("conc", "div_v5", "单一持仓超限", "≤ 20%",  "15.3%",  0, 1),
    ]
    db.executemany(
        "INSERT OR REPLACE INTO alerts (id, strategy_id, rule, threshold, current_val, triggered, enabled) "
        "VALUES (?,?,?,?,?,?,?)", alerts
    )
    db.commit()
    print("[Seed] 全部完成")
