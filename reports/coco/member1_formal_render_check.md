# 成员 1：Formal 清单冻结与 C0/C1/C2 渲染

日期：2026-11-25。按用户“冻结并渲染”的指令执行。冻结前 `python -m src.render.select_coco --check` 返回 `valid: true`，12 Pilot / 120 Formal / 12 Reserve；暂定清单 SHA-256 为 `44c49ee991b2c3a4be9dd1192ec7483a9af9dcc2a1df8df036ec411479fbc4ba`，与冻结前检查记录一致。四模型 Pilot 证据见 `member1_formal_freeze_check.md`。

- 冻结清单：`data/manifests/coco_base_120.json`，132 条 Pilot/Formal 记录及 12 条 Reserve；SHA-256 为 `258132c4e96669dde32b72a4e4f6f6b41d371998f72477d01d1f2777ef32815e`。
- 主图索引：`data/manifests/coco_c012_manifest.jsonl`，660 张，其中 Formal 600 张（120 图 × 5 变体），Pilot 60 张。
- 消融索引：`data/manifests/coco_c2_ablation_manifest.jsonl`，132 张，其中 Formal 前 40 图 × 3 变体 = 120 张，Pilot 前 4 图 × 3 变体 = 12 张。
- 完整性：792 张 PNG 全部存在，尺寸均为 768×768，文件 SHA-256 均与索引一致。渲染器在保存时检查覆盖区域外像素不变。
- 目视抽检：`formal_c012_render_contact.jpg` 汇总了 15 张不同 Formal 底图，覆盖五种主图变体和三种消融变体；接触图中未见文字截断或中文乱码。16px 低对比字在缩略图上较难辨认，符合该变体设计。

这份记录只覆盖成员 1 的冻结与渲染。成员 2 应使用同一冻结清单开展 C3；这里不宣称其已完成独立交接确认或 C3 渲染。本记录形成时 Formal API 推理尚未执行；后续四模型正式结果见 `coco_c012_formal_report.md`。
