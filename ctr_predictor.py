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

# ── Page Config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="MCD CTR 预测工具",
    page_icon="",
    layout="wide",
)

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
    m = re.search(r"\b(\d{1,2})\b", str(time_str))
    if not m:
        return 1.0
    hour = int(m.group(1))
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
        lines.append("\n各渠道最优标题字数：")
        for ch, sug in OPTIMAL_CHARS.items():
            lines.append(f"  {ch}: {sug}")

    plan_data = d.get("渠道_x_计划类型", {}).get("data", {})
    if plan_data:
        lines.append("\nAARRPlan vs 普通Plan（AARRPlan为算法精准触达）：")
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

    client = openai.OpenAI(api_key=api_key, base_url=base_url) if base_url else openai.OpenAI(api_key=api_key)

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
        bl_ctr = get_baseline_ctr(channel, coupon or None,
                                  workday or None, plan_v, owner or None)
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
输出格式：严格JSON数组，每条包含：
- "pred_ctr": 预测CTR小数（如0.025=2.5%，需综合基准CTR、时段系数、内容质量判断）
- "confidence": 置信度0-1（信息越充分越接近1）
- "suggestion": 改进建议（30字内，具体到文案本身）

直接返回JSON数组，不要其他文字："""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
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
    except Exception as e:
        return [{"pred_ctr": None, "confidence": None, "suggestion": f"API错误: {str(e)[:50]}"}] * len(rows)


# ══════════════════════════════════════════════════════════════════
#  UI
# ══════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background:#DA291C;padding:16px 20px;border-radius:12px;margin-bottom:20px">
    <div style="color:white;font-size:20px;font-weight:bold;">MCD CTR 预测工具</div>
    <div style="color:#FFC72C;font-size:13px;margin-top:4px;">上传文案 → LLM批量预测CTR + 改进建议</div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 配置")
    api_key   = st.text_input("API Key（自己填）", type="password")
    provider  = st.selectbox("API Provider", ["SiliconFlow", "百度千帆", "OpenAI"], help="推荐SiliconFlow或百度千帆（国内快）")
    model_map = {
        "SiliconFlow": ["deepseek-ai/DeepSeek-V3-0324", "Qwen/Qwen2.5-72B-Instruct", "anthropic/claude-3.5-sonnet"],
        "百度千帆":    ["qianfan-code-latest"],
        "OpenAI": ["gpt-4o-mini", "gpt-4o"],
    }
    model      = st.selectbox("模型", model_map[provider])
    batch_size = st.selectbox("每批条数", [5, 10, 15, 20], index=1)

    st.markdown("---")
    st.markdown("### 渠道基准CTR")
    ch_data = BASELINE.get("dimensions", {}).get("渠道", {}).get("data", {})
    for k, v in sorted(ch_data.items(), key=lambda x: -x[1]):
        st.markdown(f"**{k}**: {v*100:.2f}%")

    st.markdown("---")
    st.markdown("### 时段CTR（小时）")
    td = BASELINE.get("dimensions", {}).get("时段_小时", {}).get("data", {})
    if td:
        max_ctr = max(td.values())
        for h, ctr in sorted(td.items(), key=lambda x: int(x[0].replace("时",""))):
            bar_w = int(ctr / max_ctr * 28)
            st.markdown(f"{h} `{ctr*100:.3f}%` {'█'*bar_w}")
    else:
        st.info("未找到时段数据")

    st.markdown("---")
    st.markdown("### 使用说明")
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

if uploaded_file:
    df_raw = pd.read_excel(uploaded_file) if uploaded_file.name.endswith(("xlsx", "xls")) else pd.read_csv(uploaded_file)
    st.markdown(f"**{uploaded_file.name}** — {len(df_raw)}行 × {len(df_raw.columns)}列")

    col_opts = list(df_raw.columns)
    col_title   = st.selectbox("标题列", col_opts, index=0)
    col_content = st.selectbox("正文列", col_opts, index=min(1, len(col_opts) - 1))

    with st.expander("可选列映射（不填则留空）"):
        col_channel = st.selectbox("渠道", ["（不填）"] + col_opts)
        col_coupon  = st.selectbox("是否用券", ["（不填）"] + col_opts)
        col_workday = st.selectbox("工作日类型", ["（不填）"] + col_opts)
        col_time    = st.selectbox("发送时间", ["（不填）"] + col_opts)
        col_plan    = st.selectbox("计划类型（AARRPlan/普通Plan）", ["（不填）"] + col_opts)
        col_owner   = st.selectbox("预算Owner", ["（不填）"] + col_opts)

    # Prepare working df
    df_w = df_raw.copy()
    df_w["标题"]       = df_w[col_title].astype(str)
    df_w["内容"]       = df_w[col_content].astype(str)
    df_w["渠道"]       = df_w[col_channel].astype(str) if col_channel  != "（不填）" else ""
    df_w["是否用券"]   = df_w[col_coupon].astype(str)  if col_coupon   != "（不填）" else ""
    df_w["工作日类型"] = df_w[col_workday].astype(str) if col_workday != "（不填）" else ""
    df_w["发送时间"]   = df_w[col_time].astype(str)    if col_time     != "（不填）" else ""
    df_w["计划类型"]   = df_w[col_plan].astype(str)    if col_plan     != "（不填）" else ""
    df_w["预算Owner"]  = df_w[col_owner].astype(str)   if col_owner    != "（不填）" else ""

    st.dataframe(df_w[["标题","渠道","是否用券","工作日类型","发送时间","计划类型","预算Owner"]].head(3), use_container_width=True)

    if st.button("开始预测CTR", type="primary", disabled=not api_key):
        if not api_key:
            st.error("请先填API Key")
        else:
            total = len(df_w)
            pb = st.progress(0)
            status = st.empty()
            results = []
            context_str = build_context_for_llm(BASELINE)

            for start in range(0, total, batch_size):
                end = min(start + batch_size, total)
                batch = df_w.iloc[start:end].to_dict("records")
                status.text(f"处理第{start+1}-{end}条，共{total}条...")
                results.extend(call_llm_batch(api_key, provider, batch, model, context_str))
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
            def get_disp_bl(row):
                ch = row["渠道"].strip()
                coupon = "是" if "是" in row["是否用券"] else ("否" if "否" in row["是否用券"] else None)
                workday = row["工作日类型"].strip() if row["工作日类型"].strip() in ("工作日","非工作日") else None
                plan    = row["计划类型"].strip() if row["计划类型"].strip() in ("AARRPlan","普通Plan") else None
                owner   = row["预算Owner"].strip() or None
                tm      = get_time_multiplier(row["发送时间"])
                v       = get_baseline_ctr(ch, coupon, workday, plan, owner)
                base    = v if v else 0.002
                return f"{base*100:.3f}%（时段×{tm:.2f}）"

            df_w["渠道基准"] = df_w.apply(get_disp_bl, axis=1)

            # Summary metrics
            valid = df_w["预测CTR"].dropna()
            if len(valid):
                c1, c2, c3 = st.columns(3)
                c1.metric("平均预测CTR", f"{valid.mean()*100:.3f}%")
                c2.metric("最高CTR",     f"{valid.max()*100:.3f}%")
                c3.metric("最低CTR",     f"{valid.min()*100:.3f}%")

            # Display table
            disp_cols = ["标题","渠道","标题字数","渠道基准","预测CTR","置信度","改进建议","字数建议","时段建议"]
            rename_cols = {"标题":"标题","渠道":"渠道","标题字数":"字数","渠道基准":"基准CTR",
                           "预测CTR":"预测CTR","置信度":"置信度","改进建议":"改进建议",
                           "字数建议":"字数建议","时段建议":"时段建议"}
            st.dataframe(df_w[disp_cols].rename(columns=rename_cols), use_container_width=True, height=400)

            # Download
            out_cols = ["标题","内容","渠道","是否用券","工作日类型","发送时间","计划类型","预算Owner",
                        "标题字数","渠道基准","预测CTR","置信度","改进建议","字数建议","时段建议"]
            csv_out = df_w[out_cols].to_csv(index=False, encoding="utf-8-sig")
            st.download_button("下载结果CSV", csv_out, "ctr_prediction_result.csv", "text/csv")

else:
    st.markdown("### 期待文件格式示例（仅需填以下列，标题字数自动计算）")
    st.dataframe(pd.DataFrame({
        "文案标题":  ["仅剩3天！免费领麦当劳薯条", "亲爱的会员，专属优惠等你"],
        "正文":      ["戳我立即领取，新用户必享", "成为会员，享受专属折扣"],
        "渠道":      ["APP Push",    "企微1v1"],
        "是否用券":  ["是",          "否"],
        "工作日类型": ["工作日",      "非工作日"],
        "发送时间":  ["10:30",       "17:50"],
        "计划类型":  ["AARRPlan",    "普通Plan"],
        "预算Owner": ["MKT",         "Reach"],
    }), use_container_width=True)
    st.caption("标题 + 正文必填；其余列选填（填了预测更准）")
    st.caption("标题字数自动计算，无需在Excel里预填")