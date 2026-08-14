#!/usr/bin/env python3
"""h3-film-studio 生成门禁（PreToolUse hook）

拦截"提交视频/图像生成任务"的 Bash 命令，先跑 preflight_continuity.py，
不过就 deny，并把失败原因回传给 agent。

存在理由：散文规则 + 可执行校验都只是"建议"，agent 会绕。
        hook 在工具调用点直接拦，不依赖 agent 自觉。
        （文档指导遵守率 25-40%；runtime hook ≈95%）

装法：~/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash",
       "hooks": [{"type": "command",
                  "command": "python3 ~/.claude/hooks/h3-preflight-gate.py",
                  "timeout": 30}]}
    ]
  }
}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PREFLIGHT = Path.home() / ".claude/skills/h3-film-studio/scripts/preflight_continuity.py"

# 真正"提交生成任务"的命令特征（宁可漏拦，不要误伤查询类命令）
GEN_PATTERNS = [
    r"python3?\s+\S*(t8_|qwen_|krea_|fl2v_|amb|rek|steps|empty_room)\w*\.py",  # 跑批脚本
    r"h3_i2v_shot\.py",
    r"run_skill_full_zh\.py",
    r"curl[^|;]*:(8188|8190)/prompt",                                          # 直接投 ComfyUI 队列
]
# 明确放行：查询/诊断/传文件，不是生成
SAFE_PATTERNS = [
    r"^\s*(rsync|scp)\b",
    r"\bnvidia-smi\b",
    r"\b(tail|cat|grep|head|less|ls|pgrep|ps)\b.*\.log",
    r"curl[^|;]*/(queue|history|object_info|free|system_stats)",
]

# 找 shot_table.json 的候选位置
def find_shot_table(cwd: str) -> Path | None:
    cands: list[Path] = []
    c = Path(cwd) if cwd else Path.cwd()
    for d in [c, *c.parents][:4]:
        cands.append(d / "shot_table.json")
    # 桌面/文稿下的项目（按最近修改优先）
    for root in (Path.home() / "Desktop", Path.home() / "Documents"):
        if root.is_dir():
            try:
                cands.extend(sorted(root.glob("*/shot_table.json"),
                                    key=lambda p: p.stat().st_mtime, reverse=True))
            except OSError:
                pass
    for p in cands:
        if p.is_file():
            return p
    return None


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)                      # 输入异常一律放行，不阻塞正常工作

    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    cwd = data.get("cwd") or ""

    if any(re.search(p, cmd) for p in SAFE_PATTERNS):
        sys.exit(0)
    if not any(re.search(p, cmd) for p in GEN_PATTERNS):
        sys.exit(0)                      # 不是生成命令，放行

    # 逃生舱：显式声明本次是门禁之外的一次性实验
    if os.environ.get("H3_GATE_BYPASS") == "1" or "H3_GATE_BYPASS=1" in cmd:
        sys.exit(0)

    if not PREFLIGHT.is_file():
        deny(f"[h3 门禁] 找不到 preflight 脚本：{PREFLIGHT}")

    table = find_shot_table(cwd)
    if table is None:
        deny(
            "[h3 门禁] 拦截：没有 shot_table.json，禁止调用 H3/Krea 生成。\n"
            "按 reference/continuity-gate.md：先写姿态状态机（每镜 start/end/gen_mode），"
            "再跑 preflight_continuity.py，exit 0 之后才允许出片。\n"
            "模板：~/.claude/skills/h3-film-studio/templates/shot_table.template.json"
        )

    r = subprocess.run(
        [sys.executable, str(PREFLIGHT), "--table", str(table), "--strict-pose-change"],
        capture_output=True, text=True, timeout=25,
    )
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()
        deny(
            f"[h3 门禁] preflight 未通过（{table}），禁止生成。\n{msg}\n"
            "修好 shot_table.json 再跑一次 preflight，exit 0 后才可出片。"
        )
    sys.exit(0)                          # 过门，放行


if __name__ == "__main__":
    main()
