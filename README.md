# ReadOrObey

视觉语言模型图片指令注入课程项目的统一工作区。研究将“读到图中文字”（Read）与“服从文字”（Obey）分开评估，并比较 COCO 静态图像与 Mind2Web 网页任务。COCO C0/C1/C2 与 C3 必须使用同一份已冻结的底图、选项和切分。

## 两份主要文档

- [完整项目规划与实操手册](<readorobey_complete_project_plan (1).md>)：研究问题、数据与渲染、五模型矩阵、评测指标、Pilot 门槛、预算与答辩交付。§2 记录目标模型的多渠道调研和选择规则。
- [团队分工与工作流](readorobey_team_division_and_workflow.md)：三位成员的独立模块、接口交接、请求量与里程碑。模型编号 M1–M5 与完整规划 §2 保持一致。

## 当前进度（2026-11-25）

- 已建立共享 `configs/`、`data/`、`src/`、`reports/`、`runs/`，以及三位成员的独立工作目录。
- 已下载并校验 COCO val2017 全部 5,000 张图和实例标注；原始图片位于本机 `data/raw/coco/`，不随仓库上传。
- 已实现 COCO 下载、统计审计和暂定 manifest 生成脚本；从 5,000 张图筛到 200 张候选，生成 12 张 Pilot、120 张 Formal 和 12 张备选的**暂定**切分。详见 [COCO 审计与 Pilot 说明](reports/coco/README.md)。
- 已调研四个 Qwen3-VL Dense 目标模型的多渠道可用性。硅基流动目录列出四个目标端点；百炼按实际地域核验。尚未完成付费图文调用验证，也未冻结 API 主备。
- Mind2Web 成员 3 模块已完成 Pilot 和 60-case Formal v2 实验：生成 A0/A1/A2/A2G/A2C 共 300 张正式输入图，运行六个 Qwen 模型的单步 Action、独立 Read/Plan、D1/D3 Prompt 防御与 Gate A/B/C，共发起 3,948 次 API 请求，得到 3,896 条有效结果。
- Mind2Web 的代码、实际输入图、原始请求与重试日志、聚合指标和研究分析已随仓库保存。入口见 [成员 3 Mind2Web 成果索引](reports/mind2web/FORMAL_RESULTS_ANALYSIS.md#成员-3-完成内容与项目索引)，主要结论见 [正式实验结果分析](reports/mind2web/FORMAL_RESULTS_ANALYSIS.md) 与 [防御失效分析](reports/mind2web/DEFENSE_FAILURE_ANALYSIS.md)。
- **仍待完成**：COCO 人工复核与模型 Pilot；Mind2Web Formal 60 case 的人工语义复核表和正式 manifest 冻结；跨家族 M5 对照。Mind2Web 主 Action 有效覆盖率为 96.6%，低于预设 98% 门槛，正式结论已报告缺失情况和敏感性边界。

## 模型渠道

M1–M4 分别是 Qwen3-VL 8B/32B 的 Instruct/Thinking 2×2 矩阵；M5 是跨家族参照。渠道或端点切换需记录 provider、地域、model ID、版本与费用；不能把 Plus、MoE 或 Qwen3.5 的结果当作原矩阵的等价替代。具体证据、限制和预算计算方式见完整规划 §2。API Key 只放在本机 `.env`，不要提交仓库。

## 目录

| 路径 | 用途 | 负责人 |
| --- | --- | --- |
| `configs/` | 模型、prompt 和数据筛选参数 | 成员 2 维护公共协议 |
| `data/raw/coco/`, `data/raw/mind2web/`, `data/raw/scam/` | 原始公开数据；本机保存，不提交仓库 | 对应数据负责人 |
| `data/manifests/` | 经审核冻结的共享索引与样本定义；应提交仓库 | 成员 1 / 3 |
| `data/processed/` | 渲染图及中间产物；按 `coco_c012/`, `coco_c3/`, `mind2web/` 分开 | 各模块负责人 |
| `src/common/` | 统一 API、prompt 装载和计分 | 成员 2 |
| `src/render/` | COCO 和网页截图选择、渲染 | 成员 1 / 2 / 3 |
| `src/eval/` | 推理、执行闸门与指标 | 成员 2 / 3 |
| `src/analysis/` | 数据审计、统计、绘图 | 共享 |
| `runs/` | 推理日志，按实验和模型划分；默认不提交，Mind2Web Formal 的复现日志作为本次例外随仓库保存 | 各模块负责人 |
| `reports/` | 审计报告、人工复核与最终图表 | 共享 |
| `members/member1/`, `member2/`, `member3/` | 每人独立的草稿、临时运行和说明 | 各成员 |

`data/manifests/` 只放**已审核**的实验样本；候选池、接触图和待审核 CSV 放在 `reports/coco/`。不要将模型运行结果混入数据索引。原图和渲染图由 manifest 中的相对路径引用，各成员在自己的机器上按相同目录下载或生成。

成员 3 的 Mind2Web 暂定清单、复核表、指标和分析位于 `reports/mind2web/`；Formal v2 实际输入图位于 `data/processed/mind2web/formal_v2/`，原始运行记录位于 `runs/mind2web_react_formal_v2/` 和 `runs/mind2web_probe_formal_v2/`。当前 manifest 明确标为 `provisional`，完成 60 case 人工语义复核后才转入 `data/manifests/`。

## COCO 准备

官方 2017 验证集：`data/raw/coco/val2017.zip` 和 `data/raw/coco/annotations/instances_val2017.json`。运行 `python src/analysis/audit_coco.py` 会计算筛选漏斗、按类别轮询形成 200 张候选、生成复核 CSV 和接触图；复核完成后再冻结 12 Pilot、120 Formal 与 12 备选。细节见 `reports/coco/README.md`。
