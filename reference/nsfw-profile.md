# NSFW Profile（P2）— 成人片模式

h3-film-studio 电影/剧情/成人合一，NSFW 走这个 profile。普通片不加即可。

## 三处开关

1. **视频 LoRA 栈**（`providers.yaml` → `models.video.local_h3.loras`）
   - **合戏/动作段（强制）**：`[["HMNSFW_AIO_V2.safetensors", 0.5], ["H3_Motion_Booster.safetensors", 0.6]]`（+ turbo 可叠）。**禁止**为「真实/克制」拆掉 Booster——那会造成慢动作/粘帧；克制只改 prompt 节奏词。
   - **文戏/铺垫段**：`[["HMNSFW_AIO_V2.safetensors", 0.35]]` **无 Booster**（走路/接吻/对峙挂 Booster 会抽搐）
   - **解衣过渡**：默认无 Booster；若用户明确要求「动作感」可轻度 0.35–0.45，并抽帧防抽搐
   - 触发词：Booster 按运动轴 `dynvt1`（垂直/骑乘/女上）/ `dynfb1`（前后/后入）写进 prompt 段首
   - **motion_mean 验收**：合戏 &lt;2.8 必须重出；目标 3.5–5.5（金瓶梅实证 3.6–6.3）
2. **图片 LoRA**（`local_krea.lora`）：`krea2_lora 通行证刀斧手版.safetensors` @ 0.5（NSFW 静帧通行证）
3. **prompt 规范**：合戏段走 register 八段式（见 [`hmnsfw-register.md`](hmnsfw-register.md)），文戏段走详尽正向描写

### 用户纠正记录（必须遵守）

- 2026-08-29：**「为什么不挂 booster？这个明明是动作的！」** → 动作/合戏镜强制 Booster，不得再砍。

## 身份锁（治男相漂移的关键）

- **用同批出的静帧**（如金瓶梅 v3 系列 C/D/M）——身份从源头连贯，i2v 忠于静帧
- 每句合戏 prompt 复述男主造型锁：`hair fully gathered under a black gauze hairnet, short black beard, muscular Ming-dynasty merchant, masculine jaw`
- 女主 face-block 全片同名复述
- 配合 xyz 的 `consistency_anchors` / `subject_constraints`（storyboard 字段）双保险

## 音频

见 [`audio-track.md`](audio-track.md)。四层：H3 自带合戏人声（**禁 mute**）+ CosyVoice3 旁白（mouth-closed，`POST 127.0.0.1:8001/tts`，voiceId=`cosyvoice3-female-anchor`，instruct 可加情感）+ 夜景 Foley + BGM。

## 已验证（2026-08-09《金瓶梅·夜宴》62s）

- v3 自洽批次 12 段（4 铺垫 + 7 硬核合戏 + 1 收尾），全 turbo 4 步、80s/段
- 合戏 motion 3.6–6.3（register + Booster 起效），**男主全程阳刚不漂移**（金莲夜候 K09 漂移根治）
- 硬核体位真实（骑乘/后入/立姿），无畸形手
- 四层音频三层落地（旁白 + H3 喘息 + Foley），音画对齐
- 跑批脚本 `v3_run.py`（scratchpad）；成片 `~/Desktop/jinpingmei_i2v/final/jinpingmei_yeyan.mp4`

## 待深化

- content_filter：xyz 原 `content_filter.py` 会过滤 NSFW（商业广告用）；成人模式需 profile 开关翻转它。当前用独立跑批脚本绕过 xyz pipeline，未跑母模型编排的 story→framework→storyboard
- BGM：无古风音乐源，本次缺第四层（三层已远超无音频）
- r2v/fl2v 模式（多参考/尾帧）：`local_providers.video_h3` 当前只 i2v
