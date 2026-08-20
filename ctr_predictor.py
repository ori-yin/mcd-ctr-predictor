"""
MCD CTR 预测工具 v2 — Streamlit App
功能：上传文案列表 → LLM批量预测CTR + 改进建议
依赖：pip install streamlit pandas openai python-dateutil
运行：streamlit run ctr_predictor.py
"""

import streamlit as st
import pandas as pd
import json
import re
import time
from datetime import datetime

from styles import get_css

# ── Page Config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="MCD CTR 预测工具",
    page_icon="薯条",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── 注入样式 ─────────────────────────────────────────────────
st.markdown(get_css(), unsafe_allow_html=True)

# ── Load CTR Baseline ──────────────────────────────────────────────
@st.cache_data
def load_baseline(path: str = "ctr_baseline.json") -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

BASELINE = load_baseline()

# ── Constants ─────────────────────────────────────────────────────
CHANNEL_KEYS = ["APP Push", "企微1v1", "微信公众号推文", "微信小程序订阅消息", "微信订阅", "短信"]

OPTIMAL_CHARS = {
    "APP Push": "5-12字",
    "企微1v1": "13-18字",
    "微信公众号推文": "15-20字",
    "微信小程序订阅消息": "5-10字",
    "微信订阅": "7-14字",
    "短信": "9-12字",
}
# 注：ctr_baseline.json 的 渠道_x_标题字数.建议范围 也是一份"建议范围"，
# 两处手工维护，改其中一处时请同步改另一处，避免漂移。

# ── Baseline lookup ────────────────────────────────────────────────
def get_baseline_ctr(channel: str, coupon: str = None, workday: str = None,
                     plan_type: str = None, owner: str = None,
                     char_range: str = None) -> float:
    ch = channel.strip()
    d = BASELINE.get("dimensions", {})

    # 标题字数优先
    if char_range and f"{ch}_{char_range}" in d.get("渠道_x_标题字数", {}).get("data", {}):
        return d["渠道_x_标题字数"]["data"][f"{ch}_{char_range}"]

    # 渠道 × 计划类型
    if plan_type in ("AARRPlan", "普通Plan") and f"{ch}_{plan_type}" in d.get("渠道_x_计划类型", {}).get("data", {}):
        return d["渠道_x_计划类型"]["data"][f"{ch}_{plan_type}"]

    # 渠道 × 预算owner
    if owner and f"{ch}_{owner}" in d.get("渠道_x_预算owner", {}).get("data", {}):
        return d["渠道_x_预算owner"]["data"][f"{ch}_{owner}"]

    # 渠道 × 是否用券
    if coupon in ("是", "否"):
        v = d.get("渠道_x_是否用券", {}).get("data", {}).get(f"{ch}_{coupon}")
        if v:
            return v

    # 渠道 × 工作日类型
    if workday in ("工作日", "非工作日"):
        v = d.get("渠道_x_工作日类型", {}).get("data", {}).get(f"{ch}_{workday}")
        if v:
            return v

    # 渠道整体
    return d.get("渠道", {}).get("data", {}).get(ch, None)


def get_time_multiplier(time_str: str) -> float:
    if not time_str:
        return 1.0
    s = str(time_str).strip()
    # 四级回退：HH:MM > X-Y区间(取中点) > HH时 > 任意数字
    # 注：区间分支必须在 HH时 之前，否则 "8-10时" 会被 HH时 抢先匹配成 10
    hour = None
    m = re.search(r"(\d{1,2})\s*:\s*\d{1,2}", s)
    if m:
        hour = int(m.group(1))
    else:
        m = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})", s)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            hour = (lo + hi) // 2 if lo <= hi else (hi + lo) // 2
        else:
            m = re.search(r"(\d{1,2})\s*时", s)
            if m:
                hour = int(m.group(1))
            else:
                m = re.search(r"(\d{1,2})", s)
                if m:
                    hour = int(m.group(1))
    if hour is None or not (0 <= hour <= 23):
        return 1.0
    td = BASELINE.get("dimensions", {}).get("时段_小时", {}).get("data", {})
    if not td:
        return 1.0
    vals = list(td.values())
    overall_avg = sum(vals) / len(vals) if vals else 0.002
    hour_ctr = td.get(f"{hour}时", overall_avg)
    mult = hour_ctr / overall_avg if overall_avg else 1.0
    return max(0.5, min(2.5, mult))


def get_time_suggestion(time_str: str, channel: str) -> str:
    suggestions = {
        "APP Push": "11-14时",
        "企微1v1": "17-18时",
        "微信小程序订阅消息": "5-8时",
        "短信": "9-12时",
    }
    opt = suggestions.get(channel.strip(), "参考时段数据")
    tm = get_time_multiplier(time_str)
    return f"建议发送：{opt}（当前系数{tm:.2f}）" if time_str else ""


def _derive_workday_from_time(time_str: str) -> str:
    """从时间字符串里提取日期，按 weekday 派生『工作日/非工作日』。
    支持常见日期格式（年月日 + 可选时分秒，分隔符 - / . 或 ISO T）。
    解析失败返回空串（不阻断，仅不影响基线查找）。
    """
    if not time_str:
        return ""
    s = str(time_str).strip()
    if s.lower() in ("nan", "nat", ""):
        return ""
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
        "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y.%m.%d",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            d = datetime.strptime(s, fmt)
            return "工作日" if d.weekday() < 5 else "非工作日"
        except ValueError:
            continue
    return ""


def count_chars(text: str) -> int:
    return len(str(text).strip())


def get_char_range(title: str) -> str:
    n = count_chars(title)
    if n <= 6:
        return "5-6字"
    elif n <= 8:
        return "7-8字"
    elif n <= 10:
        return "9-10字"
    elif n <= 12:
        return "11-12字"
    elif n <= 14:
        return "13-14字"
    elif n <= 16:
        return "15-16字"
    elif n <= 18:
        return "17-18字"
    elif n <= 20:
        return "19-20字"
    elif n <= 22:
        return "21-22字"
    elif n <= 24:
        return "23-24字"
    return f"{n}字"


def suggest_char_range(channel: str, title: str) -> str:
    n = count_chars(title)
    optimal = OPTIMAL_CHARS.get(channel.strip(), None)
    if not optimal:
        return ""
    lo_s, hi_s = optimal.split("-")
    lo_n = int(lo_s.replace("字", ""))
    hi_n = int(hi_s.replace("字", ""))
    if lo_n <= n <= hi_n:
        return f"字数{n}字，在{optimal}最优区间内"
    elif n < lo_n:
        return f"字数{n}字，偏短{lo_n - n}字，建议{optimal}"
    else:
        return f"字数{n}字，偏长{n - hi_n}字，建议{optimal}"


# ── Build context for LLM prompt ───────────────────────────────────
def build_context_for_llm(baseline: dict) -> str:
    d = baseline.get("dimensions", {})
    lines = ["【麦当劳Push CTR基准参考】（CTR数值为小数，0.0355 = 3.55%）"]

    ch_data = d.get("渠道", {}).get("data", {})
    if ch_data:
        lines.append("\n各渠道CTR基准：")
        for k, v in sorted(ch_data.items(), key=lambda x: -x[1]):
            lines.append(f"  {k}: {v*100:.2f}%")

    coupon_data = d.get("渠道_x_是否用券", {}).get("data", {})
    if coupon_data:
        lines.append("\n用券效果（带券 > 不带券）：")
        for k, v in sorted(coupon_data.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  {k}: {v*100:.2f}%")

    time_data = d.get("时段_小时", {}).get("data", {})
    if time_data:
        lines.append("\n时段CTR（小时粒度，跨渠道加权）：")
        for k, v in sorted(time_data.items(), key=lambda x: int(x[0].replace("时",""))):
            lines.append(f"  {k}: {v*100:.3f}%")

    char_data = d.get("渠道_x_标题字数", {}).get("data", {})
    if char_data:
        # 按渠道聚合，每个渠道只输出 CTR Top 3 区间（参考维度，prompt 已降权）
        lines.append("\n各渠道高CTR标题字数区间（仅参考，降权）：")
        by_ch: dict = {}
        for k, v in char_data.items():
            ch, rng = k.split("_", 1)
            by_ch.setdefault(ch, []).append((rng, v))
        for ch, items in by_ch.items():
            top3 = sorted(items, key=lambda x: -x[1])[:3]
            lines.append(f"  {ch}: " + " | ".join(f"{rng}({v*100:.2f}%)" for rng, v in top3))

    plan_data = d.get("渠道_x_计划类型", {}).get("data", {})
    if plan_data:
        lines.append("\nAARRPlan vs 常规Plan（AARRPlan为算法精准触达）：")
        for k, v in sorted(plan_data.items(), key=lambda x: -x[1]):
            lines.append(f"  {k}: {v*100:.2f}%")

    owner_data = d.get("渠道_x_预算owner", {}).get("data", {})
    if owner_data:
        lines.append("\n渠道×预算Owner（仅列高CTR组合）：")
        for k, v in sorted(owner_data.items(), key=lambda x: -x[1])[:15]:
            lines.append(f"  {k}: {v*100:.2f}%")

    return "\n".join(lines)


# ── LLM call ───────────────────────────────────────────────────────
def call_llm_batch(api_key: str, provider: str, rows: list, model: str, context: str) -> list:
    if not api_key:
        return [{"pred_ctr": None, "confidence": None, "suggestion": "请先填写API Key"}] * len(rows)

    batch_text = []
    for i, row in enumerate(rows, 1):
        title    = str(row.get("标题", ""))
        content  = str(row.get("内容", ""))
        channel  = str(row.get("渠道", "")).strip()
        coupon   = str(row.get("是否用券", "")).strip()
        workday  = str(row.get("工作日类型", "")).strip()
        time_s   = str(row.get("发送时间", "")).strip()
        plan     = str(row.get("计划类型", "")).strip()
        owner    = str(row.get("预算Owner", "")).strip()

        # Build baseline context for this row
        plan_v = plan if plan in ("AARRPlan", "普通Plan") else None
        char_range_v = get_char_range(title) if title else None
        bl_ctr = get_baseline_ctr(channel, coupon or None,
                                  workday or None, plan_v, owner or None,
                                  char_range_v)
        bl_str = f"{bl_ctr*100:.3f}%" if bl_ctr else "未知"
        tm = get_time_multiplier(time_s)

        batch_text.append(
            f"【{i}】标题：{title}｜正文：{content}｜渠道：{channel or '未填'}"
            f"｜用券：{coupon or '未填'}｜工作日：{workday or '未填'}"
            f"｜发送时间：{time_s or '未填'}｜计划类型：{plan or '未填'}"
            f"｜预算Owner：{owner or '未填'}｜基准CTR：{bl_str}｜时段系数：{tm:.2f}"
        )

    prompt = f"""你是一个麦当劳中国Push文案CTR优化专家。

{context}

以下是要预测的文案（共{len(rows)}条）：
{chr(10).join(batch_text)}

请预测每条文案的CTR，并给出具体改进建议。
【重要】标题字数仅供参考，不是主要因素，权重低于渠道、时段和内容质量。
输出格式：严格JSON数组，每条包含：
- "pred_ctr": 预测CTR小数（如0.025=2.5%，需综合基准CTR、时段系数、内容质量判断）
- "confidence": 置信度0-1（信息越充分越接近1）
- "suggestion": 改进建议（30字内，具体到文案本身）

直接返回JSON数组，不要其他文字："""

    # ─── 分协议调用 ───
    # minimax 走 Anthropic 协议，其他 provider 走 OpenAI 协议
    try:
        if provider == "MiniMax":
            try:
                import anthropic
            except ImportError:
                return [{"pred_ctr": None, "confidence": None, "suggestion": "请安装 anthropic: pip install anthropic"}] * len(rows)
            client = anthropic.Anthropic(api_key=api_key, base_url="https://api.minimaxi.com/anthropic", timeout=60)
            resp = client.messages.create(
                model=model,
                max_tokens=4000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            # 过滤 text block（跳过 thinking 块）
            text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            raw = "\n".join(text_parts).strip()
        else:
            if provider == "SiliconFlow":
                base_url = "https://api.siliconflow.cn/v1"
            elif provider == "百度千帆":
                base_url = "https://qianfan.baidubce.com/v2/coding"
            elif provider == "OpenAI":
                base_url = None
            else:
                return [{"pred_ctr": None, "confidence": None, "suggestion": f"不支持: {provider}"}] * len(rows)

            try:
                import openai
            except ImportError:
                return [{"pred_ctr": None, "confidence": None, "suggestion": "请安装 openai: pip install openai"}] * len(rows)

            client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=60) if base_url else openai.OpenAI(api_key=api_key, timeout=60)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
                timeout=60,
            )
            raw = resp.choices[0].message.content.strip()
    except Exception as e:
        return [{"pred_ctr": None, "confidence": None, "suggestion": f"API错误: {str(e)[:50]}"}] * len(rows)

    # JSON 解析（两个协议共用）
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    try:
        results = json.loads(raw)
        if not isinstance(results, list):
            results = [results]
        if len(results) != len(rows):
            results = (results + [{}] * len(rows))[:len(rows)]
        for r in results:
            r.setdefault("pred_ctr", None)
            r.setdefault("confidence", None)
            r.setdefault("suggestion", "解析异常")
        return results
    except json.JSONDecodeError as e:
        return [{"pred_ctr": None, "confidence": None, "suggestion": f"JSON失败: {str(e)[:50]}"}] * len(rows)


# ══════════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="mcd-header">
  <h1>MCD CTR 预测工具</h1>
  <p>上传文案 → LLM批量预测CTR + 改进建议</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**API 配置**")
    with st.expander("API 配置", expanded=True):
        api_key   = st.text_input("API Key", value="sk--4XUFwAM5Sfal4M27lWTK-8nrVPI2cFy3XrkPu0LjP409K4QrSQPg12NdLcs2hrvv0CzvVOIKhRZhHTMXh1UcgLGa4LbXKKEJjPE0UBV2bN6DuMh6YobBTro", type="password")
        provider  = st.selectbox("API Provider", ["MiniMax", "百度千帆", "SiliconFlow", "OpenAI"], index=0, help="推荐MiniMax（国内快，走Anthropic协议）")
        model_map = {
            "MiniMax":     ["MiniMax-M3"],
            "百度千帆":    ["qianfan-code-latest"],
            "SiliconFlow": ["deepseek-ai/DeepSeek-V3-0324", "Qwen/Qwen2.5-72B-Instruct", "anthropic/claude-3.5-sonnet"],
            "OpenAI": ["gpt-4o-mini", "gpt-4o"],
        }
        model      = st.selectbox("模型", model_map[provider])
        batch_size = st.selectbox("每批条数", [5, 10, 15, 20], index=1)

    st.markdown("---")
    # 当前数据基准（v3 起）
    ver = BASELINE.get("version", "?")
    ws = BASELINE.get("data_window_start", "?")
    we = BASELINE.get("data_window_end", "?")
    method = BASELINE.get("weighted_method", "")
    hl = BASELINE.get("calibration_half_life_days", "")
    st.markdown(f"**当前数据基准** v{ver}")
    st.caption(f"窗口：{ws} ~ {we}")
    if method == "exponential_decay" and hl:
        st.caption(f"指数加权 · 半衰期 {hl} 天")

    st.markdown("---")
    st.markdown("**渠道基准 CTR**")
    with st.expander("渠道基准CTR（点击展开）", expanded=False):
        ch_data = BASELINE.get("dimensions", {}).get("渠道", {}).get("data", {})
        for k, v in sorted(ch_data.items(), key=lambda x: -x[1]):
            st.markdown(f"**{k}**: {v*100:.2f}%")

    st.markdown("---")
    st.markdown("**使用说明**")
    st.markdown("""
    1. 上传CSV/Excel
    2. 必填：标题 + 正文
    3. 选填：渠道/用券/工作日/时间/计划类型/Owner（填了更准）
    4. 填API Key → 点预测 → 下载
    """)

# ── File upload ────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "上传CSV或Excel（标题+正文必填，其余选填）",
    type=["csv", "xlsx", "xls"],
)

# ── 数据陈旧提醒（v3 起）──
# 距 data_window_end 超过 90 天，提示运营跑 calibrate_baseline.py 重跑
def _check_baseline_age(baseline, today, threshold_days: int = 90):
    """返回数据距今天数；返回 None 表示 baseline 无 data_window_end 或格式异常"""
    _we_str = baseline.get("data_window_end", "")
    if not _we_str:
        return None
    try:
        from datetime import datetime
        _we = datetime.strptime(_we_str, "%Y-%m-%d").date()
        return (today - _we).days
    except ValueError:
        return None

_age_days = _check_baseline_age(BASELINE, __import__("datetime").date.today())
if _age_days is not None and _age_days > 90:
    st.warning(
        f"基准数据已 {_age_days} 天未更新（最新 {BASELINE.get('data_window_end')}）。"
        f"建议跑 python calibrate_baseline.py 重跑。"
    )

# ── Auto-detect columns ───────────────────────────────────────
KNOWN_TITLE_ALIASES   = ["标题", "文案标题", "title", "标题列", "push_title", "标题title"]
KNOWN_BODY_ALIASES    = ["内容", "正文", "文案", "content", "body", "push_content", "正文内容"]
KNOWN_CHANNEL_ALIASES = ["渠道", "channel", "触点", "push_channel"]
KNOWN_COUPON_ALIASES  = ["是否用券", "用券", "coupon", "是否有券"]
KNOWN_WORKDAY_ALIASES = ["工作日类型", "工作日", "workday", "日期类型"]
KNOWN_TIME_ALIASES    = ["发送时间", "时间", "time", "推送时间", "send_time"]
KNOWN_PLAN_ALIASES    = ["计划类型", "plan_type", "计划type", "AARRPlan"]
KNOWN_OWNER_ALIASES   = ["预算owner", "owner", "预算Owner", "负责人"]

def auto_detect(df, aliases):
    # 严格匹配：列名必须与某个 alias 完全相等（不区分大小写），
    # 避免 "title" 误匹配 "subtitle"/"title_new" 等子串
    for col in df.columns:
        for alias in aliases:
            if alias.lower() == col.lower():
                return col
    return None

def auto_detect_all(df) -> dict:
    return {
        "标题":       auto_detect(df, KNOWN_TITLE_ALIASES),
        "正文":       auto_detect(df, KNOWN_BODY_ALIASES),
        "渠道":       auto_detect(df, KNOWN_CHANNEL_ALIASES),
        "是否用券":   auto_detect(df, KNOWN_COUPON_ALIASES),
        "工作日类型": auto_detect(df, KNOWN_WORKDAY_ALIASES),
        "发送时间":   auto_detect(df, KNOWN_TIME_ALIASES),
        "计划类型":   auto_detect(df, KNOWN_PLAN_ALIASES),
        "预算Owner":  auto_detect(df, KNOWN_OWNER_ALIASES),
    }

if uploaded_file:
    try:
        df_raw = pd.read_excel(uploaded_file) if uploaded_file.name.endswith(("xlsx", "xls")) else pd.read_csv(uploaded_file)
    except ImportError:
        st.error("❌ 读取Excel失败，请在本地安装 openpyxl 后重新上传，或改用CSV格式。")
        st.stop()
    except Exception as e:
        st.error(f"❌ 读取文件失败：{str(e)}")
        st.stop()

    st.markdown(f"**{uploaded_file.name}** — {len(df_raw)}行 × {len(df_raw.columns)}列")

    # ── Auto-detect ────────────────────────────────────────────
    detected = auto_detect_all(df_raw)
    detected_any = any(v for v in detected.values())
    col_opts = list(df_raw.columns)

    if detected_any:
        detected_label = [k for k, v in detected.items() if v]
        st.success(
            f"✅ 自动识别到 {len(detected_label)} 个字段：" + " | ".join(
                f"{k}={v}" for k, v in detected.items() if v
            )
        )
        if detected["标题"]:
            st.caption("如需手动调整列映射，请展开下方「手动映射」")
    else:
        st.warning("⚠️ 未识别到必填列（标题/正文），请手动指定列映射")

    with st.expander("手动映射（可覆盖自动识别）"):
        col_title   = st.selectbox("标题列", col_opts, index=col_opts.index(detected["标题"]) if detected["标题"] in col_opts else 0)
        col_content = st.selectbox("正文列", col_opts, index=col_opts.index(detected["正文"]) if detected["正文"] in col_opts else min(1, len(col_opts)-1))
        col_channel = st.selectbox("渠道", ["（不填）"] + col_opts, index=(col_opts.index(detected["渠道"]) + 1) if detected["渠道"] in col_opts else 0)
        col_coupon  = st.selectbox("是否用券", ["（不填）"] + col_opts, index=(col_opts.index(detected["是否用券"]) + 1) if detected["是否用券"] in col_opts else 0)
        col_workday = st.selectbox("工作日类型", ["（不填）"] + col_opts, index=(col_opts.index(detected["工作日类型"]) + 1) if detected["工作日类型"] in col_opts else 0)
        col_time    = st.selectbox("发送时间", ["（不填）"] + col_opts, index=(col_opts.index(detected["发送时间"]) + 1) if detected["发送时间"] in col_opts else 0)
        col_plan    = st.selectbox("计划类型", ["（不填）"] + col_opts, index=(col_opts.index(detected["计划类型"]) + 1) if detected["计划类型"] in col_opts else 0)
        col_owner   = st.selectbox("预算Owner", ["（不填）"] + col_opts, index=(col_opts.index(detected["预算Owner"]) + 1) if detected["预算Owner"] in col_opts else 0)

    # ── Prepare working df ─────────────────────────────────────
    df_w = df_raw.copy()
    df_w["标题"]       = df_w[col_title].astype(str)
    df_w["内容"]       = df_w[col_content].astype(str)
    df_w["渠道"]       = df_w[col_channel].astype(str) if col_channel  != "（不填）" else ""
    df_w["是否用券"]   = df_w[col_coupon].astype(str)  if col_coupon   != "（不填）" else ""
    df_w["发送时间"]   = df_w[col_time].astype(str)    if col_time     != "（不填）" else ""
    df_w["计划类型"]   = df_w[col_plan].astype(str)    if col_plan     != "（不填）" else ""
    df_w["预算Owner"]  = df_w[col_owner].astype(str)   if col_owner    != "（不填）" else ""

    # 工作日类型：用户填了用用户的；没填但有发送时间（含日期），从日期派生
    if col_workday != "（不填）":
        df_w["工作日类型"] = df_w[col_workday].astype(str)
    elif col_time != "（不填）":
        df_w["工作日类型"] = df_w["发送时间"].apply(_derive_workday_from_time)
    else:
        df_w["工作日类型"] = ""

    # 基于用户最终选中的 col_title 列的实际数据判断（而非自动识别结果）
    title_valid = df_w["标题"].str.strip().str.lower().replace("nan", "").ne("").any()
    missing_title = not title_valid
    st.dataframe(df_w[["标题","渠道","是否用券","工作日类型","发送时间","计划类型","预算Owner"]].head(3), use_container_width=True)

    if st.button("开始预测", type="primary", disabled=(not api_key or missing_title)):
        if not api_key:
            st.error("请先填API Key")
        elif missing_title:
            st.error("标题列为空，请检查列映射是否正确")
        else:
            total = len(df_w)
            pb = st.progress(0)
            status = st.empty()
            results = []
            context_str = build_context_for_llm(BASELINE)

            for start in range(0, total, batch_size):
                end = min(start + batch_size, total)
                batch = df_w.iloc[start:end].to_dict("records")
                batch_results = call_llm_batch(api_key, provider, batch, model, context_str)
                results.extend(batch_results)
                if len(batch_results) != len(batch):
                    st.warning(f"⚠️ 第 {start//batch_size+1} 批返回 {len(batch_results)} 条（应有 {len(batch)} 条），缺失项已用空值填充")
                pb.progress(end / total)
                if end < total:
                    time.sleep(1.2)

            status.text("完成！")
            pb.empty()

            # ── Build output columns ─────────────────────────────
            df_w["预测CTR"]    = [r.get("pred_ctr") for r in results]
            df_w["置信度"]     = [r.get("confidence") for r in results]
            df_w["改进建议"]   = [r.get("suggestion") for r in results]
            df_w["标题字数"]   = df_w["标题"].apply(count_chars)
            df_w["字数建议"]   = df_w.apply(
                lambda r: suggest_char_range(r["渠道"], r["标题"]) if r["渠道"] else "", axis=1
            )
            df_w["时段建议"]   = df_w.apply(
                lambda r: get_time_suggestion(r["发送时间"], r["渠道"]) if (r["发送时间"] and r["渠道"]) else "", axis=1
            )

            # 渠道基准（自动匹配最合适的维度组合）
            # 兜底值：用 baseline 里所有渠道 CTR 的均值；若 baseline 也为空则 0.002
            ch_data_avg = (sum(BASELINE.get("dimensions", {}).get("渠道", {}).get("data", {}).values())
                           / max(len(BASELINE.get("dimensions", {}).get("渠道", {}).get("data", {})), 1)
                           if BASELINE.get("dimensions", {}).get("渠道", {}).get("data", {}) else 0.002)

            def get_disp_bl(row):
                ch = row["渠道"].strip()
                coupon = "是" if "是" in row["是否用券"] else ("否" if "否" in row["是否用券"] else None)
                workday = row["工作日类型"].strip() if row["工作日类型"].strip() in ("工作日","非工作日") else None
                plan    = row["计划类型"].strip() if row["计划类型"].strip() in ("AARRPlan","普通Plan") else None
                owner   = row["预算Owner"].strip() or None
                tm      = get_time_multiplier(row["发送时间"])
                char_range_v = get_char_range(row["标题"]) if row["标题"] else None
                v       = get_baseline_ctr(ch, coupon, workday, plan, owner, char_range_v)
                base    = v if v else ch_data_avg
                return f"{base*100:.3f}%（时段×{tm:.2f}）"

            df_w["渠道基准"] = df_w.apply(get_disp_bl, axis=1)

            # Summary metrics
            valid = df_w["预测CTR"].dropna()
            if len(valid):
                st.markdown('<div class="section-title">预测结果概览</div>', unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("预测条数", f"{len(valid)} 条")
                c2.metric("平均预测CTR", f"{valid.mean()*100:.3f}%")
                c3.metric("最高CTR", f"{valid.max()*100:.3f}%")
                c4.metric("最低CTR", f"{valid.min()*100:.3f}%")

            # Display table
            st.markdown('<div class="section-title">预测详情</div>', unsafe_allow_html=True)
            disp_cols = ["标题","渠道","标题字数","渠道基准","预测CTR","置信度","改进建议","字数建议","时段建议"]
            rename_cols = {"标题":"标题","渠道":"渠道","标题字数":"字数","渠道基准":"基准CTR",
                           "预测CTR":"预测CTR","置信度":"置信度","改进建议":"改进建议",
                           "字数建议":"字数建议","时段建议":"时段建议"}
            # Format CTR column for display
            df_disp = df_w[disp_cols].rename(columns=rename_cols).copy()
            df_disp["预测CTR"] = df_disp["预测CTR"].apply(
                lambda x: f"{x*100:.3f}%" if pd.notna(x) else ""
            )
            st.dataframe(df_disp, use_container_width=True, height=400, hide_index=True)

            # Download
            out_cols = ["标题","内容","渠道","是否用券","工作日类型","发送时间","计划类型","预算Owner",
                        "标题字数","渠道基准","预测CTR","置信度","改进建议","字数建议","时段建议"]
            csv_out = df_w[out_cols].to_csv(index=False, encoding="utf-8-sig")
            st.download_button("下载预测结果 CSV", csv_out, "ctr_prediction_result.csv", "text/csv", use_container_width=True)

else:
    st.markdown('<div class="section-title">文件格式示例</div>', unsafe_allow_html=True)
    st.markdown(
        "<span style='font-size:13px; color:#888;'>必填：文案标题 / 正文&nbsp;&nbsp;|&nbsp;&nbsp;"
        "选填：渠道、是否用券、工作日类型、发送时间、计划类型、预算Owner&nbsp;&nbsp;|&nbsp;&nbsp;"
        "标题字数自动计算</span>",
        unsafe_allow_html=True,
    )
    st.dataframe(pd.DataFrame({
        "文案标题":  [
            "仅剩3天！0元领麦当劳薯条",
            "会员专享满40减15，点击领取",
            "【紧急通知】您的优惠券即将过期",
            "早餐限时5折，错过等一周",
            "亲爱的用户，您的积分可以兑咖啡了",
            "麦咖啡新品上市，买一送一，限时3天",
            "恭喜获得新品试吃名额，戳我领取",
        ],
        "正文": [
            "新用户专享，下载App即送薯条优惠券",
            "仅限今日，门店和外卖同步参与",
            "您的20元优惠券还剩48小时，失效不补",
            "早上6点开卖，售完即止，支持到店自取",
            "您有328积分可兑换中杯美式，7天后过期",
            "大杯拿铁+麦芬组合价19.9元，限工作日",
            "邀请好友各得免费甜筒，下载App领取",
        ],
        "渠道": [
            "APP Push",
            "企微1v1",
            "微信小程序订阅消息",
            "短信",
            "企微1v1",
            "微信订阅",
            "APP Push",
        ],
        "是否用券": [
            "是",
            "是",
            "是",
            "否",
            "是",
            "否",
            "否",
        ],
        "工作日类型": [
            "工作日",
            "非工作日",
            "工作日",
            "工作日",
            "工作日",
            "非工作日",
            "工作日",
        ],
        "发送时间": [
            "10:30",
            "17:50",
            "14:00",
            "07:30",
            "11:00",
            "08:00",
            "15:20",
        ],
        "计划类型": [
            "AARRPlan",
            "AARRPlan",
            "普通Plan",
            "普通Plan",
            "普通Plan",
            "普通Plan",
            "普通Plan",
        ],
        "预算Owner": [
            "MKT",
            "Reach",
            "Membership",
            "BF",
            "McCafe",
            "MDS",
            "Chicken",
        ],
    }), use_container_width=True, hide_index=True)