# h3-film-studio — P1 交付说明

fork 自 [`huangserva/xyz-video-skill`](https://github.com/huangserva/xyz-video-skill)，把云端 Seedance 视频后端替换为**本地 MiniMax-H3 + Krea2（ComfyUI）**。目标：一个 skill 做电影 / 剧情 / 成人片（NSFW 走 profile）。

## 架构：四方融合

| 来源 | 贡献 |
|---|---|
| **xyz-video-skill 骨架** | 导演大脑（narrative 三层派生 / director_plan / 单向运动法则 / motion_control / continuity_mode / 单一真相源）+ 流水线（vision_judge / compose）+ **provider 抽象** |
| **MiniMax 官方 skill** | 六列镜头表的**音频对白轨** + self-check gate（P3 融入） |
| **本地 H3（2026-08 打通）** | i2v / r2v / fl2v 三模式 + LoRA 货架（HMNSFW/Booster/turbo）+ **自带音频**（生成引擎） |
| **adult-krea2-h3-narrative** | NSFW profile：Krea 刀斧手/HMNSFW 静帧 + register 八段式 + 男主造型/服装状态机（P2） |

**关键同构**：xyz 的 `video_references` 用途协议天然映射 H3 三模式——`first_frame`→i2v，`reference_character/prop/stage`→r2v，`reference_target_state`→fl2v。

## P1 已完成（接引擎）

- fork 骨架 + 去硬编码路径（`SKILL.md` name=`h3-film-studio`，openclaw 路径清零）
- **`scripts/local_providers.py`**：H3 i2v 视频 provider + Krea2 t2i 图片 provider，接本地 ComfyUI
- `video_gen.py` / `image_gen.py` 的 dispatch 接入 `local_h3` / `local_krea`（xyz 原逻辑不动，插件式加入）
- `config/providers.yaml`：默认后端切到本地 H3/Krea，云端 seedance/apimart 块保留备用
- `video_references` 用途协议映射 H3：P1 走 i2v（r2v/fl2v 见 P2）
- H3 自带音频**不再 mute 一扔**（`generate_audio: true`）
- 自检：`py_compile` + yaml 接线断言通过

## 怎么跑（需本地 ComfyUI）

```bash
# 隧道（Mac 侧）：H3=8190 Krea=8188
ssh -fN -o ExitOnForwardFailure=yes -L 18190:127.0.0.1:8190 -L 18188:127.0.0.1:8188 newgpu
```

`providers.yaml` 的 `local_h3.endpoint` / `local_krea.endpoint` 默认指隧道端口（18190/18188）；盒上直跑改 8190/8188。

## 待办

- **P1f 冒烟**：跑通一条普通剧情片，验证 story→framework→storyboard→本地生成→compose 端到端
- **P2 NSFW profile**：profile 开关翻转 `content_filter` + 挂 HMNSFW/Booster + prompt 走 register 八段式；Krea i2i（角色参考图锁身份）；r2v/fl2v 模式
- **P3 音频工程**：官方六列音频轨 + H3 自带人声 + CosyVoice3 旁白（mouth-closed）+ media-use Foley/BGM 混音（移植 adult skill 的 `references/audio-track.md`）
- **P4 金瓶梅重跑验证**：带 xyz 的 `subject_constraints`/`consistency_anchors`，治 K09 男相漂移
