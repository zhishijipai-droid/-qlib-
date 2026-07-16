"""用新成本数据更新 strategy.html 中的三个策略"""
import json, os

HTML_PATH = "D:/bigquant/output/strategy.html"
OUTPUT_DIR = "D:/bigquant/output"

def load_json(name):
    with open(os.path.join(OUTPUT_DIR, name), encoding="utf-8") as f:
        return json.load(f)['strategies'][0]

s1 = load_json("small_cap_100yi.json")
s2 = load_json("micro_cap_400.json")
s3 = load_json("dividend_yield_v5.json")

for s, name in [(s1, "M1"), (s2, "M2"), (s3, "M3")]:
    print(f"{name}: 年化{s['annual_return']}% 夏普{s['sharpe']} 回撤{s['max_drawdown']}%")

with open(HTML_PATH, encoding="utf-8") as f:
    html = f.read()

# Replace M1
m1_s = html.find('var M1={')
m1_e = html.find(';', m1_s)
html = html[:m1_s] + f'var M1={json.dumps(s1, ensure_ascii=False)};' + html[m1_e+1:]

# Replace M2
m2_s = html.find('var M2={')
m2_e = html.find(';', m2_s)
html = html[:m2_s] + f'var M2={json.dumps(s2, ensure_ascii=False)};' + html[m2_e+1:]

# Replace M3
m3_s = html.find('var M3={')
m3_e = html.find(';', m3_s)
html = html[:m3_s] + f'var M3={json.dumps(s3, ensure_ascii=False)};' + html[m3_e+1:]

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✅ 已更新 ({len(html)/1024:.0f} KB)")
print(f"成本设置: 万3(双边) + 千1印花税, 无滑点 (聚宽默认)")
