# H3 官方提示词规范 · 一页纸（2026-08-25）

> 来源：`reference/official/VIDEO_PROMPT_WRITING_GUIDE_base_en.md`（MiniMaxAI/MiniMax-H3 仓库 docs/）。
> 这份规范我们 2026-08-24 调研时记下了"官方 schema vs 自由文本，锐度方差 26→367"，**却一直没读**。
> 威逼场三天里的三个病（乱码人声 / 烧字幕 / 静默镜嘴动），每一个都对应规范里我们违反的一条。
> 黄佬原话："三个问题其实是提示词控制不好造成的，根本不是音画同出本身的问题。我们对提示词的控制极其的弱。" —— 对。

## 结构（必须逐字）

```
<首行对齐指令>            ← I2VA / FL2VA 各有固定句，见下
<空一行>
integrated_multimodal_description: [Shot 1] <风格>, <首帧锚定> ... <动作时间线，台词嵌在里面>
<空一行>
overall_soundscape: <1–4 句英文：环境声/动作声/非语言人声，不复述台词>
<空一行>
non_diegetic_music: <配器/速度/动态；没有写 N/A>
```

| 任务 | 首行固定句 |
|---|---|
| I2VA | `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` |
| FL2VA | `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the S.SS-second mark of the target video.`（S.SS = 帧数/24，两位小数） |

## 语言（这是我们烧字幕/念舞台指示的根子）

- **正文全英文**。只有三样保留原文：`<d>` 里的台词、歌词、画面里真实可见的文字。
- **中文只能出现在 `<d>[Chinese] …</d>` 里**。`<d>` 之外出现任何中文 = 违规（模型会把它当要念/要显示的内容）。
- 画面可见文字（招牌/字条）用**英文双引号**原样引用 —— 所以「」中文引号不是任何官方语法，模型只能瞎猜它是台词还是要显示的字。
- 编译器 `scripts/h3_prompt_compiler.py` 对"`<d>` 外有中文"直接 `ValueError`。

## 台词与说话人（这是乱码人声的根子）

- 台词：`<d>[Chinese] 逐字原文</d>`，一个标点都不改；句末 `。？！` 之一；去省略号/装饰标点。
- 说话人：稳定编号 `(S1)` `(S2)`，第一次出现给足身份+音色+语速；**身份/语气写在 `<d>` 外面**。
- **不出声的人不给编号。** 静默镜 = 没有任何 `(Sx)`、没有 `<d>`。
- 画外音：`says in an off-screen voiceover: <d>…</d> while his lips remain completely closed.` —— **`lips remain completely closed` 是官方唯一的"闭嘴"句式**，静默镜借用它。
- 台词跨切：`<scenetrans>`；被片尾截断：`<cutoff>`。
- 台词密度不再是硬规则：A 组实测（3 字台词配 10 秒镜）官方格式下不再乱码填空，念完就安静。短台词配长镜仍然会让画面"空"，那是导演问题，不是模型问题。

## 镜头与运镜

- `[Shot 1]` 无时间戳；后续 `[Shot 2] At 00:03.500, the camera cuts to ...`（严格递增，落在时长内）。**一次生成可以多镜**——对应《黄果》"中位 3.2 秒短镜"节奏，不必一镜一生成。
- 运镜写成自然英文动作句：`The camera pushes in with small amplitude at slow speed toward ...`。词表：Zoom/Push/Pull/Pan/Truck/Tilt/Pedestal/Arc/Tracking/Static/Shake/POV/Roll + `with small|large amplitude` + `at slow|fast speed`。
- 只是改距离/微调角度 → 用运镜，不要切镜。

## 我们的三个病 ↔ 规范条款

| 病 | 违反的条款 | 规范写法 |
|---|---|---|
| 乱码人声、"不是普通话" | 台词没进 `<d>`、没有 `(S1)`，模型不知道哪句是台词 | `The young woman with a soft, trembling voice (S1) pleads: <d>[Chinese] 使不得。</d>` |
| 烧字幕、中文舞台指示被念 | `<d>` 之外有中文 | 正文全英文 |
| 静默镜嘴动/瞎发声 | 自由文本求"别动嘴"，没有官方句式；给了情绪词却没锁嘴 | 无 `(Sx)`、无 `<d>`，`... remains silent throughout the shot, and her lips remain completely closed.`，soundscape 只写环境声 |

## 用法

```python
from h3_prompt_compiler import compile_i2va, compile_fl2va, Line, density
p = compile_i2va(style="Live-action, cinematic", anchor="a close-up frames the young woman ... shown in <Picture 1> ...",
                 beats=["She lifts her gaze ...", "She lowers her eyes and closes her lips as the line ends"],
                 lines=[Line("S1", "The young woman with a soft, trembling voice", "asks", "官人这话是什么意思，妾身实在听不明白。")],
                 soundscape="Quiet indoor room tone with a faint candle flicker continues throughout ...")
```

## 验证记录（2026-08-25 对照实验，同母图同 seed 只换格式）

| 镜 | 旧写法（自由文本+「」） | 官方格式（seed 1001 / 2002） |
|---|---|---|
| A k09 短台词「使不得。」243帧 | 满屏乱码"穆丽清哈病损…" | 只念「使不得」，其余 9 秒安静，零字幕 |
| B k02 惊惶母图静默 124帧 | 4 次都张嘴发声/烧字 | 嘴全程闭着、真静音、零字幕 |
| C k02 对白特写 124帧 | 4/4 烧字幕 | 台词清晰、嘴动对得上、零字幕 |

**6/6 过。结论：三个病的真根因是 prompt 格式，不是音画同出。** "台词密度≥1.5"、"静态镜用 Ken Burns"、"换 seed 抽卡"降级为格式错误时代的补丁，不再作为主规则。
证据：`/home/admin01/ab_matrix_0808/{A,B,C}_*_official_s{1001,2002}.mp4`，抽帧条 `/tmp/abo/*.png`。
