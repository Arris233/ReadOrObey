# 共享数据约定

- `raw/`：公开数据原件，下载后保留原文件名；本机存储，不进版本库。
- `manifests/`：人工审核并通过 Pilot 后冻结的样本定义。包括图 ID、相对路径、答案、注入目标、切分和版本哈希，供三人共同使用。
- `processed/coco_c012/`：成员 1 渲染的静态错标签与中性对照。
- `processed/coco_c3/`：成员 2 渲染的视觉指令。
- `processed/mind2web/`：成员 3 清洗与渲染的 Web Agent 步骤。

目前 COCO 的候选池与暂定切分在 `reports/coco/`，还没有冻结版本。
