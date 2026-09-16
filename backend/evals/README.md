# TripMind Agent 评测体系

该目录用于回答两个不同问题：

1. 自动化测试：代码是否仍能运行、接口和解析器是否符合约定。
2. Agent 评测：需求理解、工具轨迹、POI 可靠性和最终行程质量是否真的变好。

评测采用三层组合：确定性规则负责持续回归；人工评分负责路线可执行性和体验判断；少量 LLM-as-judge 用于扩大语义质量抽检。任何真实 API Key 都不写入数据集或报告。

发布口径不再用一个总分混合所有含义：

- `overall`：全部 30 条版本化样本；
- `hard-set`：避雷、无障碍、多轮修正、日期冲突、记忆覆盖、节奏限制等高风险切片；
- `raw`：模型刚返回、尚未经时间轴重建、POI 置换和确定性降级的计划；
- `final`：经系统校验与修复后真正交付给用户的计划。

## 目录

```text
evals/
├── data/
│   ├── trip_eval_dataset.jsonl       # 30 条版本化旅行需求与期望
│   ├── sample_runs.jsonl              # 两条脱敏运行记录，用于验证评测管线
│   └── human_reviews.example.jsonl    # 人工评分示例
├── metrics.py                         # 规则评分与汇总
├── runner.py                          # 离线/真实 API 运行器与报告生成
└── reports/                           # 本地报告，默认不提交
```

数据集覆盖单轮、多轮更正、日期/天数冲突、缺少必填信息、用户指定 POI、避雷、亲子、老人、慢节奏、长期记忆覆盖等场景。每条数据都包含：

- `messages`：对话输入；
- `expected_brief`：结构化需求真值；
- `expected_tools`：期望的节点/工具及关键参数；
- `selected_places`：必须进入行程的用户选择；
- `should_plan`：信息冲突或缺失时应为 `false`，用于检查系统没有提前开跑；
- `tags`：便于按场景切片分析。

## 指标定义

| 指标 | 计算方式 |
| --- | --- |
| Planning Brief 准确率 | 城市、日期、天数、交通、住宿逐字段准确率；偏好使用集合相似度 |
| 工具选择正确率 | 期望工具与实际工具的 precision、recall、F1 |
| 工具参数正确率 | 对每个期望调用比较城市、日期、偏好等关键参数 |
| POI 城市通过率 | 高德返回城市或地址与目的地一致 |
| POI 坐标通过率 | 坐标存在且位于中国经纬度合理范围 |
| POI 身份通过率 | POI ID 存在且名称不是占位文本 |
| POI 营业状态数据覆盖率 | `operational_status` 明确为 `available` 或 `unavailable` 的比例；`unknown` 如实保留 |
| POI 综合通过率 | POI ID、名称、城市、坐标均通过，且没有明确标记为关闭 |
| POI 类型覆盖/通过率 | 必须保留高德 `type/typecode`，公交站、寄存处、停车场、住宅区等不得冒充景点 |
| 时间冲突率 | 相邻时间段重叠、非法时间和空白日程占所有检查项的比例 |
| 路线距离通过率 | 根据已核验坐标计算每日相邻景点距离，捕捉明显跨区赶场 |
| 真实通勤时间 | 真实运行使用高德路线 API 核验 transport 路段，统计覆盖率和模型是否低估通勤时间 |
| 避雷约束 | 数据集使用 `avoid_terms` 保存明确禁止项，最终景点、餐饮、时间轴和说明中均不得出现 |
| 选择地点覆盖率 | 用户勾选地点是否出现在景点清单或 attraction 时间轴 |
| 降级触发率 | `fallback` 节点、`fallback_plan` 或工作流错误占正式规划样本比例 |
| 性能与成本 | 单次耗时、输入/输出 Token、API 成本及汇总 |

现有业务 API 没有返回供应商 `usage` 时，真实运行器会估算 Token 并标记 `estimated: true`；读取离线运行记录时则优先使用记录的精确 usage。

## 1. 验证评测管线（不调用 API）

```bash
cd backend
source .venv/bin/activate
python -m evals.runner \
  --runs evals/data/sample_runs.jsonl \
  --human-reviews evals/data/human_reviews.example.jsonl
```

输出包括：

- `evaluation-*.json`：机器可读完整结果；
- `evaluation-*.md`：指标总览和最低分样本；
- `human-review-*.jsonl`：待填写的人工评分模板。

样例记录只用于检查评测代码，不代表真实模型效果。

## 2. 运行真实端到端评测

先启动后端并确认 `.env` 中的模型和高德配置有效，然后另开终端执行全量 30 条：

```bash
cd backend
source .venv/bin/activate
python -m evals.runner \
  --live \
  --confirm-live \
  --base-url http://localhost:8000 \
  --input-cost-per-million 0 \
  --output-cost-per-million 0
```

`--confirm-live` 是强制成本保护。不传 `--limit` 时必须执行全部 30 条。运行器会调用对话澄清接口、提交后台任务、等待 LangGraph 完成、收集原始/最终计划与 SSE 轨迹，并对最终路线抽取高德真实通勤时间。真实运行记录会一起保存，后续可以零成本离线回放。

仓库同时提供手动触发的 `Live agent evaluation` GitHub Actions 工作流。配置 `LLM_API_KEY`、`AMAP_API_KEY` 等 Repository Secrets 后，可从 Actions 页面选择 5、10、20 或 30 条真实样本；工作流不会随普通 push 自动执行，避免意外消耗额度，结果会作为 Artifact 保留 30 天。

## 3. 人工评分

打开生成的 `human-review-*.jsonl`，将四项评分填为 1–5：

- `correctness`：事实、日期、城市是否正确；
- `route_practicality`：路线、时长和节奏是否可执行；
- `preference_alignment`：是否满足偏好、避雷和必选地点；
- `explanation_quality`：建议是否具体、清晰、不编造。

完成后用同一份运行记录重新执行并传入：

```bash
python -m evals.runner \
  --runs evals/reports/live-runs-YYYYMMDD-HHMMSS.jsonl \
  --human-reviews evals/reports/human-review-YYYYMMDD-HHMMSS.jsonl
```

## 4. 少量 LLM-as-judge

Judge 使用现有 OpenAI-compatible 环境变量，只抽检指定数量：

```bash
python -m evals.runner \
  --runs evals/reports/live-runs-YYYYMMDD-HHMMSS.jsonl \
  --judge-sample 5
```

LLM judge 不能替代 POI、坐标、时间冲突等确定性规则，也不应成为唯一发布门禁。建议固定模型和温度，保存 judge 模型版本，并定期拿人工结果校准。

## 5. 回归门禁

本地或 CI 可传 `--fail-on-threshold`。核心指标低于 `runner.py` 中的阈值时返回退出码 1：

```bash
python -m evals.runner \
  --runs path/to/candidate-runs.jsonl \
  --fail-on-threshold
```

建议把线上出现的真实失败脱敏后追加为新 case，并保留一套固定回归集。不要只看总分：按 `tags` 分析日期冲突、多轮更正、用户必选地点、记忆覆盖等切片，能更快发现退化原因。

## 6. 严格发布门禁（必须完成人工评分）

真实跑数只产生待审记录，不能单独宣称“发布通过”。评审人填完 30 条 `human-review-*.jsonl` 后，用同一份运行记录执行：

```bash
python -m evals.runner \
  --runs evals/reports/live-runs-YYYYMMDD-HHMMSS.jsonl \
  --human-reviews evals/reports/human-review-YYYYMMDD-HHMMSS.jsonl \
  --release-gate
```

`--release-gate` 会同时检查 overall 和 hard-set，要求原始输出捕获率、原始/最终质量分、POI 类型、路线距离、真实通勤、避雷约束以及人工评分全部达标。人工评分覆盖不足 100% 或平均分低于 80% 时，门禁必须失败。

## 运行记录格式

```json
{
  "case_id": "TM-001",
  "planning_brief": {},
  "tool_calls": [
    {
      "name": "amap.weather.forecast",
      "arguments": {"city": "北京", "start_date": "2027-04-02", "end_date": "2027-04-04"},
      "success": true
    }
  ],
  "trip_plan": {},
  "events": [],
  "latency_ms": 8200,
  "usage": {
    "input_tokens": 4380,
    "output_tokens": 2070,
    "api_cost_usd": 0.00321,
    "estimated": false
  },
  "error": null
}
```

LangGraph 事件只记录工具名和非敏感参数，不记录 API Key。工具轨迹评测关注实际选择及关键参数，不要求保存完整提示词或第三方响应。
