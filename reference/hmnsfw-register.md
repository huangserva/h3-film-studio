# HMNSFW register + Booster 触发词（H3 视频 prompt 编译规范）

来源：HMNSFW AIO V2 作者公开的训练语料规范（civitai 2834417）+ Motion Booster（2840146）触发模板 + 2026-08-08 本机 A/B 实证（C 变体 motion mean 5.16，超历史最佳 r2v）。

**适用**：i2v/fl2v 合戏段的 `prompt_h3`。与 `h3-prompt-doctrine.md`（详尽正向>约束堆叠）同向，本文件更具体：给出词表和段落结构。两者冲突时以本文件为准（它对齐的是 LoRA 训练分布）。

## 硬规格

- **一整段流水文，200–270 词**（训练语料中位数 225）；不用列表、不用逗号堆 tag。短 prompt = 偏离分布。
- 语域：解剖直白的观察者描述。不写文学比喻、不评价好看不好看、不写画面外的情绪。**只写画面里有什么、在哪**。
- 触发词：`hmmotion` 放段首。叠 Booster 时再加运动轴 token（见下）。

## 八段固定顺序

1. **HEADER**（逗号分隔，先于一切散文）：`class, viewpoint, pace, shot`
   - class: `handjob / insertion / missionary / cowgirl / blowjob / doggy`（就叫 doggy；贴着未入=insertion 不是 missionary）
   - viewpoint: `pov` 或 `side`（第三人称）
   - pace: `fast` 或 `slow` —— 选一个，后文不许打架
   - shot: `close-up / medium shot / third-person side view / high-angle downward shot / low angle / wide shot`
2. **女方**：一两句——体型、肤色、发色发型、可见特征（雀斑/纹身/首饰/妆）、胸型、着装或全裸；然后姿势与朝向。**只写画面能看到的，不发明**。
3. **男方**（画内可见时）：相对位置、哪些部位入画。
4. **FRAME POSITION（最重要的一句，语料里密度最高）**：哪块解剖在画面哪个位置、谁前谁后、谁被遮挡。用语：`in the center of the frame / lower third / at the left / is the focal point / in the foreground / partially obscured by / enters the frame from`。
5. **解剖细节**（用白名单词）：只描述真实可见的；模糊就写模糊（`the penis is blurred and lacks clear anatomical detail due to fast motion` 是语料原话，比编细节安全）。
6. **运动**：开头 `The motion is ...`；什么在动、方向、节奏、接触形变（rim stretching / buttocks rippling / shaft skin bunching）。pace 词与 HEADER 一致：`fast / slow / rhythmic / steady / deliberate / forceful`。
7. **表面状态**（单独一句）：湿润/汗/体液，什么覆在什么上、怎么反光；默认名词 **sheen**。
8. **音频**（一句）：`The audio consists of ...` 或 `accompanied by ...`。

## 词表（按语料频次）

**用（男）**：penis(145) shaft(124) glans(93) corona ridge(40) urethral slit/opening(32) visible veins(35) circumcised(18) scrotum(7) foreskin(4)
**用（女）**：vulva(33) labia majora(19) anus(17) vagina(14) inner labia(13) clitoral hood(5) perineum(3)
**用（身体/表面）**：buttocks(54) breasts(31) thighs(23) sheen(53) wrinkles(27) pinkish glistening flushed taut textured
**禁（语料零次）**：cock, tits, ass, pussy, balls, testicles, nipples, areolas, mound, labia minora, clitoris（clitoral hood 可以）, veiny, swollen, genitalia, "the subject"

## Motion Booster 叠加

- 触发词按**起始帧的主运动轴**选：
  - `dynfb1` 前后往复（doggy / 站立 / 前倾）
  - `dynvt1` 垂直起落（cowgirl / reverse cowgirl / 弹跳）
- token 放段首（`dynvt1, hmmotion. cowgirl, ...`），运动段（第 6 段）换成 Booster 语言：`extremely fast, maximum-intensity vertical rising-and-dropping motion with zero build-up ... strong secondary motion and heavy follow-through on every stroke ... chest bouncing is strong, constant and highly visible`，收尾加 `Preserve stable anatomy, keep both figures clearly separated, keep the camera mostly steady.`
- 强度：内容 LoRA（HMNSFW **0.5** 或 SexGod 0.65）在前，Booster **0.7** 在后。
- Booster 音频会乱——无所谓，产线本来就 mute H3 原声统一铺底。

## 模式与采样

- **I2V 远好于 T2V**（作者原话 + 本机验证）；起始帧必须是 Krea2 出的干净双人图。
- 本机验证参数：`res_multistep / simple / 20 步 / cfg 1 / shift 12`（作者用 dpmpp_2m/Beta/20 on bf16 全量，本机 pruned int8 用上面这套已实证可行）。
- **默认工作档 = `--turbo`**（turbo LoRA 1.0 + 4 步）：80s/段，与 Booster 共存实证 motion **5.30**（反超 20 步档的 5.16），identity 稳、画质肉眼无差；20 步只留个别 beat 精修。8 步档 motion 5.95 但耗时同 20 步，不采用。

## 实证样例（2026-08-08 C 变体，motion 5.16）

```
integrated_multimodal_description: [Shot 1] dynvt1, hmmotion. cowgirl, side, fast, medium shot, third-person side view. Keep the characters, environment and composition of the first frame consistent. A slender young adult East Asian woman with long straight black hair straddles an adult man in cowgirl position on a Ming-dynasty canopy bed; both are fully nude. Her hands press on his upper chest with straight arms, his hands hold her hips; in the center of the frame her hips straddle his pelvis, the focal point, the point of penetration in the lower third of the frame partially obscured between her thighs. From the very first frame the two figures are already locked in extremely fast, maximum-intensity vertical rising-and-dropping motion with zero build-up. [...] Preserve stable anatomy, keep both figures clearly separated, keep the camera mostly steady. The audio consists of rapid rhythmic skin contact, her breathy moans, his low breathing, and the wooden bed frame creaking in rhythm.
```

## 运动尺子（本机 ffmpeg 刻度，`h3_i2v_shot.py` 自动输出）

`format=gray,tblend=difference,signalstats` 的逐帧 YAVG 均值：
- **0.25** = 死片（v4/v5 fl2v morph）
- **2.4–4.9** = 历史活片（r2v 雨林/浴室级）
- **≥3.5** = 合戏段过门线；**5+** = Booster 级
- **10** = 高速打斗上限（参考系）
