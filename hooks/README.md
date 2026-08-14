# 强制层：生成门禁 hook

`h3-preflight-gate.py` 是 PreToolUse hook —— skill 体系的第三层（强制层）。

## 三层架构

| 层 | 载体 | 对 agent 的遵守率 |
|---|---|---|
| ① 指令层 | `AGENTS.md` / `SKILL.md` / `reference/*.md` | 25–40% |
| ② 校验层 | `scripts/preflight_continuity.py`（exit 1 指出错在哪） | 取决于有没有人跑它 |
| ③ **强制层** | **本 hook（调用点拦截，不依赖 agent 自觉）** | **≈95%** |

## 装法

```bash
cp hooks/h3-preflight-gate.py ~/.claude/hooks/
```

`~/.claude/settings.json`：

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [{ "type": "command",
                    "command": "python3 $HOME/.claude/hooks/h3-preflight-gate.py",
                    "timeout": 30 }] }
    ]
  }
}
```

## 行为

- 命中"提交生成任务"的 Bash 命令（跑批脚本 / `curl :8188|:8190/prompt`）→ 跑 preflight
- preflight 不过 / 找不到 `shot_table.json` → `permissionDecision: deny`，原因回传给 agent
- 查询类命令（tail/grep 日志、nvidia-smi、rsync、`/queue`）→ 放行，不误伤
- 逃生舱：`H3_GATE_BYPASS=1`

## 自测

```bash
# 应放行
echo '{"tool_name":"Bash","cwd":"<项目>","tool_input":{"command":"ssh newgpu tail -5 x.log"}}' \
  | python3 ~/.claude/hooks/h3-preflight-gate.py

# 状态机破损时应 deny
echo '{"tool_name":"Bash","cwd":"<项目>","tool_input":{"command":"ssh newgpu python3 /home/admin01/t8_x.py"}}' \
  | python3 ~/.claude/hooks/h3-preflight-gate.py
```
