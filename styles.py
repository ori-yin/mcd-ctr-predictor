"""
styles.py - MCD CTR 预测工具：CSS 样式
参考 mcd-content-rank 设计风格
"""

# ─── 品牌色 ─────────────────────────────────────────────────────
MCD_RED = "#DA291C"
MCD_GOLD = "#FFC000"
MCD_GREEN = "#00A04A"
MCD_BG = "#FAFAFA"


def get_css() -> str:
    return f"""
<style>
  /* ─── 全局字体 ─── */
    html, body, .stApp {{
    font-family: 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif !important;
    background: {MCD_BG};
    color: #1a1a1a;
  }}

  /* ─── Streamlit 顶部导航条 ─── */
  .st-emotion-cache-1kyxreq {{
    background: #FFFFFF !important;
  }}

  /* ─── 侧边栏：白底 + 金色顶边（参考 mcd-content-rank）── */
  [data-testid="stSidebar"] {{
    background: #FFFFFF !important;
    border-right: 1px solid #E8E8E8;
    border-top: 3px solid {MCD_GOLD};
  }}

  /* ─── 侧边栏文件上传区 ─── */
  [data-testid="stSidebar"] [data-testid="stFileUploader"] > div > div {{
    border: 1px solid #E0E0E0 !important;
    border-radius: 8px !important;
    padding: 6px 10px !important;
    background: #FFFFFF !important;
  }}

  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] p {{
    color: #000000 !important;
    font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif !important;
  }}

  /* ─── 侧边栏：标签样式 ─── */
  [data-testid="stSidebar"] .stRadio label,
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stTextInput label,
  [data-testid="stSidebar"] .stDateInput label,
  [data-testid="stSidebar"] .stSlider label {{
    color: #000000 !important;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.04em;
    margin-bottom: 4px;
  }}

  [data-testid="stSidebar"] hr {{
    border-color: #EFEFEF !important;
    margin: 12px 0;
  }}

  [data-testid="stSidebar"] .stSelectbox > div > div,
  [data-testid="stSidebar"] .stTextInput > div > div,
  [data-testid="stSidebar"] .stDateInput > div > div {{
    background: #FFFFFF !important;
    border: 1px solid #E0E0E0 !important;
    border-radius: 10px !important;
    color: #000000 !important;
  }}

  [data-testid="stSidebar"] [data-baseweb="select"] span {{
    color: #000000 !important;
  }}

  [data-testid="stSidebar"] [data-baseweb="input"] {{
    color: #000000 !important;
  }}

  [data-testid="stSidebar"] .stDownloadButton > button {{
    background: {MCD_RED} !important;
    color: #FFFFFF !important;
    font-weight: 700;
    border: none !important;
    border-radius: 10px !important;
  }}

  /* ─── 页面布局 ─── */
  .block-container {{
    padding-top: 1.5rem;
    padding-left: 2rem;
    padding-right: 2rem;
    background: {MCD_BG};
  }}

  /* ─── 顶部指标卡（弱化）─── */
  div[data-testid="stMetricValue"] {{
    font-size: 14px !important;
    font-weight: 300 !important;
    color: #999 !important;
    font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif !important;
    letter-spacing: 0;
  }}
  div[data-testid="stMetricLabel"] {{
    font-size: 10px !important;
    color: #BBB !important;
    font-weight: 300;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }}
  div[data-testid="stMetricDelta"] {{
    display: none;
  }}

  /* ─── Tab 栏 ─── */
  .stTabs [data-baseweb="tab-list"] {{
    gap: 4px;
    border-bottom: 2px solid #EFEFEF;
  }}
  .stTabs [data-baseweb="tab"] {{
    color: #888 !important;
    font-weight: 600;
    font-size: 14px;
    padding: 8px 16px;
    border-radius: 8px 8px 0 0;
    border-bottom: 3px solid transparent;
    transition: all 0.15s ease;
  }}
  .stTabs [data-baseweb="tab"]:hover {{
    color: {MCD_RED} !important;
  }}
  .stTabs [aria-selected="true"] {{
    color: {MCD_RED} !important;
    border-bottom: 3px solid {MCD_RED} !important;
    font-weight: 700;
  }}

  /* ─── 主标题卡片 ─── */
  .mcd-header {{
    background: {MCD_RED};
    border-radius: 16px;
    padding: 28px 36px;
    color: #FFFFFF;
    margin-bottom: 24px;
    border-left: 6px solid {MCD_GOLD};
  }}
  .mcd-header h1 {{
    font-size: 22px;
    font-weight: 900;
    margin: 0 0 6px 0;
    letter-spacing: -0.02em;
    color: #FFFFFF;
  }}
  .mcd-header p {{
    font-size: 13px;
    opacity: 1;
    margin: 0;
    font-weight: 500;
    color: #FFFFFF;
  }}

  /* ─── 内容卡片 ─── */
  .content-card {{
    background: #FFFFFF;
    border: 1px solid rgba(0,0,0,0.06);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: all 0.15s ease;
  }}
  .content-card:hover {{
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    border-color: rgba(0,0,0,0.1);
  }}

  /* ─── 章节标题 ─── */
  .section-title {{
    font-size: 14px;
    font-weight: 700;
    color: #1a1a1a;
    margin: 28px 0 14px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid {MCD_RED};
    letter-spacing: -0.01em;
  }}

  /* ─── 数据表格 ─── */
  .stDataFrame thead th {{
    background: {MCD_RED} !important;
    color: #FFFFFF !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    letter-spacing: 0.03em;
    border: none !important;
    padding: 10px 12px !important;
  }}
  .stDataFrame tbody tr:hover {{ background: rgba(228,0,4, 0.04) !important; }}
  .stDataFrame tbody td {{
    font-size: 13px !important;
    color: #333 !important;
    padding: 9px 12px !important;
    border-color: #F0F0F0 !important;
  }}

  /* ─── 清洗状态提示 ─── */
  .clean-status {{
    background: #FFF8F0;
    border: 1px solid {MCD_GOLD};
    border-left: 4px solid {MCD_GOLD};
    border-radius: 10px;
    padding: 10px 16px;
    margin-bottom: 20px;
    font-size: 13px;
    color: #000000;
    font-weight: 500;
  }}

  /* ─── 副文本 / 说明文字 ─── */
  .stCaption {{
    font-size: 12px !important;
    color: #AAA !important;
  }}

  /* ─── 数字高亮 ─── */
  .stAlert {{
    border-radius: 10px;
  }}

  /* ─── 隐藏 API Key 密码小眼睛 ─── */
  [data-testid="stTextInputVisibilityToggle"] {{
    display: none !important;
  }}

  /* ─── 按钮加载动画 ─── */
  @keyframes mcd-pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.5; }}
  }}
  .stButton > button[data-testid="stBaseButton-primary"]:disabled {{
    animation: mcd-pulse 1.2s ease-in-out infinite;
    background: {MCD_RED} !important;
    color: #FFF !important;
  }}

  /* ─── 主按钮样式 ─── */
  .stButton > button[data-testid="stBaseButton-primary"] {{
    background: {MCD_RED} !important;
    color: #FFF !important;
    font-weight: 700;
    border: none !important;
    border-radius: 10px !important;
    transition: all 0.15s ease;
  }}
  .stButton > button[data-testid="stBaseButton-primary"]:hover {{
    background: #B82015 !important;
    box-shadow: 0 2px 8px rgba(218,41,28,0.3);
  }}

  /* ─── CTR 结果卡片 ─── */
  .ctr-result-card {{
    background: #FFFFFF;
    border: 1px solid rgba(0,0,0,0.06);
    border-left: 3px solid {MCD_GOLD};
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .ctr-result-card:hover {{
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  }}

  /* ─── 配置信息卡片 ─── */
  .config-card {{
    background: #FFFFFF;
    border: 1px solid rgba(0,0,0,0.06);
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}

  /* ─── 基准CTR标签 ─── */
  .baseline-tag {{
    display: inline-block;
    background: #F8F7F5;
    color: #666;
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 6px;
    margin-right: 6px;
    margin-bottom: 4px;
    border: none;
    font-weight: 500;
  }}

  /* ─── 预测结果高亮 ─── */
  .pred-ctr-high {{
    color: {MCD_GREEN};
    font-weight: 700;
  }}
  .pred-ctr-mid {{
    color: {MCD_GOLD};
    font-weight: 700;
  }}
  .pred-ctr-low {{
    color: {MCD_RED};
    font-weight: 700;
  }}

</style>
"""
