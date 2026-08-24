# H3 提速/提质全网调研（2026-08-24，三路并行：X/TikHub + GitHub/社区 + 模型货架）

> 基线：4090 48G / int8 pruned convrot / turbo 4步 / T8 音频8步 / Sage 开 / **5秒片≈95秒** / 768p 上限。
> 结论先行：基线在社区已属第一梯队（有 4090 用户裸跑 8 分钟），但有一个**已在我们盒上验证的 2 倍级根因**和一堆免费升级没吃。

---

## A. 头号发现（已在盒上验证）：cu128 把优化算子整个禁了

- `comfy/quant_ops.py`：`cuda_version < (13,) → ck.registry.disable("cuda")`。我们 torch 2.11.0+**cu128** → comfy_kitchen CUDA 后端 `disabled: True`，**int8_convrot 全程模拟路径**。
- 官方 README 原话："prefer int8_convrot if you can use pytorch with cu130"。社区实测（4060Ti，20步）：升 cu130 后 12:50 → 5:55（**2.17x**）。
- 修法：H3 .venv 升 `torch --index-url .../whl/cu130`。
- **风险**：该 venv 同时服务 krea2.service；sageattention 是编译包，torch 升级后要重装/重编；升级前必须 `pip freeze` 快照 + venv 备份，失败可回滚。
- 替代（不升 torch）：`--enable-triton-backend` 只覆盖部分算子，**convrot 专用 kernel 不在 triton 列表里**，治不了本。
- 备选：fp8_scaled 权重在 cu128 下反而比模拟 int8 快 1.38x（Pedro 4090 实测）——若 cu130 升级受阻可退这条。

## B. 免费升级堆（低风险，逐项吃）

| 项 | 内容 | 来源 |
|---|---|---|
| **T8 v1.45**（今天刚发） | 8步学习型两遍音频（MultiRateSampler 的下一代）+ 音频时钟 bug 修复 + FETA 动作增强 + 长视频 latent 拼接 + NFE 断点续跑 | github.com/T8mars/comfyui-minimax-h3-audio-T8 |
| **ComfyUI 升 master** | ①special tokens 质量修复（8/22）②**prompt embeddings**：`embedding:` 语法加载预计算文本嵌入，**整个跳过 32B 编码器**（14.6G 显存大头+编码耗时归零；我们大量重复模板 prompt，收益直接） | comfyanonymous/ComfyUI #15697 #15808 |
| **lightx2v turbo v1.1**（08-20） | 我们在用 v0.1；v1.1 是 768p 正式训练版（强度 1.0），另有 8step 版 | HF lightx2v/Minimax-h3-Turbo |
| **ref2va 专用 turbo v0.1**（08-13） | 首个 ref2va 原生蒸馏——此前拿 fl2v turbo 凑合 | 同上 + Comfy-Org 转档 |
| **Kijai pruned turbo 307MB** | 结构化剪枝版 turbo，声称**消除音频"电子味"机械噪声** | HF Kijai/MiniMax-H3_comfy |
| **Motion Booster V0.2 + ref2va 版**（08-19） | 新触发词 `dynv2`；V0.1 直接升级 | civitai 2840146 |
| **NaughtyTimes v2 pruned r128**（08-09） | 作者原话"pruned 底座用错版本等于没挂"——**我们旧版可能一直没生效** | civitai |
| **HM 单件套**（08-08 后新路线） | HMPussy/HMPenis v2/HMCumshot/HMInnie/HMBreasts，与 AIO V2 叠加；HF 镜像 Hearmeman/minimax-h3-loras 可 wget | civitai/HF |
| **moawxx**（08-14） | 女声呻吟+身体反应 LoRA，0.6-0.85（1.0 伤画质）——NSFW 音频最实用 | civitai 2857965 |
| **官方特效 embeddings**（08-22） | bullet_time/kiss_camera 等 10 个，小体积顺手下 | Comfy-Org/MiniMax-H3 |
| **结构化 prompt schema** | 同种子锐度方差 26.0 → **367.6**（官方 schema vs 自由文本）——最大的免费质量项；guide 在模型仓库 docs/ | Pedro 实测 |
| 稳定性两则 | 重任务关 dynamic VRAM（官方已知 bug）；`--disable-pinned-memory` 系统 RAM 45G→6G 零代价 | r/comfyui 官方帖 |

## C. 破 768p → 本地 2K（多人独立验证）

**两段式 latent upscale**（社区当前最优解）：
1. 低清一遍（~0.5MP，如 736×416 或 736×1280）
2. **LBH-123-AI/Minimax_h3_latent_Upscaler**（24通道 latent 直接 3D 上采样 1.5-2x，跳过 VAE 往返）
3. refine 遍 **8 步 denoise 0.5**（实测 8 步比 20 步更清）
- **三个坑（都有人踩过）**：①conditioning 必须按放大后分辨率重挂 ②refine 遍可挂 ref2v turbo 4步省时 ③**上采样会微妙改变音频→把上采样前的原音轨压回去**
- R2V 版加参考锚定（refine 遍把同组参考图再喂一遍）→ 人物一致性保持，避免 SeedVR2 塑料脸
- 数据点：416×736→1120×1984 细节反增；5090 2K 5秒共 353s；T8 v1.45 自带 13-latent-upscale 工作流（T8 原生版）
- 长片工程版：bbaudio-2025/Comfyui-MMH3-UltimateUpscale（分块+音频原样透传）
- 外部 VSR 结论：0.4MP 源直放 2K"无理"；1.3MP 源可放；SeedVR2 收益边际；**别从 480×864 直接外部放大**

## D. 值得 A/B 的（有数据但需自测）

| 项 | 声称 | 注意 |
|---|---|---|
| **Sol-Attn 替换 Sage**（Saganaki22/kijai 版） | 5090 上 vs Sage 1.4-2.3x；与 turbo/int8_convrot 兼容实测过；附带 Fused Modulation(1.2-1.9x, bit-exact) + Chunk FF(MLP 显存-37%) | SM89(4090) 只有冒烟无基准；需 Triton 3.6；与 KJ Low VRAM Attention 互斥 |
| **AudioRefine**（Adudeguyman） | 视频4步后**冻结视频流只补音频4-6步**（denoise 0.5），与 T8 思路不同、与一切正交 | 跟 T8 8步/learned two-pass 三方 A/B |
| **FastH3 DMD2 LoRA**（drozbay 提取 pruned 专用 rank128, 1.33G） | FastVideo 官方 DMD2 蒸馏，唯一非 lightx2v 系正经路线 | 还是 preview（训练 2900/4000 步） |
| **fl2va×ref2va Hybrid b20/b25**（smhfacct） | ref2va 有已知训练质量缺陷；hybrid 保留参考能力找回 fl2va 画质音质 | 我们若嫌 ref2va 糊，这是对症药 |
| **turbo 当调味料** | turbo 强度 0.1 + 50 步：人物融化缓解且不压动作（质量模式邪道） | 单人报告 |
| res_multistep/simple 采样器 | 8步下比 euler/beta 快 13% | |
| DaSiWa v1.0 / 10Eros-Max beta2 | NSFW 底模换代候选（DaSiWa 宣称声音/人声更好，有 t8star 4步 turbo 合并版；10Eros 有 int8_convrot 镜像） | 换底模是大动作，P2 后再评 |
| ClipProj 4B/8B 编码器桥（T8） | 换掉 32B 编码器省 14.6G；单种子盲测"全维 tie" | 样本量极小；8B 在 Ref2VA 身份不稳；prompt embeddings 方案可能更干净 |

## E. 死路确认（别再花时间）

- **cache 类×4步蒸馏 = 无效**（社区共识+我们实测一致）：EasyCache 音频变瘦、FBC 违背运动指令、Spectrum 4步没得跳（20步档才有 30-45%）；TeaCache 仅 20 步档 3x
- **SageAttention 3**：面向 Blackwell FP4，无 H3/4090 证据——我们的 Sage 已是该线终点
- **torch.compile**：无任何 H3 实测
- **STA/SVG/PAB**：无 H3 移植；稀疏注意力生态里有实测的只有 Sol-Attn
- **Turbo-SLA**：需 LightX2V 推理栈，ComfyUI 吃不下（T8 侧仅机械验证无 claim）；观望
- **T8 的 SPEED 节点**：仓库自测更慢，"research only"
- **SLA 系 4 步**：音频变噪声，6 步才是实用线
- 官方动态：**无 H3.5/H4**；API 无升级（8/20 只是 5 折促销）；AMA 提到官方 2K regenerate 模型 "not very far"——观察
- 合规注：H3 Community License 适用区明文排除美/欧/英/韩

## 推荐执行顺序

1. **cu130 升级**（快照+备份后干；预期 ~2x，95s→~50s 量级）→ 复测 t8_i2v_warm.py
2. **免费堆**：T8 v1.45 + ComfyUI master + LoRA 五连（v1.1/ref2va turbo/Booster V0.2/NaughtyTimes v2 pruned/Kijai 307M）+ prompt schema 落进出片脚本
3. **A/B 三连**：音频（T8-8步 vs learned two-pass vs AudioRefine）、注意力（Sage vs Sol-Attn）、蒸馏（lightx2v v1.1 vs FastH3 vs larryvrh v4）
4. **2K 管线**：latent upscaler 两段式接进产线（终稿精修档）
5. P2 后评估：hybrid 权重 / NSFW 底模换代 / 编码器替换

原始底料：三个 agent 报告全文见本次会话；civitai/HF 扫描数据在 scratchpad（civ_rank.txt 等）。
