# 音频工程（成片必做，不是事后补）

> 教训（2026-08-08 金莲夜候翻车）：把 H3 原声 mute 扔掉、只铺一层合成底噪 = 哑巴片。
> 成人叙事片的音频是半条命，尤其合戏段的喘息。音频必须**从分镜设计阶段就规划**（见 SKILL 六列镜头表的 Audio & Dialogue Track 列），不是画面拼完才想起来。
> 方法论移植自 MiniMax 官方 3d-animation-short 的六列镜头表 + 逐秒音频 cue + 口型纪律。

## 四层音轨（成片音频 = 四轨混音，缺一不可）

| 层 | 内容 | 工具（全现成） | 关键铁律 |
|----|------|------|------|
| **人声/喘息** | 合戏段呻吟、喘息、气声 | **H3 生成自带音频** | 合戏段 prompt 写 `breathy moans / rhythmic breath`，**H3 原声必须留下来用**，禁止 mute 一扔；从 seg.mp4 提音轨 |
| **旁白/说话** | 潘金莲视角情节叙述、内心独白 | **CosyVoice3**（4090 `POST 127.0.0.1:8001/tts`，`voiceId=qiuzhi2046-female`，见 [[cosyvoice3-4090-tts-api]]） | **画外音 = mouth-closed**，不对嘴不穿帮；这是"说话"的唯一可行解 |
| **环境/Foley** | 分场景：院外夜虫风、室内烛火噼啪、床榻吱呀、纱帐、脚步 | **media-use resolve**（音效库真 Foley） | 按场景分层，替代合成假底噪 |
| **音乐/BGM** | 古风箫/筝，低音量垫 | **media-use resolve**（音乐库） | 情绪垫底，别盖过人声 |

## 口型纪律（借官方，解 H3 对不上嘴）

- **画外旁白 → mouth-closed**：H3 静帧脸本就没有说话嘴型，旁白是画外音，完美契合。**默认走这条**。
- **角色开口对白 → mouth-open**：H3 对不上中文口型，会穿帮。**除非上 DUIX 数字人管线（[[ltx-duix-digital-human]]），否则不做角色对白，只做旁白**。
- 每一镜若有旁白/对白，在镜头表标 `narrator-mouth-closed: true`。

## 分镜表音频轨字段（每镜必填，见 SKILL 六列表第 6 列）

```
Audio & Dialogue Track:
  Narration:  旁白文本 + 时间码（如 0.0–3.0s「那夜，西门府的灯还亮着…」）| 无则省略
  Voice:      人声描述 + 时间码（合戏段：呻吟/喘息强度，如 0–5s 渐强喘息）
  SFX:        环境音效 + 时间码（如 烛火噼啪 全程 / 床榻吱呀 2–5s）
  BGM cue:    音乐情绪（如 箫，clandestine，pp）
  mouth:      narrator-mouth-closed: true（旁白镜必标）
```

## H3 原声提取

`h3_i2v_shot.py` 出的 mp4 **带 H3 生成的音轨**。
- 合戏段：提人声 `ffmpeg -i seg.mp4 -vn -c:a pcm_s16le voice_KXX.wav`，降噪后垫进人声层。
- 文戏段：H3 音多为无意义环境噪，弃用，改铺 media-use Foley。

## 混音（四轨对齐 + loudnorm）

层级：人声/旁白在**前景**，Foley 在**中景**，BGM 在**低垫**。

```bash
# 示意：旁白 + 合戏人声 + Foley + BGM → 混音 → loudnorm → 贴回画面
ffmpeg -i narration.wav -i voice.wav -i foley.wav -i bgm.wav \
  -filter_complex "[0:a]volume=1.0[n];[1:a]volume=0.9[v];[2:a]volume=0.5[f];[3:a]volume=0.28[b];\
  [n][v][f][b]amix=inputs=4:duration=longest:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]" \
  -map "[a]" mix.wav
ffmpeg -i video_mute.mp4 -i mix.wav -c:v copy -c:a aac -b:a 160k -shortest final.mp4
```

## 音频 self-check（进拼接前必过，借官方 Step 5.5）

- [ ] 每一镜的 Audio & Dialogue Track 四字段齐（Narration/Voice/SFX/BGM），无空镜漏音
- [ ] 合戏段 H3 人声已提取入轨，**没有被 mute 扔掉**
- [ ] 旁白镜标了 `mouth-closed`，没做对不上嘴的角色对白
- [ ] 逐秒无音频空档（每秒都有 cue，`silent` 也要显式写）
- [ ] 混音后人声清晰、BGM 不盖人声、loudnorm 达标

## H3 原声拼片规则（2026-09-03 买鸟记实测）

H3 每镜音频固有形状：t=0 一声瞬态（约 -30 dB）→ 约 0.25 s 死寂（-70 dB）→ 约 0.5 s 后人声起；镜尾环境声接近静音（-60 dB）；各镜综合响度可差 6 dB；动态范围仅 1.4–2.1 LU。硬切拼接会被人耳听成"跳闸"。

拼片必须：
1. 每镜裁掉开头 0.5 s（连画带声，母图静帧无信息）；镜尾死寂只留 0.4 s。
2. 用 ebur128 量每镜综合响度，按纯增益对齐到目标（-18 LUFS）；**不用 loudnorm**（它自带压缩，黄佬听得出"被压"）。
3. 切点做 0.4–0.5 s 音频交叉淡化，视频硬切。
4. 一切只用 H3 自己的音轨；不铺任何外部环境声（黄佬铁律）。
量化脚本思路见 `~/Desktop/mainiaoji_h3/work/`（lufs.json / trim_plan.json）。

- audio_steps 对照（s02 同 seed）：16 步比 8 步响 3.5 dB、4–8 kHz 高频多 3 dB，动态范围不变（1.9 vs 2.1 LU）。"被压"= 窄动态是 H3 本性，步数不改；用不用 16 步由黄佬耳朵定。
- 出片速度：本次 4090 被另一 session 手动起的 ComfyUI（非 systemd，h3.service 显示 inactive）共用队列，单镜从 135 s 拖到 1300+ s；不是配方问题。
