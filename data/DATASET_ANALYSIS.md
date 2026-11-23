# 数据下载、结构核验和使用说明

范围以 [Project_Proposal.pdf](../Project_Proposal.pdf) 与根目录两份项目文档为准。COCO 和 Multimodal-Mind2Web 是主实验的原始数据；SCAM 是静态标签误导的补充对照。本页保留首轮数据核验记录；COCO 的后续完整下载与受控筛选以 [最新 COCO 审计](../reports/coco/README.md) 为准。

## 本地文件与规模

| 数据 | 目录 | 数据规模与验证方式 |
|---|---|---|
| COCO val2017 | 本机 `raw/coco/` | 官方标注 ZIP 252,907,541 字节；完整图片 ZIP 815,585,330 字节已下载并校验、解压 5,000 图。实测 5,000 图、36,781 个实例、80 类。后续筛选得到 200 张候选，见最新 COCO 审计。 |
| Multimodal-Mind2Web | [mind2web](raw/mind2web/) | 固定 HF revision 1b4c6a8cf9f77b7a5e0d641959935c80c4a05889。目标 split 为 test_task，共 5 个 Parquet 分片、1,277,260,247 字节。官方数据卡列 1,339 步、177 个任务。首分片已解码，另存 [10 张截图预览](audit/mind2web_preview/)。test_website 与 test_domain 保留为独立扩展，需另下载。 |
| SCAM | [scam](raw/scam/) | 92,160,377 字节的 ZIP 已落盘。实测 3,486 张图，SCAM／NoSCAM／SynthSCAM 各 1,162 张，另有一个 3,486 行的 metadata.jsonl。补充 COCO 的 C2 分析，不计入 COCO 样本。 |

来源：[COCO 官方下载](https://github.com/cocodataset/cocodataset.github.io/blob/master/dataset/download.htm) · [Mind2Web 数据卡](https://huggingface.co/datasets/osunlp/Multimodal-Mind2Web) · [Mind2Web 固定版本](https://huggingface.co/datasets/osunlp/Multimodal-Mind2Web/tree/1b4c6a8cf9f77b7a5e0d641959935c80c4a05889/data) · [SCAM 数据卡](https://huggingface.co/datasets/BLISS-e-V/SCAM)

下载后可以在本项目目录运行下列命令复核。下载脚本检查文件长度和每段 Content-Range。验收以原始数据能打开、文件数量符合预期和审计结果为准。

[本地审计 JSON](audit/inspection.json) 记录实际打开的分片、字段和计数。[GUI 候选索引](audit/mind2web_clean_candidates.jsonl) 记录首分片中可解码且至少一个正候选框完整位于图片内的 190 个 CLICK 步，来自 35 个任务。截图已经导出到 [GUI 原始截图](audit/mind2web_clean_images/)，索引包含相对 JPEG 路径、任务及步骤 ID 和候选框。它只做几何初筛，尚待人工核对目标对齐。

当前已核验 COCO 全部 5,000 张验证图、Mind2Web 首分片及导出的 190 张截图、SCAM 完整 ZIP。Mind2Web 其余四个 test_task 分片仍有未完成的分段，不能按全量数据引用。

网络不稳定时可以按文件指定下载目标。`python data/audit/download_public.py mind2web` 只补齐 test_task。COCO 的 `python data/audit/stage_coco.py` 按已下载的标注保留一个可独立使用的候选池，逐张解码核对尺寸，样本未经人工确认。原始 ZIP 和候选池并存时按同一个 COCO image_id 去重。

```powershell
Set-Location 'D:/code/assignment/vlm'
python data/audit/download_public.py
$env:PYTHONPATH=(Resolve-Path 'data/.audit_deps').Path
python data/audit/inspect_downloads.py
```

## COCO 怎么用

- `images[]` 有原图 ID、文件名、尺寸与许可，`annotations[]` 通过 `image_id` 关联，`categories[]` 将 category_id 映射到类名。bbox 为原图像素坐标 `[x,y,width,height]`，annotation area 通常反映实例 mask 的面积。统计用于提名候选，不应用来自动判断画面主对象。
- 按原 proposal 从候选池取约 300 张，先固定随机种子和类别分布，再人工复核主体。预试验和正式实验按原图 ID 切分。同一原图派生的所有条件应始终留在同一 split。用原图固定任务、四选项及顺序，在所有配对条件复用；记录背景文字、候选类别是否实际出现在图里和图像许可。
- **C0** 用原图生成干净物体识别题，需要新增题目、选项和主对象真值。**C1** 由原图制作普通中性文字对照，并标注 OCR 参考文本和遮挡比例。**C2** 评估非指令性的错误类别标签对物体选择的影响，SCAM 的同 ID 三种现成变体可以独立用于这部分外部核验。COCO 上仍需使用同图匹配的样本。给 C1/C2 记录同一格式的文字属性和图像变换，方便检查视觉干扰与语义冲突。
- **C3** 是原 proposal 的独立指令条件。COCO 没有这类标签或专门的真值。其评估需要独立、固定且有依据的样本与结果标签，并保持与同一基础样本的配对关系。仅使用 C0/C1/C2 得到的是物体识别与文字干扰结果，覆盖不了 C3。

## Mind2Web 怎么用

- Parquet 每行是**一个标注动作**。关联键用 `annotation_id`（任务）和 `action_uid`（步骤）。`confirmed_task` 是任务，`screenshot` 是视觉观察，`operation` 给动作类型，`pos_candidates` 给真值候选，`neg_candidates` 给备选元素。`raw_html`、`cleaned_html` 用于本地核验，`action_reprs`、`target_action_index` 与 `target_action_reprs` 辅助确定历史和当前步骤。
- 本地首个分片的 `operation` 为字符串，`pos_candidates` / `neg_candidates` 为字符串列表，候选的 `attributes` 需再解码。`screenshot` 是 `{bytes: binary, path: string}`，图片字节内嵌在 Parquet。bbox 示例为逗号分隔的 `x,y,w,h` 字符串。首分片 268 步、36 个任务、26 个站点，214 个 CLICK 中 190 个有正候选并带 bbox 字段，24 个正候选为空。字段存在只够初筛，需核对是否为有效的文档或视口坐标，以及与截图尺寸、滚动偏移和裁剪的对应。已解码的一张截图为 JPEG 1280×4171，长截图对视口和 OCR 很关键。
- 做原 proposal 的 **A0** 时，优先筛 CLICK、截图可解码、合法目标看得见的步。用候选元数据提出参考框，人工核对，记录排除原因。框和任务编号进入视觉动作预测的输入，候选文字、DOM 与真值留在评分侧。先固定约 30 步 pilot，再从不同任务/网站挑约 150 个符合规则的正式步骤。若源集合达不到要求，报告筛选人数与原因。
- **A1** 是匹配的中性视觉对照。需要单独保存中性对照图与候选映射，再核对合法目标、视口和候选 ID 对应关系。**A2** 需要额外的指令条件样本与单步结果标注，原数据集不给这一条件。Read、Plan、Act 的结果要通过同一个基础步骤 ID 关联，既有任务历史和评分真值不可混入观测内容。
- 网页部分输出为离线的元素选择和评分。Mind2Web 的 1,339 是数据行数，不代表 1,339 条可直接用的视觉 CLICK 样本。应先计 CLICK、缺少正候选、缺失或无效 bbox，以及截图与框人工核对的通过率，再报告最终可用数。

## 直接使用和改造的边界

- **可直接复用**：COCO 原图和物体实例标注，Mind2Web 公开截图、正常任务和动作标注，SCAM 的标签误导及干净对照。
- **需加工**：静态 MCQ 与显式主体标签、同图配对、OCR 参考、GUI 元素位置映射和历史截取、把防御条件映射回同一图片或步骤。原始字节与改造后的样本分目录，保留基样本 ID、来源 revision、处理版本、支持的 RQ 和排除原因。复用样本检查同一 base_id 的用户任务和合法标注是否稳定。
- **需要单列的缺口**：C3 与 A2 属于视觉指令条件；原始数据集不包含对应的成对图像和结果标签，需要按项目方案构造、审核并单列来源和版本。

SCAM 的 `metadata.jsonl` 包含 file_name、type、object_label、attack_word、postit_area_pct 和 id。实测 id 带版本前缀，例如 `SCAM_img_0001`，去掉 `SCAM_`、`NoSCAM_` 或 `SynthSCAM_` 后用 `img_0001` 对齐。实测 1,162 个组各有三行，覆盖 660 个物体标签和 206 个贴纸词。该数据可用于估计错误标签对分类的影响。C3 或 A2 的指令服从需要独立真值。
