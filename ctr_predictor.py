"""
MCD CTR 预测工具 — Streamlit App
功能：上传文案列表 → LLM批量预测CTR + 改进建议
依赖：pip install streamlit pandas openai python-dateutil
运行：streamlit run ctr_predictor.py
"""

import streamlit as st
import pandas as pd
import json
import re
import time
import os
from datetime import datetime, date
from io import StringIO, BytesIO

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
CHANNEL_DISPLAY = {
    "APP Push": "APP Push",
    "企微1v1": "企微1v1",
    "微信公众号推文": "微信公众号推文",
    "微信小程序订阅消息": "微信小程序订阅消息",
    "微信订阅": "微信订阅",
    "短信": "短信",
}
CHANNEL_KEYS = list(CHANNEL_DISPLAY.values())

OPTIMAL_CHARS = {
    "APP Push": "5-12字",
    "企微1v1": "13-18字",
    "微信公众号推文": "15-20字",
    "微信小程序订阅消息": "5-10字",
    "微信订阅": "7-14字",
    "短信": "9-12字",
}

# ── Title Analysis Helpers ─────────────────────────────────────────
def count_chars(text: str) -> int:
    return len(str(text).strip())

def suggest_char_range(channel: str, title: str) -> str:
    n = count_chars(title)
    optimal = OPTIMAL_CHARS.get(channel, "未知")
    lo, hi = optimal.split("-")
    lo_n, hi_n = int(lo.replace("字", "")), int(hi.replace("字", ""))
    if lo_n <= n <= hi_n:
        return f"字数{n}字，在{optimal}最优区间内"
    elif n < lo_n:
        return f"字数{n}字，偏短，建议增加到{optimal}（当前短{lo_n - n}字）"
    else:
        return f"字数{n}字，偏长，建议精简到{optimal}（当前长{n - hi_n}字）"

def get_baseline_ctr(channel: str, coupon: str = None, workday: str = None, char_range: str = None) -> float:
    ch = channel.strip()
    d = BASELINE.get("dimensions", {})

    # 渠道 × 字数
    if char_range and ch in d.get("渠道_x_标题字数", {}).get("data", {}):
        key = f"{ch}_{char_range}"
        v = d["渠道_x_标题字数"]["data"].get(key)
        if v:
            return v

    # 渠道 × 用券
    if coupon in ("是", "否") and ch in d.get("渠道_x_是否用券", {}).get("data", {}):
        key = f"{ch}_{coupon}"
        v = d["渠道_x_是否用券"]["data"].get(key)
        if v:
            return v

    # 渠道 × 工作日类型
    if workday in ("工作日", "非工作日") and ch in d.get("渠道_x_工作日类型", {}).get("data", {}):
        key = f"{ch}_{workday}"
        v = d["渠道_x_工作日类型"]["data"].get(key)
        if v:
            return v

    # 渠道基准
    return d.get("渠道", {}).get("data", {}).get(ch, None)

def build_context_for_llm(baseline: dict) -> str:
    """Build a compact context string for the LLM prompt."""
    d = baseline.get("dimensions", {})
    lines = ["【麦当劳Push CTR基准参考】", "(数值为小数，0.0355 = 3.55%)"]
    ch_data = d.get("渠道", {}).get("data", {})
    if ch_data:
        lines.append("\n各渠道CTR基准：")
        for k, v in ch_data.items():
            lines.append(f"  {k}: {v*100:.2f}%")
    coupon_data = d.get("渠道_x_是否用券", {}).get("data", {})
    if coupon_data:
        lines.append("\n用券提升效果（带券CTR > 不带券CTR）：")
        for k, v in coupon_data.items():
            lines.append(f"  {k}: {v*100:.2f}%")
    return "\n".join(lines)

# ── LLM Call ───────────────────────────────────────────────────────
def call_llm_batch(api_key: str, provider: str, rows: list, model: str, context: str) -> list:
    """Call LLM for a batch of rows, return list of {'pred_ctr': float, 'suggestion': str}"""
    if not api_key:
        return [{"pred_ctr": None, "suggestion": "请先填写API Key"}] * len(rows)

    import openai
    openai.api_key = api_key

    # Build the prompt
    batch_text = []
    for i, row in enumerate(rows, 1):
        title = str(row.get("标题", row.get("文案标题", "")))
        content = str(row.get("内容", row.get("文案", "")))
        channel = str(row.get("渠道", ""))
        coupon = str(row.get("是否用券", ""))
        workday = str(row.get("工作日类型", ""))
        baseline_ctr = get_baseline_ctr(channel, coupon, workday)
        baseline_str = f"{baseline_ctr*100:.2f}%" if baseline_ctr else "未知"
        batch_text.append(
            f"【{i}】\n标题：{title}\n正文：{content}\n渠道：{channel or '未填'}\n是否用券：{coupon or '未填'}\n工作日类型：{workday or '未填'}\n该渠道基准CTR：{baseline_str}"
        )

    prompt = f"""你是一个专业的麦当劳中国Push文案效果优化专家。

{context}

以下是要预测的文案（每条包含标题+正文+渠道+用券情况）：

{chr(10).join(batch_text)}

请对每条文案预测CTR并给出改进建议。CTR预测需结合渠道基准、内容质量（利益点、紧迫感、标题吸引力）、用券效果等因素。
输出格式要求：严格JSON数组格式，每条对应一个对象，包含字段：
- "pred_ctr": 预测CTR（小数，如0.025表示2.5%），需结合基准CTR和内容质量综合判断
- "confidence": 预测置信度（0-1之间，取决于你掌握的信息充分程度）
- "suggestion": 改进建议（50字以内，中文，具体到文案本身）

JSON数组（直接返回，不要有其他文字）："""

    try:
        if provider == "OpenAI":
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            raw = resp.choices[0].message.content.strip()
        elif provider == "SiliconFlow":
            client = openai.OpenAI(api_key=api_key, base_url="https://api.siliconflow.cn/v1")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            raw = resp.choices[0].message.content.strip()
        else:
            return [{"pred_ctr": None, "suggestion": f"不支持的Provider: {provider}"}] * len(rows)

        # Parse JSON
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        results = json.loads(raw)
        if len(results) != len(rows):
            results = (results + [{"pred_ctr": None, "suggestion": "解析数量不匹配"}] * len(rows))[:len(rows)]
        return results
    except json.JSONDecodeError as e:
        return [{"pred_ctr": None, "suggestion": f"JSON解析失败: {str(e)[:30]}"}] * len(rows)
    except Exception as e:
        return [{"pred_ctr": None, "suggestion": f"API错误: {str(e)[:50]}"}] * len(rows)

# ── Streamlit UI ──────────────────────────────────────────────────
# Header
st.markdown("""
<div style="background:#DA291C;padding:16px 20px;border-radius:12px;margin-bottom:20px">
    <div style="color:white;font-size:20px;font-weight:bold;">MCD CTR 预测工具</div>
    <div style="color:#FFC72C;font-size:13px;margin-top:4px;">上传文案 → LLM批量预测CTR + 改进建议</div>
</div>
""", unsafe_allow_html=True)

# Sidebar config
with st.sidebar:
    st.markdown("### 配置")
    api_key = st.text_input("API Key", type="password", help="OpenAI或SiliconFlow密钥")
    provider = st.selectbox("Provider", ["SiliconFlow", "OpenAI"], help="推荐SiliconFlow（国内访问快）")
    model_options = {
        "SiliconFlow": ["deepseek-ai/DeepSeek-V3-0324", "Qwen/Qwen2.5-72B-Instruct", "anthropic/claude-3.5-sonnet"],
        "OpenAI": ["gpt-4o-mini", "gpt-4o"],
    }
    model = st.selectbox("模型", model_options[provider])

    st.markdown("---")
    st.markdown("### 批次设置")
    batch_size = st.selectbox("每批处理条数", [5, 10, 15, 20], index=1)

    st.markdown("---")
    st.markdown("### 基准CTR（参考）")
    if BASELINE.get("dimensions", {}).get("渠道"):
        for ch, ctr in BASELINE["dimensions"]["渠道"]["data"].items():
            st.markdown(f"**{ch}**: {ctr*100:.2f}%")
    else:
        st.info("未找到 ctr_baseline.json，请确保文件在工作目录下")

    st.markdown("---")
    st.markdown("### 使用说明")
    st.markdown("""
    1. 上传CSV/Excel（标题+正文列必填）
    2. 可选：渠道/是否用券/工作日类型
    3. 填API Key（自己提供）
    4. 点击预测，等待完成
    5. 下载结果CSV
    """)

# Main area
uploaded_file = st.file_uploader(
    "上传CSV或Excel文件",
    type=["csv", "xlsx", "xls"],
    help="文件需包含：标题列（文案标题/标题）、正文列（文案/内容）\n可选：渠道、是否用券、工作日类型"
)

if uploaded_file:
    # Read file
    if uploaded_file.name.endswith(".xlsx") or uploaded_file.name.endswith(".xls"):
        df_raw = pd.read_excel(uploaded_file)
    else:
        df_raw = pd.read_csv(uploaded_file)

    st.markdown(f"**已上传：** {uploaded_file.name} | {len(df_raw)} 行 × {len(df_raw.columns)} 列")

    # Column mapping
    col_options = list(df_raw.columns)
    col_title = st.selectbox("标题列", col_options,
        index=col_options.index(col_options[0]) if "标题" in col_options[0] else 0)
    col_content = st.selectbox("正文列", col_options,
        index=col_options.index(col_options[0]) if "内容" in col_options[0] else 0)

    # Optional columns
    with st.expander("可选列映射（不填则留空）"):
        col_channel = st.selectbox("渠道列", ["（不填）"] + col_options)
        col_coupon = st.selectbox("是否用券列", ["（不填）"] + col_options)
        col_workday = st.selectbox("工作日类型列", ["（不填）"] + col_options)

    def get_val(row, col):
        if col == "（不填）" or col not in row:
            return ""
        return str(row[col])

    # Build working dataframe
    df_work = df_raw.copy()
    df_work["标题"] = df_work[col_title].astype(str)
    df_work["内容"] = df_work[col_content].astype(str)
    df_work["渠道"] = df_work[col_channel].astype(str) if col_channel != "（不填）" else ""
    df_work["是否用券"] = df_work[col_coupon].astype(str) if col_coupon != "（不填）" else ""
    df_work["工作日类型"] = df_work[col_workday].astype(str) if col_workday != "（不填）" else ""

    # Show first few rows
    st.markdown("**前5行预览：**")
    st.dataframe(df_work[["标题", "渠道", "是否用券", "工作日类型"]].head(), use_container_width=True)

    # Predict button
    if st.button("开始预测CTR", type="primary", disabled=not api_key):
        if not api_key:
            st.error("请先在侧边栏填写API Key")
        else:
            total = len(df_work)
            progress_bar = st.progress(0)
            status_text = st.empty()

            results = []
            context_str = build_context_for_llm(BASELINE)

            # Process in batches
            for start in range(0, total, batch_size):
                end = min(start + batch_size, total)
                batch = df_work.iloc[start:end].to_dict("records")
                status_text.text(f"正在处理第 {start+1}-{end} 条，共 {total} 条...")
                batch_results = call_llm_batch(api_key, provider, batch, model, context_str)
                results.extend(batch_results)
                progress_bar.progress(end / total)
                # Rate limit protection
                if end < total:
                    time.sleep(1)

            status_text.text("处理完成！")
            progress_bar.empty()

            # Merge results
            df_work["预测CTR"] = [r.get("pred_ctr") for r in results]
            df_work["置信度"] = [r.get("confidence") for r in results]
            df_work["改进建议"] = [r.get("suggestion") for r in results]

            # Add char count + baseline comparison
            df_work["标题字数"] = df_work["标题"].apply(count_chars)
            df_work["字数建议"] = df_work.apply(
                lambda r: suggest_char_range(r["渠道"], r["标题"]) if r["渠道"] else "", axis=1
            )

            # Baseline CTR
            def get_bl_ctr(row):
                ch = row["渠道"].strip()
                coupon = "是" if "是" in row["是否用券"] else ("否" if "否" in row["是否用券"] else None)
                workday = row["工作日类型"].strip()
                workday = workday if workday in ("工作日", "非工作日") else None
                v = get_baseline_ctr(ch, coupon, workday)
                return f"{v*100:.2f}%" if v else "—"

            df_work["渠道基准CTR"] = df_work.apply(get_bl_ctr, axis=1)

            # Summary
            valid_preds = df_work["预测CTR"].dropna()
            if len(valid_preds) > 0:
                st.markdown("### 预测结果摘要")
                col1, col2, col3 = st.columns(3)
                col1.metric("平均预测CTR", f"{valid_preds.mean()*100:.3f}%")
                col2.metric("最高CTR", f"{valid_preds.max()*100:.3f}%")
                col3.metric("最低CTR", f"{valid_preds.min()*100:.3f}%")

            st.markdown("### 预测结果")
            display_cols = ["标题", "渠道", "是否用券", "标题字数", "渠道基准CTR", "预测CTR", "置信度", "改进建议"]
            st.dataframe(
                df_work[display_cols].rename(columns={
                    "标题": "标题", "渠道": "渠道", "是否用券": "是否用券",
                    "标题字数": "字数", "渠道基准CTR": "基准CTR", "预测CTR": "预测CTR",
                    "置信度": "置信度", "改进建议": "改进建议"
                }),
                use_container_width=True, height=400
            )

            # Download
            out_df = df_work[["标题", "内容", "渠道", "是否用券", "工作日类型",
                               "标题字数", "渠道基准CTR", "预测CTR", "置信度", "改进建议", "字数建议"]]
            csv_out = out_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                "下载结果CSV",
                csv_out,
                file_name="ctr_prediction_result.csv",
                mime="text/csv",
            )

            # Store in session state
            st.session_state["result_df"] = out_df

else:
    # Show sample format
    st.markdown("### 期待文件格式")
    sample = pd.DataFrame({
        "文案标题": ["仅剩3天！免费领麦当劳薯条", "亲爱的会员，专属优惠等你来"],
        "文案": ["戳我免费领...", "成为会员，享受..."],
        "渠道": ["APP Push", "企微1v1"],
        "是否用券": ["是", "否"],
        "工作日类型": ["工作日", "非工作日"],
    })
    st.dataframe(sample, use_container_width=True)
    st.caption("标题+正文必填，渠道/用券/工作日类型可选（填了预测更准）")