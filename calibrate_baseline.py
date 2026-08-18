"""
calibrate_baseline.py — MCD CTR 基准 v3.0 校准脚本
读 CNN历史备份.xlsx → 按指数衰减加权聚合 6 个维度 CTR → 输出新 ctr_baseline.json

参数：
  λ = 0.010，半衰期 ≈ 69 天
  D = 数据最新日期（2026-08-16）
  w(d) = exp(-λ × (D - d).days)
  weighted_CTR = Σ(w × click) / Σ(w × reach)

跳过渠道：微信订阅（全量 NaN，保留 v2 旧值）
"""
import pandas as pd
import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ── 配置 ──
SOURCE_XLSX = r"c:\Users\a952462\常用文件\数据\CNN历史备份.xlsx"
TARGET_JSON = r"c:\Users\a952462\OneDrive - ATOS\桌面\mcd-ctr-predictor-main\ctr_baseline.json"
OLD_JSON_BAK = r"c:\Users\a952462\OneDrive - ATOS\桌面\mcd-ctr-predictor-main\ctr_baseline_v2.json.bak"
LAMBDA = 0.010
SKIP_CHANNELS = ["微信订阅"]
MIN_REACH_FOR_OWNER = 10000
MIN_REACH_FOR_CHAR = 5000
HALF_LIFE_DAYS = round(math.log(2) / LAMBDA, 1)

# ── 加载 + 清洗 ──
df = pd.read_excel(SOURCE_XLSX, sheet_name=0)
df.columns = ['发送日期','计划类型','渠道','Plan ID','Unit ID','Plan名称','预算owner',
              '是否用券','预计触达','触达成功','点击人次','触发下单人次','触发GC',
              '触发Sales','Message ID','信息标题','信息内容']

df = df.dropna(subset=['发送日期','渠道','触达成功','点击人次'])
df['触达成功'] = df['触达成功'].astype(int)
df['点击人次'] = df['点击人次'].astype(int)
df['发送日期'] = pd.to_datetime(df['发送日期'])  # 统一 datetime
df['日期'] = df['发送日期'].dt.normalize()
D = df['日期'].max()
df['days_old'] = (D - df['日期']).dt.days
df['w'] = df['days_old'].apply(lambda d: math.exp(-LAMBDA * d))

print(f"数据加载: {len(df)} 条 Plan, 日期 {df['日期'].min().date()} ~ {D.date()}")
print(f"λ={LAMBDA}, 半衰期≈{HALF_LIFE_DAYS} 天")

# ── 工具 ──
def weighted_ctr(sub):
    w_click = (sub['w'] * sub['点击人次']).sum()
    w_reach = (sub['w'] * sub['触达成功']).sum()
    return w_click / w_reach if w_reach > 0 else None

def get_char_range(title):
    n = len(str(title).strip())
    for hi, lbl in [(6,"5-6字"),(8,"7-8字"),(10,"9-10字"),(12,"11-12字"),
                    (14,"13-14字"),(16,"15-16字"),(18,"17-18字"),(20,"19-20字"),
                    (22,"21-22字"),(24,"23-24字")]:
        if n <= hi: return lbl
    return f"{n}字"

# ── 1. 渠道 ──
# 读 v2 备份（避免被本脚本上次运行覆盖的 v3 影响"沿用旧值"的逻辑）
old_path = OLD_JSON_BAK if Path(OLD_JSON_BAK).exists() else TARGET_JSON
old = json.load(open(old_path, encoding='utf-8'))
print(f"读旧 baseline: {old_path} (version={old.get('version','?')})")
dim_channel = {}
for ch in df['渠道'].unique():
    sub = df[df['渠道'] == ch]
    ctr = weighted_ctr(sub)
    if ctr is not None and ch not in SKIP_CHANNELS:
        dim_channel[ch] = round(ctr, 6)
# 微信订阅保留 v2 值
if '微信订阅' in old['dimensions']['渠道']['data']:
    dim_channel['微信订阅'] = old['dimensions']['渠道']['data']['微信订阅']

# ── 2. 渠道×用券 ──
dim_coupon = {}
for (ch, coupon), sub in df.groupby(['渠道','是否用券']):
    if ch in SKIP_CHANNELS: continue
    ctr = weighted_ctr(sub)
    if ctr is not None:
        dim_coupon[f"{ch}_{coupon}"] = round(ctr, 6)

# ── 3. 渠道×预算owner（过滤小样本）──
dim_owner = {}
for (ch, owner), sub in df.groupby(['渠道','预算owner']):
    if ch in SKIP_CHANNELS: continue
    if sub['触达成功'].sum() < MIN_REACH_FOR_OWNER: continue
    ctr = weighted_ctr(sub)
    if ctr is not None:
        dim_owner[f"{ch}_{owner}"] = round(ctr, 6)

# ── 4. 渠道×计划类型 ──
dim_plan = {}
for (ch, plan), sub in df.groupby(['渠道','计划类型']):
    if ch in SKIP_CHANNELS: continue
    ctr = weighted_ctr(sub)
    if ctr is not None:
        dim_plan[f"{ch}_{plan}"] = round(ctr, 6)

# ── 5. 渠道×工作日类型 ──
df['工作日类型'] = df['日期'].dt.weekday.apply(lambda x: '工作日' if x < 5 else '非工作日')
dim_workday = {}
for (ch, wd), sub in df.groupby(['渠道','工作日类型']):
    if ch in SKIP_CHANNELS: continue
    ctr = weighted_ctr(sub)
    if ctr is not None:
        dim_workday[f"{ch}_{wd}"] = round(ctr, 6)

# ── 6. 渠道×标题字数 ──
df['标题字数'] = df['Plan名称'].apply(get_char_range)
dim_char = {}
for (ch, rng), sub in df.groupby(['渠道','标题字数']):
    if ch in SKIP_CHANNELS: continue
    if sub['触达成功'].sum() < MIN_REACH_FOR_CHAR: continue
    ctr = weighted_ctr(sub)
    if ctr is not None:
        dim_char[f"{ch}_{rng}"] = round(ctr, 6)

# ── 7. 时段_小时（xlsx 没小时字段，沿用 v2 旧值）──
dim_hour = old['dimensions'].get('时段_小时', {}).get('data', {})

# ── 写入新 JSON ──
new_data = {
    "version": "v3.0",
    "last_updated": "2026-08-18",
    "last_refreshed_at": "2026-08-18",
    "last_refreshed_by": "claude-session-2026-08-18",
    "data_window_start": str(df['日期'].min().date()),
    "data_window_end": str(D.date()),
    "calibration_lambda": LAMBDA,
    "calibration_half_life_days": HALF_LIFE_DAYS,
    "weighted_method": "exponential_decay",
    "source": f"CNN历史备份.xlsx ({df['日期'].min().date()} ~ {D.date()}, 加权聚合, λ={LAMBDA}, 半衰期≈{HALF_LIFE_DAYS}天)",
    "_note": f"CTR 值均为小数形式。v3 改用指数衰减加权，半衰期 {HALF_LIFE_DAYS} 天，越靠近 {D.date()} 的数据权重越高。微信订阅渠道本期无新样本，保留 v2 旧值。",
    "dimensions": {
        "渠道": {
            "description": "各渠道整体 CTR（指数加权）",
            "data": dim_channel
        },
        "渠道_x_是否用券": {
            "description": "渠道 × 是否带券（指数加权）",
            "data": dim_coupon
        },
        "渠道_x_预算owner": {
            "description": f"渠道 × 预算 Owner（指数加权，reach≥{MIN_REACH_FOR_OWNER} 过滤）",
            "data": dim_owner
        },
        "渠道_x_计划类型": {
            "description": "渠道 × 计划类型（指数加权）",
            "data": dim_plan
        },
        "渠道_x_工作日类型": {
            "description": "渠道 × 工作日类型（指数加权）",
            "data": dim_workday
        },
        "渠道_x_标题字数": {
            "description": f"渠道 × 标题字数区间（指数加权，reach≥{MIN_REACH_FOR_CHAR} 过滤）",
            "data": dim_char
        },
        "时段_小时": {
            "description": "整点小时 CTR（v2 数据源保留，未加权）",
            "data": dim_hour
        }
    }
}

with open(TARGET_JSON, 'w', encoding='utf-8') as f:
    json.dump(new_data, f, ensure_ascii=False, indent=2)

# ── 输出统计 ──
print(f"\n写入: {TARGET_JSON}")
print(f"  渠道:        {len(dim_channel)} 个 (旧 v2: 6)")
print(f"  渠道×用券:    {len(dim_coupon)} 个 (旧 v2: 12)")
print(f"  渠道×owner:   {len(dim_owner)} 个 (旧 v2: 47)")
print(f"  渠道×计划类型: {len(dim_plan)} 个 (旧 v2: 11)")
print(f"  渠道×工作日:   {len(dim_workday)} 个 (旧 v2: 12)")
print(f"  渠道×字数:     {len(dim_char)} 个 (旧 v2: ~45)")
print(f"  时段_小时:     {len(dim_hour)} 个 (旧 v2: 11, 7-17时)")

# ── 关键渠道 CTR 对比 ──
print(f"\n=== 关键渠道 CTR 对比（v2 加权 vs v3 加权）===")
print(f"{'渠道':<20} {'v2':<10} {'v3 加权':<10} {'Δ%':<10}")
for ch in ['APP Push', '企微1v1', '微信小程序订阅消息', '微信公众号推文', '短信']:
    old_v = old['dimensions']['渠道']['data'].get(ch, None)
    new_v = dim_channel.get(ch, None)
    if old_v and new_v:
        delta = (new_v - old_v) / old_v * 100
        print(f"{ch:<20} {old_v:<10.4f} {new_v:<10.4f} {delta:+.1f}%")