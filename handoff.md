# MCD CTR Predictor — 交接文档（HANDOFF）

> 新 session 从这里接手即可。本文件说明项目现状、结构、怎么跑、本轮改动、已知坑，以及给未来 session 的工作建议。

---

## 1. 这是什么

基于麦当劳历史触达数据训练的 **CTR 预测 + 文案优化建议** 工具。Streamlit 单页应用，喂文案列表（CSV/Excel），LLM 批量预测 CTR + 给出改进建议 + 字数/时段优化提示，最后导出 CSV。

**形态**：单文件主程序 + 样式 + JSON 基准数据。无 git 历史（OneDrive 同步目录），改之前先复制一份 `.bak`。

**触发场景**：运营/分析师上传一批待发文案，工具给出每条预测 CTR + 优化建议，决定哪条先发/改写。

---

## 2. 怎么跑

### 一键启动（推荐）
双击 `setup_and_run.bat`：
- 自动检查 Python、创建 venv（`--system-site-packages`）、检查/安装依赖、启动 streamlit
- 默认端口 8501（Streamlit 默认），窗口关闭 = 停服务

### 手动启动
```bash
cd "c:/Users/a952462/OneDrive - ATOS/桌面/mcd-ctr-predictor-main"
python -m venv --system-site-packages venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m streamlit run ctr_predictor.py
```

浏览器开 http://localhost:8501

### 必须填的输入
- 上传 CSV/Excel（标题 + 正文 必填，其余 6 列选填）
- API Key（侧边栏 → API 配置 → API Key）
- API Provider + Model（默认 SiliconFlow / 百度千帆）
- 点「开始预测」

---

## 3. 目录结构

```
mcd-ctr-predictor-main/
├── ctr_predictor.py       主程序（约 580 行），含 baseline 查找 + LLM 调用 + UI
├── styles.py              CSS 样式（get_css()），品牌色：红 #DA291C / 金 #FFC000
├── ctr_baseline.json      基准 CTR 数据（6 个维度，2026年1-5月数据源）
├── requirements.txt       streamlit / pandas / openpyxl / openai
├── setup_and_run.bat      一键启动（仿 mcd-reach-trend 风格）
├── README.md              5 行功能介绍
└── handoff.md             本文件
```

---

## 4. 关键约定（改代码前必读）

### 数据契约（ctr_baseline.json）
- **版本**：v3.0，最后更新 2026-08-18，指数衰减加权校准
- **数据源**：CNN历史备份.xlsx（2024-10-15 ~ 2026-08-16，22 个月，48090 条 Plan）
- **加权方法**：λ=0.010 指数衰减，半衰期 ≈69.3 天（越靠近 2026-08-16 的数据权重越高）
- **6 个维度**（v3）：渠道 / 渠道×用券 / 渠道×预算Owner / 渠道×计划类型 / 渠道×工作日类型 / 渠道×标题字数 + 时段_小时（沿用 v2 数据源）
- **元信息字段**（v3 新增）：`last_refreshed_at / last_refreshed_by / data_window_start / data_window_end / calibration_lambda / calibration_half_life_days / weighted_method`
- **计划类型**只有两种：`AARRPlan` / `普通Plan`（"常规Plan" 不在 baseline 里，已统一为白名单）
- **CTR 数值**是小数（0.035531 = 3.55%），不是百分比字符串
- **渠道清单**：`APP Push / 企微1v1 / 微信公众号推文 / 微信小程序订阅消息 / 微信订阅 / 短信`
- **微信订阅**：v3 xlsx 无新样本，渠道值保留 v2 旧值 0.034362
- **关键差异**（v2 → v3）：企微1v1 暴跌 49.8%（0.0145 → 0.0073）、微信公众号推文 +26.8%、APP Push -26.9%
- **校准脚本**：`calibrate_baseline.py`（读 xlsx → 加权聚合 → 写 JSON）。`ctr_baseline_v2.json.bak` 是 v2 备份。

### 列名映射（auto_detect）
- 标题别名：标题 / 文案标题 / title / 标题列 / push_title / 标题title
- 正文别名：内容 / 正文 / 文案 / content / body / push_content / 正文内容
- 渠道别名：渠道 / channel / 触点 / push_channel
- 用券别名：是否用券 / 用券 / coupon / 是否有券
- 工作日别名：工作日类型 / 工作日 / workday / 日期类型
- 时间别名：发送时间 / 时间 / time / 推送时间 / send_time
- 计划别名：计划类型 / plan_type / 计划type / AARRPlan
- Owner 别名：预算owner / owner / 预算Owner / 负责人

**严格匹配**（不区分大小写），**不做子串匹配**（避免 `title` 误匹配 `subtitle`）。

### baseline 查找优先级（get_baseline_ctr）
1. 渠道×标题字数（最具体，**已接线 ✅**）
2. 渠道×计划类型
3. 渠道×预算Owner
4. 渠道×是否用券
5. 渠道×工作日类型
6. 渠道整体（兜底）

如果全都查不到，回退到 baseline 里所有渠道 CTR 的均值（兜底再兜底 0.002）。

### prompt 喂给 LLM 的内容
- 渠道 CTR 基准（按 CTR 降序全列）
- 用券效果 Top 8
- 时段 CTR（按小时升序全列）
- 各渠道高CTR标题字数 Top 3（**已实际喂入数据**）
- AARRPlan vs 常规Plan
- 渠道×Owner Top 15

prompt 模板明确说"标题字数仅供参考，不是主要因素，权重低于渠道、时段和内容质量"。

---

## 5. 当前状态（2026-08-18）

### 5.1 本轮代码审查 + 11 处修改

| 优先级 | 位置 | 改动 |
|---|---|---|
| 🔴 P0 | `call_llm_batch` | `char_range=get_char_range(title)` 接线 |
| 🔴 P0 | `get_disp_bl` | `char_range=get_char_range(row["标题"])` 接线 |
| 🔴 P0 | `get_disp_bl` 兜底 | 0.002 硬编码 → baseline 渠道均值 |
| 🟠 P1 | `get_baseline_ctr` L62 | 计划类型白名单去 `常规Plan` |
| 🟠 P1 | `call_llm_batch` L236 | 同上 |
| 🟠 P1 | `get_disp_bl` L459 | 同上 |
| 🟠 P1 | `auto_detect` | 子串匹配 → 严格相等匹配 |
| 🟠 P1 | `missing_title` | 从 `detected["标题"]` → 用户最终选的 `col_title` |
| 🟠 P1 | `build_context_for_llm` | `char_data` 检查了却没用 → 真正按渠道聚合输出 Top 3 |
| 🟠 P1 | JSON 解析 | 新增 `re.search(r'\[.*\]', ...)` 容错剥前缀文字 |
| 🟠 P1 | `KNOWN_OWNER_ALIASES` | 去重 `"预算owner"` |
| 🟠 P2 | `time_str` 解析 | `\b\d{1,2}\b` → HH:MM / HH时 / 数字 三级回退 + 0-23 边界 |
| 🟠 P2 | API 调用 | 加 `timeout=60` |
| 🟠 P2 | 主循环 | 返回条数不齐时 `st.warning` |
| 🟠 P2 | `OPTIMAL_CHARS` | 加注释提示 JSON 同步 |
| ⚪ | L14 导入 | 去 4 个未用颜色常量 |
| ⚪ | UI 示例数据 | 5 个 `常规Plan` → `普通Plan` |
| ⚪ | JSON | 删 `baseline_ctr_by_channel`（与 `dimensions.渠道.data` 逐字重复）+ 删 `insights`（没人读） |

### 5.2 验证结果（15/15 通过）
测试覆盖：char_range 接线、计划类型白名单、auto_detect 严格匹配、time_str 三级回退、build_context char_data 实际输出、JSON 字段清理、suggest_char_range、missing_title 判定、OPTIMAL_CHARS 完整。

### 5.3 当前数据基线（v3.0）
`ctr_baseline.json` 最后更新 **2026-08-18**，版本 **v3.0**。

- **数据源**：CNN历史备份.xlsx（2024-10-15 ~ 2026-08-16，48090 条 Plan）
- **加权**：λ=0.010 指数衰减，半衰期 ≈69.3 天
- **核心方法**：越靠近 2026-08-16 的 Plan 权重越高
- **校准脚本**：`calibrate_baseline.py`（可重复运行）
- **v2 备份**：`ctr_baseline_v2.json.bak`

⚠️ **关键差异**：v2 → v3 企微1v1 暴跌 49.8%（1.45% → 0.73%）。如果旧 session 还引用 v2 数字，预测会系统性高估企微1v1 文案 CTR。

---

## 6. 已知坑（不要踩）

### 6.1 已修（本轮）
- ✅ `char_range` 维度"装了没接线"：之前定义了优先级但从未传入，标题字数维度完全失效。**本轮已修**
- ✅ 计划类型"三处定义不一致"：`get_baseline_ctr / call_llm_batch / get_disp_bl` 白名单宽严不一。**本轮已统一**
- ✅ API Key 硬编码泄露：源码 L305 有默认值 `ce-v3/ALTAKSP-...`。用户说是假的，没事。**保留默认值无影响**
- ✅ `auto_detect` 子串过宽：`title` 会误匹配 `subtitle`。**本轮已改严格匹配**
- ✅ JSON 解析脆弱：LLM 在 ```json``` 外的解释文字会残留。**本轮已加 `re.search(r'\[.*\]', ...)` 容错**
- ✅ 区间时间被 HH时 抢先匹配：`"8-10时"` 解析成 10（HH时），正确应是中点 9。**已重排正则优先级，区间优先于 HH时**
- ✅ baseline 过期无提示：`data_window_end` 距今 >90 天仍是静默。**侧边栏 + `_check_baseline_age` + `st.warning` 已加**
- ✅ 侧边栏盲选：看不出当前用的是哪一版 baseline、窗口、加权方式。**侧边栏加版本/窗口/方法三行展示**
- ✅ 无单元测试：`time_str / auto_detect / build_context` 全靠手测。**`tests/verify.py` 已加（33 用例），无 pytest 依赖**

### 6.2 还没碰（可能未来要做）
- ⚠️ **`baseline_ctr_by_channel` / `insights` 已删**（本轮）：如果业务想用 `insights` 字段做汇报展示，需要从代码重新生成或保留
- ⚠️ **`OPTIMAL_CHARS` 双源**：`ctr_predictor.py` 维护一份 + `ctr_baseline.json` 的 `渠道_x_标题字数.建议范围` 也有一份。已加注释提醒手工同步，**没动逻辑**
- ⚠️ **`get_baseline_ctr` 优先级没考虑样本量**：`APP Push_5-6字` 小样本维度 CTR 噪声大，反而不如 `渠道整体` 稳健。已和用户确认"不大改"，本轮跳过
- ⚠️ **没 `if __name__ == "__main__"`**：直接 `python ctr_predictor.py` 会执行 UI 层。本轮未加，按用户"不破坏"原则保持
- ⚠️ **没 git 历史**：OneDrive 同步目录，`.git` 已被吞（按 memory 里 `feedback-onedrive-git` 的提示）。如要 git 化，需先在非 OneDrive 目录 init + push

### 6.3 LLM 相关
- ⚠️ **batch 之间 sleep 1.2 秒**：限速经验值，不同 provider 实际限速不同。如果 429 增多，调大 `time.sleep` 或减 `batch_size`
- ⚠️ **timeout=60**：本轮已加。如果用户反馈"卡太久"，可调大
- ⚠️ **返回条数不齐**：本轮加了 `st.warning` 提示。如果 LLM 经常输出错条数，建议在 prompt 里强调 "严格返回 N 条"
- ⚠️ **dirtyjson 不可达**：当前用 `json.loads` 标准解析，LLM 输出非标 JSON 会失败。如果发现脏数据多，加 `dirtyjson` 依赖

---

## 7. 给未来 session 的工作建议

### 7.1 如果用户说"数据校准"
直接跑 `python calibrate_baseline.py` 即可（已封装好）：
1. 读 xlsx（路径写死在脚本顶 `SOURCE_XLSX`，如有变动改一下）
2. 读 v2 备份 `ctr_baseline_v2.json.bak` 拿"沿用旧值"字段（时段_小时）
3. 按 λ=0.010 加权聚合 7 个维度
4. 写 v3 JSON（含 6 个元信息字段）

**改 λ**：脚本顶部 `LAMBDA = 0.010`，改成你想要的（比如 0.005 半衰期 139 天，0.02 半衰期 35 天）。λ 越大"越近的越重要"。

**数据源变了**：把新 xlsx 覆盖到 `常用文件\数据\CNN历史备份.xlsx` 即可（或改 `SOURCE_XLSX` 路径）。

**保留字段**：当前"微信订阅"渠道保留 v2 旧值（v3 xlsx 无新样本）。如果新 xlsx 有了，再去掉 `SKIP_CHANNELS`。

### 7.2 如果用户说"加新功能"
- **新维度**：在 `ctr_baseline.json` 加 `dimensions.<新维度>.data`，在 `get_baseline_ctr` 加查找分支
- **新 provider**：在 `call_llm_batch` 的 provider 白名单加分支 + `model_map` 加模型列表
- **新评估指标**：在 `df_w["预测CTR"]` 后处理逻辑加列

### 7.3 如果用户说"改样式"
- 品牌色在 `styles.py` 顶部（MCD_RED/GOLD/GREEN/BG）
- 主程序**已不再 import 颜色常量**（本轮清理过死代码），改色必须改 `styles.py`
- `mcd-header` 红卡 / `section-title` 红下划线 / `baseline-tag` 灰底标签 是 3 个最常用组件

### 7.4 如果用户说"出 bug"
1. 先看 setup_and_run.bat 输出，确认 Python / venv / 依赖 OK
2. 看 sidebar API 配置：API Key 是否有效、Provider/Model 是否选对
3. 看 `last_updated` 字段：JSON 是不是过期了
4. 跑测试：手写一个 `_verify.py`（仿本轮验证脚本），覆盖关键函数
5. 改之前先 `cp ctr_predictor.py ctr_predictor.py.bak`（OneDrive 无 git，备份是唯一保险）

### 7.5 一键启动常见问题
- 端口被占：另起 streamlit 进程，`taskkill /F /PID <pid>` 杀掉；或手动跑 `streamlit run ctr_predictor.py --server.port 8502`
- 阿里云镜像失败：bat 会 fallback 清华镜像，两个都失败就是网络问题
- venv 损坏：删 `venv/` 目录重跑 bat

---

## 8. 相关 memory 条目

- `cnn-weekly-suite-handoff-20260710.md` — 同类项目的 handoff 范式参考（更详细）
- `mcd-reach-trend-main/setup_and_run.bat` — 一键启动 bat 范式参考
- `mcd-analysis` skill — 麦当劳多 session 数据分析工作流（本项目不是 mcd-analysis 流程，但触达数据更新可参考）

---

## 9. 联系信息

- 项目位置：`c:/Users/a952462/OneDrive - ATOS/桌面/mcd-ctr-predictor-main/`
- 数据源负责人：（待用户确认）
- LLM API Key 联系人：（待用户确认）
- 最后更新：2026-08-18（本轮代码审查 + bat + handoff + v3 数据校准）

---

## 10. 本会话迭代（2026-08-18）

按时间3 件事，所有改动 OneDrive 同步目录下完成（**没 git**）。

### 10.1 代码审查 + 修复
触发：用户问有没有 BUG / 死代码。审查发现 17 项（P0 2 / P1 6 / P2 5 / 死代码 3 + 1 跳过）。实际改 15 处，验证 15/15 通过。详见 §5.1。

### 10.2 一键启动 bat + handoff 创建
- `setup_and_run.bat`：仿 reach-trend，2.3KB
- `handoff.md`：本文件

搜遍 OneDrive 无 CTR 专属 handoff，已有的两份是 AB 实验 PPT 和 IT-traffic 图书馆。

### 10.3 v2 → v3 数据校准（指数加权）
触发：用户问能不能指数平滑加权。参数：
- λ = 0.010，半衰期 ≈69 天
- 微信订阅保留 v2 值（新数据全 NaN）
- 加 6 个元信息字段，version v2 → v3

**关键发现：企微1v1 暴跌 49.8%**（1.45% → 0.73%）。这是用户感觉"阈值不对"的根因。

产出：
- `ctr_baseline.json` v3.0（10.7KB）
- `ctr_baseline_v2.json.bak`（v2 备份）
- `calibrate_baseline.py`（8KB，可重复运行）

### 10.4 文件清单
```
ctr_predictor.py            ← 11 处修复（10.1）+ 4 处增量（10.5）
ctr_baseline.json           ← v3 加权（10.3）
ctr_baseline_v2.json.bak    ← v2 备份（10.3）
calibrate_baseline.py       ← 新增（10.3）
setup_and_run.bat           ← 新增（10.2）
handoff.md                  ← 本文件
tests/verify.py             ← 新增（10.5，33 用例全过）
styles.py / requirements.txt / README.md   （未动）

### 10.5 第二轮小改动（低风险诊断 + UI 收尾）

| # | 改动 | 文件 |
|---|---|---|
| #14 | 侧边栏加 v3 baseline 元信息（版本/窗口/加权方法） | ctr_predictor.py L349 |
| #12 | `_check_baseline_age` + `data_window_end >90 天` 触发 `st.warning` | ctr_predictor.py L384 / L396 |
| #11 | 单元测试 `tests/verify.py`（33 用例，无 pytest 依赖） | tests/verify.py |
| #6  | `get_time_multiplier` 区间 X-Y 取中点，X-Y 优先级排在 HH时 之前 | ctr_predictor.py L88-L100 |

测试结果：`python tests/verify.py` → 33/33 PASS。
```