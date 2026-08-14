# H3 提示词纪律 + 画面连贯（2026-08-09 实证，黄佬逐条逼出来）

这份是做 H3 剧情片的两条命脉：**画面靠母图派生连贯，声音靠 T8 原声 + prompt 明确性**。

## 〇、人物一致性 = 角色 bible，每张母图强制复述（漏了就换人）

**踩坑**：出母图时只写了空间锚（房间/床/窗/烛台），忘了人物锚 → 交欢母图里男主直接变成没网巾、没胡须的年轻人，跟前面戴网巾有须的中年商贾对不上。

**规矩**：先定义角色 bible，**每一张母图 prompt 里逐字复述，一张都不许省**：

```python
MAN   = ("a 35-year-old Ming-dynasty merchant man: hair fully gathered up under a BLACK GAUZE HAIRNET (wangjin), "
         "a SHORT BLACK BEARD and moustache, thick eyebrows, broad shoulders, mature masculine face")
WOMAN = ("a 25-year-old woman: oval face, willow brows, phoenix eyes, full red lips, porcelain pale skin, "
         "long straight black hair parted in the middle")
```

- 裸戏尤其容易丢特征（模型倾向画年轻裸男）→ 交欢母图里要**再强调一次** `his black gauze hairnet and short beard still clearly visible`。
- 更强的锁：Krea i2i 从角色主图派生（VAEEncode 原图 + denoise 0.42），脸最稳。
- **三重锚缺一不可**：人物 bible + 空间锚 + 同 seed 族。

## 一、画面连贯 = 导演统一母图派生多景别（已验证成功）

**病根**：零散现成图各拍各的 → 拼起来 shot 之间跳，像"会动的照片"，不是电影。

**解法**：一场戏先出**一张高分辨率场景母图**（定死空间/站位/机位/光线），再从**同一张母图裁切**派生多景别：

```bash
# 母图 1088×1920（Krea），裁出 480×864（必须被 32 整除，否则 H3 报错）
ffmpeg -i MASTER.png -vf "scale=486:864,crop=480:864:3:0"        wide.png   # 全景
ffmpeg -i MASTER.png -vf "crop=680:1224:200:632,scale=480:864"   mid.png    # 双人中景
ffmpeg -i MASTER.png -vf "crop=460:828:45:720,scale=480:864"     left.png   # 左侧人物特写
ffmpeg -i MASTER.png -vf "crop=460:828:585:720,scale=480:864"    right.png  # 右侧人物特写
```

为什么这样就连贯：同一母图裁的 → **视线天然匹配**（左边人物看右、右边人物看左，正反打自动成立）、**空间/站位/光线绝对一致**、机位不越轴。

**跨场也要连贯**：同一场景的不同阶段（登场/宽衣/交欢/余韵），用**完全相同的空间描述前缀 + 同 seed 族**生成各自母图 → 房间、床、窗、烛台、地毯位置一致。空间描述示例见本文件末。

**站位纪律**：全片同一人固定在同一侧（如男左女右），别越轴。

## 二、声音 = T8 原声（禁外部配音）

见 [`nsfw-profile.md`](nsfw-profile.md) 与 T8 装配。核心：`MiniMaxH3MultiRateSamplerEXPT8` **video_steps=4（快）/ audio_steps=8（清晰）**。turbo 一刀切 4 步会把音频糊成噪声。

## 三、提示词语言（2026-08-12 更新）

### 3.0 【硬规则】画面/动作 prompt 一律中文

**黄佬原话**：「不要用英文写提示词了，现在都是中文提示词更强！！！」

- H3 视频 prompt、Qwen 母图 prompt、分镜动作描述 → **默认整段中文**
- **禁止**再写整段英文流水（含旧 HMNSFW 英文八段式主文）
- 体位用中文写清楚（「后入式」「女上位」「正常位」），**禁止**裸写英文 `doggy`（会生成真狗）

### 3.1 中文副作用：H3 仍可能把部分中文句子念出来 / 烧字幕

**2026-08-09 实证仍有效**：H3 不理解"约束"，可能把 prompt 里的中文当台词念，或烧进画面。

| 写法 | 结果 |
|---|---|
| 画面动作/场景用中文细写 | **优先**（更强） |
| 对白：`他说道：「…」` | 要中文声时用；台词镜多 seed 抽帧防字幕 |
| 单独写 `Audio: 烛火轻响…` | 易被念出来 ✗ → **默认不写 Audio 行** |
| 无台词镜母图闭嘴 + 不写「」 | 降低乱说话 |

### 硬规矩（中文主文 + 音频安全）

| 镜头 | 怎么写 |
|---|---|
| **有台词** | 中文画面描述 + `他说道：「…」` / `她说道：「…」`；**不要**另写 Audio 行；出片多 seed 抽无字幕 |
| **无台词** | 中文画面描述 + 母图闭嘴；**不要**写「全程无人声」这类中文禁声句 |
| **合戏** | 中文写体位与动作 +「全身赤裸，男仅网巾短须」+「仅两位成年人类，无动物」 |
| **绝对禁止** | 整段英文主 prompt；裸词 `doggy`；中文 Audio 环境音描述行 |

**台词长度**配时长（约 5s ≈ 20 字较稳）。

**出片必听 + 台词镜必抽帧查字。**

## 四、工程坑

- **Krea(8188) 与 H3(8190) 共享显存**：切换前必须 `POST /free`，否则 OOM。
- **宽高必须被 32 整除**（854 会报错，用 864）。
- **帧数落 17k+5 网格**（124 等）。
- **经跳板的 scp 在 GPU 忙时易断**（文件没传上却以为在跑）：用 `rsync --partial` + ControlMaster，启动后**必须 `pgrep` 确认进程存在**。
- 盒上跑脚本用 `setsid ... < /dev/null &`，否则 ssh 断连会带走进程。

## 附：同空间描述模板（金瓶梅卧房）

```
in the same warm candlelit Ming-dynasty bedchamber: a red lacquer canopy bed with white gauze curtains,
carved lattice windows behind, a bronze candlestick casting warm light, a patterned carpet on the floor,
red lacquer furniture. cinematic photoreal, film grain
```


## 五、合戏母图定稿（2026-08-12 黄佬确认真实）

**刀斧手主路径 + 中文真实交欢写法**，详见项目 `INTENT.md`「合戏母图定稿方法」。

口诀：Krea2刀斧手 → S5 master → i2i 改姿；中文写正在发生；半身暗光不对镜头；禁瓷白、禁 doggy、禁第三人。
