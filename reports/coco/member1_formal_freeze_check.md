# 成员 1：Formal 底图清单冻结前检查

日期：2026-11-25。范围：COCO 底图与四选一审核、C0/C1/C2 Pilot、C2 字号梯度；模型仅 M1–M4。按用户确认接受的 v3 修订判断，旧的 `P(O|¬R)<0.05` 不再是硬门槛，独立 Read 与 Task 的配对只作描述。C3、Thinking 机制和 Mind2Web 的实验执行分别由其他成员负责，不纳入本记录的成员 1 门槛。

## 判定

**成员 1 的数据与 C0/C1/C2 Pilot 技术检查通过，可以将暂定的 120 张 Formal 底图清单提交成员 2 做共享清单交接确认。** `data/manifests/coco_base_120.json` 当前尚未生成；本记录不是冻结操作，也不表示其他成员的实验已经完成。依据 `reports/coco/README.md` 的共享清单流程，成员 1/2 确认后再运行 `python -m src.render.select_coco --pilot-approved`。

## 核查结果

| 检查 | 结果 | 判定 |
| --- | --- | --- |
| 原图与 MCQ 审核 | 250 张候选中 144 张图像 `accept`；入选 144 张的 MCQ 均 `accept` | 通过 |
| `select_coco --check` | `valid: true`；12 Pilot / 120 Formal / 12 Reserve；检查原图、唯一 ID、选项、类别和答案平衡 | 通过 |
| Pilot 渲染文件 | C0/C1/C2 共 60 张、C2 消融 12 张，文件齐全且与 manifest SHA-256 一致；渲染器实现了框外逐像素检查 | 通过 |
| M1–M4 C0/C1/C2 请求 | 每模型 84/84，共 336/336 | 通过 |
| 32B-Instruct C0 正确率 | 12/12，门槛 ≥85% | 通过 |
| 32B-Instruct C0→C1_object | 12/12→12/12，下降 0 个百分点，门槛 ≤10 | 通过 |
| C2 正常字号 Read | 四模型各 24/24 完整转录，门槛 ≥80% | 通过 |
| C2 低对比梯度 | M1 正常 4/4、低对比 2/4、大字 4/4；M3 为 4/4、0/4、4/4；降幅分别 50、100 个百分点，门槛 ≥15 | 通过 |
| C0/C1/C2 Task 合法格式 | 四模型各 60/60，门槛 ≥95% | 通过 |

四模型的 C0 和 C1_object Task 正确率均为 12/12。C2 错误选项输出：M1 2/24，M2 0/24，M3 0/24，M4 0/24；这些是 Pilot 观察值，v3 没有要求注入成功率达到某个下限。正式效应应在冻结后的 120 图上估计。

## 证据与交接

- 数据审核：`reports/coco/coco_review.csv`、`reports/coco/coco_mcq_review.csv`、`reports/coco/coco_base_120.provisional.json`。暂定索引 SHA-256：`44c49ee991b2c3a4be9dd1192ec7483a9af9dcc2a1df8df036ec411479fbc4ba`。
- Pilot 清单：`data/manifests/coco_pilot_manifest.provisional.jsonl`，SHA-256：`cc7df78147e49ca615cab239fbfd773fd7f21134ec369c922f4711a2eef74544`。
- 四模型逐请求日志：`runs/coco_pilot_m1_m3.jsonl`、`runs/coco_pilot_read_v2_m1_m3.jsonl`、`runs/coco_pilot_m2_m4.jsonl`；按当前 Prompt 哈希重算的结果为 `reports/coco/coco_protocol_v3_pilot_all_qwen.json`。分析器忽略 96 条旧版 Read Prompt 记录，未混入当前指标。
- 字号梯度证据：`reports/coco/coco_remaining_pilot_summary.json` 与 `runs/coco_c2_gradient_read_m1_m3.jsonl`。

冻结后成员 1 再生成正式 C0/C1/C2 与前 40 张 C2 消融图，抽检 15 张成品，随后按四模型范围运行正式请求。成员 2 使用同一冻结底图索引，不再单方更换图像或选项。
