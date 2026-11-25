# Mind2Web 实验计划与实现核对

| 计划项 | 审计结果与处理 |
| --- | --- |
| Exp 3 主结局 | 旧 Pilot 直接返回编号，缺少工具路径。现已用单步 `click` 重新测完 10 case × 6 模型 × 3 条件，保存工具传输形式、原始响应和本地终止分类。 |
| 工具回合范围 | 当前 Action 在模型发出一次 `click` 后，由本地静态执行器记录终止回执。没有把回执再发给模型进行第二次生成。先前对话将“完整回合”描述为两次模型请求，该功能尚未实现，也不包含在计划的每 case × 模型六次请求预算里。静态 Mind2Web 截图无法提供点击后的反事实页面观察。 |
| Exp 3 独立诊断 | 已有 120 个 Plan 和 60 个 Read。复用这些独立响应，按 case 与模型键连接新的 A2 工具动作。保留全部八种组合。Plan 标签来自一轮人工核对，正式版应采用明确标准并抽检。 |
| Exp 4 防御 | 计划的最低 Pilot 矩阵把 D1/D3 留到 Formal。本轮按实际工具协议补跑了 80 次，并报告了 A0 效用与 A2 点选。 |
| Exp 5A/B/C | 补跑工具动作下的 DOM 检查、60 次文本审计和 40 次任务遮蔽重跑。Gate A 检查 A1 是额外诊断。Gate B 实际审计器为 X9，计划原列百炼 Flash。两者的结果需按实际配置署名。 |
| 数据分层 | 旧 Formal 的文案不覆盖计划子条件。另建 Formal v2，60 case、300 张图。每条 case 均有同底图 A2G/A2C，用于配对文案比较。原 A2 仍按 Generic/Contextual 各 30 分配。A1 两类各 30，near/far 各 30。几何和像素校验通过，正式语义复核记录待完成。 |
| 模型覆盖 | 实测 M1–M4、X9、X27 均来自 Qwen，通过硅基流动调用。跨家族 M5 无可验证结果。配置已支持按模型指定供应商。更换 Flash 审计器或接入 M5 后先跑小样本，确认图片与工具接口兼容。 |
| Prompt 一致性 | 已测版本的完整提示以 `configs/mind2web_react_pilot.json` 和 `configs/mind2web_pilot.json` 为准。计划正文的 D1、Gate B 描述与实测提示字面有差异。复现实验使用已测配置，并随 Formal 保存配置快照。 |
| 请求与复跑 | 支持独立数据切分、case 上限、模型子集、结果目录和失败续跑。更换模型端点、工具参数或提示后使用新结果目录，以免复用旧缓存。达到 ≥98% 覆盖率仍需以正式运行日志核算。 |
| 正式分析与交接 | 指标 JSON 提供 Wilson 区间、配对 Bootstrap、McNemar、合并结果按 case 聚类的 Bootstrap 和探针交叉表。项目级 Formal 图、答辩 PPT 与 Thinking 日志交接依赖正式结果。 |

## 正式运行

先复核 [Formal v2 审查表](formal_v2_review/review_decisions.csv) 和对应接触图，解决任务、目标或渲染存在疑义的 case，冻结实际使用的 manifest。将已验证的 M5 配置同步至两个运行器的配置文件。下例用本轮配置作为起点，Formal 的数据 manifest 路径以冻结文件为准。Gate B 默认复用 X9，选用其他审计器时在 Action 配置显式替换。

```powershell
python src/eval/run_mind2web_react_pilot.py --manifest data/manifests/mind2web_formal_v2.jsonl --split formal --cases 60 --models M1 M2 M3 M4 M5 --run-dir runs/mind2web_react_formal_v2 --retry-failed
python src/eval/run_mind2web_pilot.py --manifest data/manifests/mind2web_formal_v2.jsonl --split formal --cases 60 --models M1 M2 M3 M4 M5 --kinds plan read --stage baseline --run-dir runs/mind2web_probe_formal_v2 --retry-failed
python src/analysis/summarize_mind2web_react_pilot.py --manifest data/manifests/mind2web_formal_v2.jsonl --split formal --cases 60 --models M1 M2 M3 M4 M5 --run-dir runs/mind2web_react_formal_v2 --direct-run-dir runs/mind2web_probe_formal_v2 --plan-review reports/mind2web/formal_v2_plan_review.jsonl --output reports/mind2web/formal_v2_metrics.json
```

原计划五模型矩阵预算为 900 个基线 Action、900 个独立 Plan/Read、480 个 Prompt 防御、最多 360 个 Gate B 和 240 个 Gate C，共最多 2,880 个唯一请求。本次可用模型为六个，基线 Action 与独立探针各为 1,080 次，另有 720 次配对文案 Action，总预算最多 3,960 次。Gate B 需要有效的上游提议。重试次数另外统计。待正式 A2 Plan 标签填写后再重算诊断交叉表。标签沿用 Pilot 文件中的 `sample_id`、`model_id` 和 `label` 字段。

顺序运行入口为 `python scripts/run_mind2web_formal.py`，阶段日志在 `runs/mind2web_formal_pipeline.log`，逐请求原始结果在对应 `runs/mind2web_*_formal_v2/requests.jsonl`。脚本先验证数据、跑 3-case 检查，再依次跑主矩阵与防御、配对文案、独立 Plan/Read、汇总。每模型的 RPM/TPM 由配置及运行器控制。计划中的跨家族 M5 目前缺少可用密钥和经过验证的图片工具接口，顺序脚本运行六个已测通的 Qwen 模型。
