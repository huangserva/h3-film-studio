# 有 skill 为什么仍手搓？怎么解？

## 现象

仓库/skill 写得越来越全，但 agent 仍：

- 直接写 Comfy graph / `h3_i2v_shot.py` / scratchpad
- 跳过 `storyboard.json` / `shot_table.json`
- 独立出母图再拼片
- 交付后再「审计」衔接（用户已经看过烂片）

## 根因（不是「模型懒」那么简单）

| # | 根因 | 说明 |
|---|------|------|
| 1 | **规则是散文，生成是 API** | 「必须写起态」没有 `exit 1`，GPU 照样烧 |
| 2 | **旁路更短** | 历史成功脚本在 `/tmp/.../scratchpad`，复制即跑；主路径要读 1800 行 SKILL |
| 3 | **主路径能力缺口** | 文档写 fl2v，provider 只接了 i2v → 要么假遵守要么手搓 fl2v |
| 4 | **多入口** | adult-krea2 / h3-film-studio / 用户项目脚本 三套并行 |
| 5 | **催交付** | 「做完整成片」被理解成立刻出 mp4，状态机被当成可选项 |
| 6 | **事后 QC** | 衔接检查发生在用户眼睛上，而不是 preflight |

## 解法原则

```
可执行的门禁 > 更长的文档
唯一入口 > 更多旁路脚本
缺能力就显式失败 > 默默降级成 i2v_solo
```

### 已落地（本 skill）

1. **`reference/continuity-gate.md`** — 衔接硬门  
2. **`templates/shot_table.template.json`** — 姿态状态机模板  
3. **`scripts/preflight_continuity.py`** — 相邻 end≠start 或坐站大变却 i2v_solo → **exit 1**  
4. **SKILL 步骤 0.5** — 无 preflight 通过禁止出片  

### Agent 必须遵守的入口

```bash
# 1) 写 shot_table.json
# 2) 门禁
python3 ~/.claude/skills/h3-film-studio/scripts/preflight_continuity.py \
  --table <项目>/shot_table.json --strict-pose-change

# 3) exit 0 之后才允许生成
```

### 仍待工程化（诚实列表）

- `local_providers.video_h3` 正式支持 `fl2v` / `chain`（现在脚本旁路存在，主 dispatch 未强制）  
- 出片 runner 在 submit Comfy 前 **内嵌调用 preflight**（不调用也能跑的脚本应删或加 assert）  
- 旧 `adult-krea2-h3-narrative` 顶部 redirect 到本 skill  

## 给用户的判据

若 agent：

- 交不出 `shot_table.json` + preflight 日志  
- 或承认「先出了视频再补表」  

→ **仍是手搓**，流程不合格，不管成片好不好看。
