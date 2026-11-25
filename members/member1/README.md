# 成员 1：COCO C0/C1/C2

负责 COCO 底图、四选一选项的人工核验与冻结；`src/render/` 下的 C0/C1/C2 渲染及消融；12 图 Pilot、正式推理和 C2 统计。共享产物放 `data/manifests/`、`data/processed/coco_c012/` 和 `reports/`；个人草稿放本目录的 `scratch/`，个人日志放 `runs/`。

## 代码流程

1. 用 `python scripts/download_coco.py` 下载并校验 COCO，再运行 `python src/analysis/audit_coco.py --pool-size 250` 生成当前候选池。原图在 `data/raw/coco/`，不提交 Git。
2. 按 `reports/coco/README.md` 逐张审核原图，在 `reports/coco/coco_review.csv` 填决定。达到至少 144 张 `accept` 后运行 `python src/render/prepare_coco_manifest.py` 重建暂定索引，再运行 `python src/render/select_coco.py --sync-mcq-review` 同步 MCQ 审核表。逐张核对四个选项并在 `reports/coco/coco_mcq_review.csv` 填决定。两表均须将入选图标为 `accept`；若更换图片或选项，应重新审核并保留审查记录。MCQ 审核表内的选项、答案与暂定索引必须一致。
3. `python src/render/select_coco.py --check` 检查 12/120/12 切分、选项、类别平衡、人工审核和原图。暂定 Pilot 可先用 `python src/render/render_coco_c012.py --allow-provisional --split pilot` 渲染审图；包括 Pilot 前 4 图的 12 张字号/双语探针图。Pilot 请求也需加 `--provisional`。核对计划中的 Pilot 门槛后，执行 `python src/render/select_coco.py --pilot-approved`，生成含 132 条 Pilot/Formal 记录与 12 条备选记录的 `data/manifests/coco_base_120.json`。不要把暂定索引当作正式实验数据。
4. `python src/render/render_coco_c012.py` 生成 660 张主实验图、120 张正式消融图及 12 张 Pilot 消融图，输出两份 JSONL 索引；PNG 保证框外逐像素一致。正式图需要冻结 manifest。
5. 先用 `python src/eval/run_coco_c012.py --experiment main --split pilot --model MODEL_ID --provider PROVIDER --base-url BASE_URL` 查看请求数。加 `--execute` 才调用 API。密钥从 `OPENAI_API_KEY` 环境变量读取；可用 `--api-key-env` 修改。当前范围仅 M1–M4，正式集用 `--split formal`，M1/M3 可用 `--experiment all` 一次覆盖主实验与消融。运行器现复用 `configs/prompts.yaml` 的 v2 Task/Read 模板。输出在 `runs/`，已成功请求按图像、Prompt、模型和渠道哈希跳过；失败请求可重跑。
6. Pilot 的 v3 门槛与四模型结果见 `reports/coco/member1_formal_freeze_check.md` 和 `coco_protocol_v3_pilot_all_qwen.json`。正式统计见 `coco_c012_formal_summary.json`；运行 `python -m src.analysis.plot_coco_c2 reports/coco/coco_c012_formal_summary.json --only-ablation` 可从该汇总重绘 C2 消融图，不会调用 API。完整交付清单和复现限制见 `reports/coco/member1_delivery.md`。

当前仓库有 250 张机器候选：144 张图像审核通过、74 张拒绝、32 张待审。144 张入选 MCQ 选项审核均已 accept。M1–M4 的 C0/C1/C2 Pilot 和成员 1 的数据检查已完成，结论见 `reports/coco/member1_formal_freeze_check.md`。用户指令下已冻结共享底图清单并渲染 C0/C1/C2；产物与检查结果见 `reports/coco/member1_formal_render_check.md`。四模型 Formal 推理与正式指标已完成，见 `reports/coco/coco_c012_formal_report.md`；实际扣费仍待账户账单核对。成员 2 应使用同一冻结清单进行后续 C3 工作。COCO 原图、完整渲染 PNG 和 API 请求日志不在 Git 中；详见 `reports/coco/member1_delivery.md`。API 密钥由实验人员自行配置。运行环境按计划使用 Python 3.10+ 与 `pip install -r requirements.txt`。
