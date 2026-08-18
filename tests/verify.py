"""
verify.py — MCD CTR Predictor 验证脚本（不依赖 pytest）
用法：python tests/verify.py
退出码：0 全过；1 有失败。
"""
import sys, os, ast, json, re, types
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ── 路径 ──
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8")

# ── 抽取 ctr_predictor.py 函数定义 + 常量（绕过 UI 渲染）──
src = open(ROOT / "ctr_predictor.py", encoding="utf-8").read()
tree = ast.parse(src)
extracted = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        extracted.append(ast.unparse(node))
    elif isinstance(node, ast.Assign):
        is_bl = any(isinstance(t, ast.Name) and t.id == "BASELINE" for t in node.targets)
        if is_bl:
            continue
        extracted.append(ast.unparse(node))

class _FakeSt:
    def __getattr__(self, name):
        if name in ("cache_data", "cache_resource"):
            return lambda f: f
        return lambda *a, **k: None

ns = {"__builtins__": __builtins__, "json": json, "re": re,
      "time": __import__("time"), "pd": pd, "st": _FakeSt()}
# 先注入 BASELINE（函数定义体内部引用）
BASELINE = json.load(open(ROOT / "ctr_baseline.json", encoding="utf-8"))
ns["BASELINE"] = BASELINE
exec("\n".join(extracted), ns)

# 函数引用
get_baseline_ctr = ns["get_baseline_ctr"]
get_time_multiplier = ns["get_time_multiplier"]
get_char_range = ns["get_char_range"]
suggest_char_range = ns["suggest_char_range"]
build_context_for_llm = ns["build_context_for_llm"]
auto_detect = ns["auto_detect"]
_check_baseline_age = ns["_check_baseline_age"]
OPTIMAL_CHARS = ns["OPTIMAL_CHARS"]

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f" ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" ({detail})" if detail else ""))


# ════════════════════════════════════════════════
print("\n[1] char_range 接线（v3 数据）")
# ════════════════════════════════════════════════
v = get_baseline_ctr("APP Push", None, None, None, None, "11-12字")
check("APP Push 11-12字 → 非空", v is not None, f"={v}")
v2 = get_baseline_ctr("APP Push", None, None, None, None, None)
check("APP Push 整体 → 非空", v2 is not None, f"={v2}")

# ════════════════════════════════════════════════
print("\n[2] 计划类型白名单统一")
# ════════════════════════════════════════════════
v3 = get_baseline_ctr("APP Push", None, None, "常规Plan", None, "11-12字")
check("常规Plan 不命中计划维度（回退 char_range）",
      v3 == get_baseline_ctr("APP Push", None, None, None, None, "11-12字"))
v4 = get_baseline_ctr("APP Push", None, None, "普通Plan", None)
check("普通Plan 命中", v4 is not None, f"={v4}")

# ════════════════════════════════════════════════
print("\n[3] auto_detect 严格匹配")
# ════════════════════════════════════════════════
df = pd.DataFrame(columns=["标题", "subtitle_test", "title", "内容"])
check("'标题' 严格命中", auto_detect(df, ["标题", "title"]) == "标题")
check("'title' 不误匹配 subtitle_test", auto_detect(df, ["title"]) == "title")

# ════════════════════════════════════════════════
print("\n[4] time_str 四级回退 + 区间中点")
# ════════════════════════════════════════════════
check("HH:MM '10:30' → 10", abs(get_time_multiplier("10:30") - get_time_multiplier("10时")) < 1e-9)
check("HH时 '10时' → 10", abs(get_time_multiplier("10时") - get_time_multiplier("10")) < 1e-9)
check("纯数字 '10' → 10", get_time_multiplier("10") > 0)
check("含文字 '上午10:30' → 10", get_time_multiplier("上午10:30") > 0)
check("空 → 1.0", get_time_multiplier("") == 1.0)
check("无数字 → 1.0", get_time_multiplier("abc") == 1.0)
check("非法 hour → 1.0", get_time_multiplier("25:00") == 1.0)
# 区间中点（新增）
m_8_10 = get_time_multiplier("8-10时")
m_9    = get_time_multiplier("9时")
check("区间 '8-10时' 取中点 9",
      abs(m_8_10 - m_9) < 1e-9,
      f"8-10={m_8_10:.4f}, 9={m_9:.4f}")
m_8_18 = get_time_multiplier("8-18")
m_13    = get_time_multiplier("13时")
check("区间 '8-18' 取中点 13",
      abs(m_8_18 - m_13) < 1e-9,
      f"8-18={m_8_18:.4f}, 13={m_13:.4f}")

# ════════════════════════════════════════════════
print("\n[5] build_context_for_llm 含 char_data")
# ════════════════════════════════════════════════
ctx = build_context_for_llm(BASELINE)
check("含'各渠道高CTR标题字数区间'段落",
      "各渠道高CTR标题字数区间" in ctx)
check("含 APP Push 数据",
      "APP Push:" in ctx and "%" in ctx)

# ════════════════════════════════════════════════
print("\n[6] JSON v3 元信息")
# ════════════════════════════════════════════════
check("version = v3.0", BASELINE["version"] == "v3.0")
check("calibration_lambda = 0.01", BASELINE["calibration_lambda"] == 0.01)
check("weighted_method = exponential_decay",
      BASELINE["weighted_method"] == "exponential_decay")
check("data_window_end 字段存在",
      "data_window_end" in BASELINE)

# ════════════════════════════════════════════════
print("\n[7] 微信订阅保留 v2 值")
# ════════════════════════════════════════════════
check("微信订阅 = 0.034362（v2 旧值）",
      BASELINE["dimensions"]["渠道"]["data"]["微信订阅"] == 0.034362)

# ════════════════════════════════════════════════
print("\n[8] suggest_char_range")
# ════════════════════════════════════════════════
r1 = suggest_char_range("APP Push", "麦乐鸡")
check("偏短提示", "偏短" in r1 and "5-12字" in r1)
r2 = suggest_char_range("APP Push", "麦乐鸡5折限时抢")
check("区间内提示", "最优区间内" in r2)

# ════════════════════════════════════════════════
print("\n[9] missing_title 判定（间接：pandas 语义）")
# ════════════════════════════════════════════════
title_valid = pd.Series(["麦乐鸡", "nan", ""]).str.strip().str.lower().replace("nan", "").ne("").any()
check("单非空 → valid=True", bool(title_valid))
title_all_empty = pd.Series(["nan", "", "  "]).str.strip().str.lower().replace("nan", "").eq("").all()
check("全 nan/空 → empty=True", bool(title_all_empty))

# ════════════════════════════════════════════════
print("\n[10] OPTIMAL_CHARS 完整")
# ════════════════════════════════════════════════
check("APP Push = 5-12字", OPTIMAL_CHARS["APP Push"] == "5-12字")
check("企微1v1 = 13-18字", OPTIMAL_CHARS["企微1v1"] == "13-18字")

# ════════════════════════════════════════════════
print("\n[11] 陈旧数据提醒（新功能）")
# ════════════════════════════════════════════════
# 用今天做 today
today = date.today()
age = _check_baseline_age(BASELINE, today)
check("v3 当前 baseline 计算 age 成功", age is not None, f"age={age}天")

# 模拟 100 天前
old_bl = {**BASELINE, "data_window_end": (today - timedelta(days=100)).isoformat()}
age100 = _check_baseline_age(old_bl, today)
check("100 天前 → age=100", age100 == 100, f"={age100}")

# 模拟 30 天前（未过期）
fresh_bl = {**BASELINE, "data_window_end": (today - timedelta(days=30)).isoformat()}
age30 = _check_baseline_age(fresh_bl, today)
check("30 天前 → age=30（不触发 warn）", age30 == 30, f"={age30}")

# 缺字段
no_window = {k: v for k, v in BASELINE.items() if k != "data_window_end"}
age_none = _check_baseline_age(no_window, today)
check("无 data_window_end → None", age_none is None)

# 异常日期
bad_bl = {**BASELINE, "data_window_end": "not-a-date"}
age_bad = _check_baseline_age(bad_bl, today)
check("异常日期格式 → None", age_bad is None)

# ════════════════════════════════════════════════
print("\n" + "═" * 50)
print(f"结果：{PASS} 通过 / {FAIL} 失败")
print("═" * 50)
sys.exit(0 if FAIL == 0 else 1)