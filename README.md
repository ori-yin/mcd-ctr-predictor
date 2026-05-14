# MCD CTR 预测工具

基于麦当劳历史触达数据训练的 CTR 预测 + 文案优化建议工具。

## 功能
- 上传文案列表（CSV/Excel）
- LLM 批量预测 CTR（支持 OpenAI / SiliconFlow）
- 改进建议 + 字数优化提示
- 下载结果

## 依赖
```
pip install streamlit pandas openai python-dateutil
```

## 运行
```bash
streamlit run ctr_predictor.py
```

## CTR 基准数据
基准 CTR 数据来源：2026年1-5月触达数据，涵盖6个维度：
- 渠道基准CTR
- 渠道×是否用券
- 渠道×计划类型（AARRPlan / 普通Plan）
- 渠道×工作日类型（工作日 / 非工作日）
- 渠道×标题字数区间
