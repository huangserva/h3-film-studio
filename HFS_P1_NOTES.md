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
- **P1f 冒烟通过**（2026-08-09）：`video_h3` 经 xyz provider 契约驱动本地 H3 出片，普通剧情片（红袍女子走入院子，非 NSFW）124f/5.08s、**video+audio 双流**、turbo 4 步 ~80s。证明骨架→本地引擎→出片端到端通。

## 怎么跑（需本地 ComfyUI）

```bash
# 隧道（Mac 侧）：H3=8190 Krea=8188
ssh -fN -o ExitOnForwardFailure=yes -L 18190:127.0.0.1:8190 -L 18188:127.0.0.1:8188 newgpu
```

`providers.yaml` 的 `local_h3.endpoint` / `local_krea.endpoint` 默认指隧道端口（18190/18188）；盒上直跑改 8190/8188。

## P2/P3/P4 进展（2026-08-09，《金瓶梅·夜宴》62s 验证）

- **P2 NSFW profile** ✅ 见 [`reference/nsfw-profile.md`](reference/nsfw-profile.md)：LoRA 栈（合戏 HMNSFW 0.5+Booster 0.6，文戏轻）+ register 八段式（[`reference/hmnsfw-register.md`](reference/hmnsfw-register.md)）+ 身份锁。**男相漂移根治**（用 v3 自洽批次 + 男主造型复述）。
- **P3 音频工程** ✅ 见 [`reference/audio-track.md`](reference/audio-track.md)：四层三落地——H3 自带合戏人声 + CosyVoice3 旁白（mouth-closed）+ 夜景 Foley，音画对齐。BGM 缺源待加。
- **P4 金瓶梅重跑** ✅ v3 自洽批次 12 段，硬核合戏 motion 3.6–6.3，身份连贯，四层音频，62s 成片。

## 叙事成人片方法论（2026-08-09《金瓶梅·夜宴》119s 定版）

一部有戏的成人片 = 完整叙事 + 人物逻辑 + 表情博弈 + 对白，不是三段硬拼。**做叙事成人片先读 [`reference/narrative-adult-film.md`](reference/narrative-adult-film.md)**：六幕结构、金瓶梅欲擒故纵人物逻辑、i2v慢镜/fl2v表情戏/chain交欢的手法映射、对白配音、四层音频、工程坑。fl2v 表情戏 graph 见 [`scripts/fl2v_build.py`](scripts/fl2v_build.py)（微表情博弈 i2v 演不动0.3，fl2v 首尾差大补心理转变1.3-2.2）。定版 `~/Desktop/jinpingmei_i2v/final/jinpingmei_yeyan_full_v4.mp4`。

## 待办

- content_filter profile 开关（成人模式翻转 NSFW 过滤）；跑通母模型 story→framework→storyboard→compose 全 pipeline（当前用独立跑批脚本绕过）
- `local_providers.video_h3` 打开 r2v/fl2v 模式（多参考/尾帧）；Krea i2i 角色参考锁身份
- BGM 第四层音源；交欢段分块 chain 恢复体位变化
