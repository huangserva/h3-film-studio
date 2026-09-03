# AGENTS.md — h3-film-studio

> 给 agent 的操作入口。**先读这份，再读 SKILL.md。**
> 本文件是「指令层」；真正拦你的是「强制层」(PreToolUse hook)，见文末。

---

## 0. 强制执行顺序（不许跳步）

```
① 读 INTENT.md          ← 用户意图的单一真相源（项目目录）
② 写/更新 shot_table.json  ← 姿态状态机（每镜 start/end/gen_mode）
③ preflight_continuity.py --strict-pose-change  → 必须 exit 0
④ 出母图                ← Qwen-Edit 参考图注入；人工核对姿态匹配 start/end
⑤ 出片                  ← 按 gen_mode：i2v / fl2v / chain
⑥ 交付前自检门          ← 字幕 / 人声 / 衔接，任一不过就返工
```

**跳过 ①②③ = 手搓 = 流程失败**，不管成片好不好看。
`reference/anti-handroll.md` 里有给用户的判据：交不出 `shot_table.json` + preflight 日志 = 不合格。

---

## 1. 环境

| 服务 | 地址 | 用途 |
|---|---|---|
| ComfyUI-H3 | `newgpu:8190` | 视频（i2v/fl2v/chain）+ T8 multi-rate 音频 |
| ComfyUI-Krea2 | `newgpu:8188` | 母图 + Qwen-Image-Edit-2511 身份锁 |

**显存秩序（2026-08-24 定版：H3 主人 / Krea 客人 / Qwen 已下架）**
- **H3 = 主人**：`h3.service` 常驻（lowvram + headroom 8 + Sage attention），长镜峰值 ~26.6G
- **Krea = 客人**：`krea2.service`（--lowvram，借 H3 venv），出图峰值 30.6G → **必须错峰**：出图一律走 `scripts/deploy/gpu_arbiter.py` 的 `krea_slot()`（等 H3 空闲 → 出图 → 自动 /free 归还）
- Qwen LLM 已 stop+disable（恢复：`systemctl --user start qwen38-q4-20g frpc-qwen38`）
- 状态一眼看：`ssh newgpu 'bash ~/gpu_status.sh'`；部署档案见 `scripts/deploy/README.md`
- 连接：`rsync + ssh ControlMaster`；盒上跑脚本用 `setsid ... < /dev/null &`，启动后 `pgrep` 确认

---

## 2. 命令

```bash
# 门禁（跑生成前必须 exit 0）
python3 ~/.claude/skills/h3-film-studio/scripts/preflight_continuity.py \
  --table <项目>/shot_table.json --strict-pose-change

# 身份锁出图（参考图注入，不是文字描述）
python3 ~/.claude/skills/h3-film-studio/scripts/qwen_edit_identity.py

# 出片
python3 ~/.claude/skills/h3-film-studio/scripts/h3_i2v_shot.py     # i2v
python3 ~/.claude/skills/h3-film-studio/scripts/fl2v_build.py      # fl2v 首尾帧
```

---

## 3. 硬规矩（违反必返工）

### 人物一致性
- **靠参考图注入**（Qwen-Image-Edit-2511），**不是**在 prompt 里复述角色描述
- 锚定参考图固定不换（如 `REF_XM.png` / `REF_PJ.png`）
- 文字锁不住衣服剪裁和脸几何 —— 每张图独立生成必飘

### 提示词（2026-08-25 定，优先级最高）
- **所有 H3 prompt 必须由 `scripts/h3_prompt_compiler.py` 生成**，禁止手写自由文本（三天血泪的真根因，见 `reference/h3-prompt-official-digest.md`）
- 台词只能在 `<d>[Chinese] …</d>` 里，说话人 `(S1)`；**`<d>` 之外一个中文字都不许有**
- 静默镜：不给 `(Sx)`，写官方句 `lips remain completely closed`，soundscape 只写环境声
- 官方原文：`reference/official/VIDEO_PROMPT_WRITING_GUIDE_{base,ref}_en.md`

### 音频
- **必须 H3 原生音画同出**（`audio_mode=native`），**禁止 TTS 外部配音**
- T8 multi-rate：`video_steps=4` / `audio_steps=8`（turbo 一刀切会糊音频）
- 中文只在 `<d>` 里（见上「提示词」节）
- **禁止合成噪声**（anoisesrc）冒充环境音

### 字幕
- **H3 绝不允许自己出字幕**，字幕一律后期
- 根因：**母图里人物张嘴 → H3 认定他在说话 → 自配乱码语音+字幕**
- 对策：无台词镜的母图必须**嘴唇紧闭**；出片后逐镜抽帧查字，有字换 seed

### 镜头与衔接
- **时长按内容定**（反应 71–124 / 对话 124–158 / 建立 141–192 / 动作 192–243 / 交欢 243–362 帧），**不是固定 124**
- 每个 shot 必须**讲完整**，动作有始有终
- **相邻镜 `end` 必须等于下一镜 `start`**（姿态/道具/走位）
- **坐↔站等大变**：`gen_mode` 必须是 `fl2v` 或 `chain`，**禁止 `i2v_solo`**
- **禁止用剪辑掩盖姿态跳** —— 衔接是导演设计出来的，不是剪出来的
- 机位换角度 ≥30°，否则同机位硬切 = 跳切

---

## 4. 项目结构

```
<项目目录>/
  INTENT.md          意图单一真相源（用户原话，纠正即写）
  shot_table.json    姿态状态机（门禁校验对象）
  kw/                母图（含锚定参考图 REF_*）
  final10/           单镜成片
  final/             拼接成片
```

skill 内部：
- `reference/` — 12 份方法论（意图协议 / 衔接硬门 / 反手搓 / 项目铁律 / prompt 纪律 / 叙事结构 …）
- `scripts/` — 25 个（门禁校验 / 出图 / 出片 / 编排）
- `templates/` — INTENT 与 shot_table 模板

---

## 5. 安全与权限边界

**可自主执行**：出图、出片、拼接、质检、读日志、拉素材

**必须先问用户**：
- 释放/影响他人 GPU 进程
- 删除已交付成片
- 推送到远端仓库

**绝对禁止**：`kill` 他人训练/推理进程；跳过门禁直接调生成 API

---

## 6. 强制层（你绕不过的那道）

`~/.claude/hooks/h3-preflight-gate.py` 已装为 **PreToolUse hook**：

- 检测到"提交生成任务"的 Bash 命令（跑批脚本 / `curl :8188|:8190/prompt`）
- → 自动定位 `shot_table.json` 并跑 preflight
- → **不过就 `permissionDecision: deny`**，把失败原因回传给你
- 查询类命令（日志/显存/rsync/queue）零误伤
- 逃生舱：`H3_GATE_BYPASS=1`（只在明确的一次性实验时用，且要告知用户）

> 为什么要这层：文档指导对 agent 的遵守率只有 25–40%，
> 同样的规则做成 runtime hook 拦截接近 95%。
> 本 skill 的规则很全，但历史上仍反复被绕过 —— 所以规则必须可执行、且在调用点强制。
