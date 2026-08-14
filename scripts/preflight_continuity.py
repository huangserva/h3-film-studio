#!/usr/bin/env python3
"""Continuity preflight gate — refuse generation if shot state machine is broken.

Usage:
  python3 preflight_continuity.py --table /path/to/shot_table.json
  python3 preflight_continuity.py --table shot_table.json --strict-pose-change

Exit 0 = OK to generate. Exit 1 = must fix table first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

POSE_KEYS_DEFAULT = ("man", "woman")
# keys that must match end[i] == start[i+1] when present on both sides
STATE_KEYS_COMPARE = ("man", "woman", "prop_silver", "blocking")

BIG_POSE = {"sit", "stand", "lie", "kneel"}


def load_table(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "shots" not in data or not isinstance(data["shots"], list):
        raise SystemExit(f"{path}: missing shots[]")
    return data


def pose_changed(a: dict, b: dict, who: str) -> bool:
    if who not in a or who not in b:
        return False
    va, vb = a[who], b[who]
    if va in BIG_POSE and vb in BIG_POSE and va != vb:
        return True
    return False


def check(table: dict[str, Any], *, strict_pose_change: bool) -> list[str]:
    errors: list[str] = []
    shots = table["shots"]
    if len(shots) < 1:
        return ["shots[] is empty"]

    for i, sh in enumerate(shots):
        sid = sh.get("id", f"index_{i}")
        for req in ("id", "start", "end", "gen_mode"):
            if req not in sh:
                errors.append(f"{sid}: missing field `{req}`")
        start, end = sh.get("start") or {}, sh.get("end") or {}
        if not isinstance(start, dict) or not isinstance(end, dict):
            errors.append(f"{sid}: start/end must be objects")
            continue
        for who in POSE_KEYS_DEFAULT:
            if who not in start or who not in end:
                errors.append(f"{sid}: start/end must include `{who}` pose")

        mode = (sh.get("gen_mode") or "").strip()
        allowed = {"i2v", "i2v_solo", "fl2v", "chain"}
        if mode and mode not in allowed:
            errors.append(f"{sid}: gen_mode={mode!r} not in {sorted(allowed)}")

        # big pose change inside shot → cannot be solo independent i2v
        changed = any(pose_changed(start, end, w) for w in POSE_KEYS_DEFAULT)
        if changed and mode in ("i2v_solo",):
            errors.append(
                f"{sid}: pose changes inside shot (sit/stand/…) but gen_mode=i2v_solo; "
                f"use fl2v (first+last) or chain"
            )
        if changed and mode == "i2v" and strict_pose_change:
            errors.append(
                f"{sid}: pose changes inside shot; under --strict-pose-change require fl2v or chain "
                f"(not plain i2v)"
            )

        if mode == "chain" and not sh.get("chain_from_previous"):
            errors.append(f"{sid}: gen_mode=chain requires chain_from_previous=true")

    # adjacent continuity
    for i in range(len(shots) - 1):
        a, b = shots[i], shots[i + 1]
        aid, bid = a.get("id", i), b.get("id", i + 1)
        ae, bs = a.get("end") or {}, b.get("start") or {}
        for key in STATE_KEYS_COMPARE:
            if key in ae and key in bs and ae[key] != bs[key]:
                errors.append(
                    f"JUNCTION {aid}→{bid}: end.{key}={ae[key]!r} != start.{key}={bs[key]!r} "
                    f"(上一镜终态必须等于下一镜起态)"
                )
        # chain target should match previous end physically
        if b.get("gen_mode") == "chain" or b.get("chain_from_previous"):
            for who in POSE_KEYS_DEFAULT:
                if who in ae and who in bs and ae[who] != bs[who]:
                    errors.append(
                        f"JUNCTION {aid}→{bid}: chain shot but {who} pose breaks "
                        f"({ae[who]}→{bs[who]})"
                    )

    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="H3 film continuity preflight gate")
    ap.add_argument("--table", required=True, help="path to shot_table.json")
    ap.add_argument(
        "--strict-pose-change",
        action="store_true",
        help="require fl2v/chain whenever sit/stand changes inside a shot",
    )
    args = ap.parse_args()
    path = Path(args.table).expanduser().resolve()
    if not path.is_file():
        print(f"FAIL: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    table = load_table(path)
    errors = check(table, strict_pose_change=args.strict_pose_change)
    n = len(table["shots"])
    if errors:
        print(f"PREFLIGHT FAIL — {path.name} ({n} shots, {len(errors)} error(s))", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print(
            "\nFix shot_table.json, then re-run preflight. "
            "Do NOT call H3/Krea until exit 0.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"PREFLIGHT OK — {path} ({n} shots)")
    print("Safe to generate (still verify mother stills match start/end keys).")
    sys.exit(0)


if __name__ == "__main__":
    main()
