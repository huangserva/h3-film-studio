#!/usr/bin/env python3
"""按 reference/audio-track.md 的「H3 原声拼片规则」拼接多镜成片（2026-09-03 买鸟记定版）。

规则（只用 H3 自己的音轨，不铺任何外部声音，不用 loudnorm 这类带压缩的归一）：
1. 每镜裁掉开头 head_trim 秒（H3 音频 t=0 的瞬态 + 死寂；母图静帧无信息），连画带声。
2. 镜尾死寂只留 tail_keep 秒（用 RMS 窗找最后一个有声窗）。
3. 用 ebur128 量每镜综合响度，按纯增益对齐到 target LUFS。
4. 切点做 xfade 秒音频交叉淡化（默认 0.15 s；太长会淡掉下一镜起得早的旁白首字），视频硬切。

用法：
  python3 assemble_h3_cuts.py --clips s01.mp4 s02.mp4 ... --out final.mp4
  python3 assemble_h3_cuts.py --manifest manifest.json --shots-dir shots --out final.mp4
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess


def lufs(path: str) -> float:
    o = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    tail = o[o.rfind("Summary:"):]
    return float(re.search(r"I:\s*(-?[\d.]+) LUFS", tail).group(1))


def rms_series(path: str, window_samples: int = 11025):
    tmp = "/tmp/_assemble_rms.txt"
    subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", path, "-af",
                    f"asetnsamples={window_samples},astats=metadata=1:reset=1,"
                    f"ametadata=print:key=lavfi.astats.Overall.RMS_level:file={tmp}",
                    "-f", "null", "-"], capture_output=True)
    rows, t = [], None
    for line in open(tmp):
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"RMS_level=(-?[\d.]+|-inf)", line)
        if m and t is not None:
            rows.append((t, -99.0 if m.group(1) == "-inf" else float(m.group(1))))
    return rows


def duration(path: str) -> float:
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True).stdout.strip()
    return float(o)


def plan_clip(path: str, *, head_trim: float, tail_keep: float, target: float, loud_thresh: float):
    rows = rms_series(path)
    dur = duration(path)
    loud = [t for t, v in rows if v > loud_thresh]
    last_loud = max(loud) if loud else dur
    end = min(dur, last_loud + 0.25 + tail_keep)
    # 头：裁掉 t=0 的瞬态与死寂，但不许切进人声——最多 head_trim，且停在第一个有声窗前 0.1 s
    # （t=0 那个窗本身是瞬态，跳过它再找起声点）
    onset = next((t for t, v in rows if t >= 0.25 and v > loud_thresh), None)
    # 起声点前留 0.3 s 余量（交叉淡化会再吃掉一点），起声很早的镜干脆不裁头
    head = head_trim if onset is None else max(0.0, min(head_trim, onset - 0.3))
    gain = target - lufs(path)
    return {"head": round(head, 2), "end": round(end, 2), "gain": round(gain, 2), "duration": round(dur, 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble H3 shots with head trim, gain match and crossfades")
    ap.add_argument("--clips", nargs="*", default=[])
    ap.add_argument("--manifest")
    ap.add_argument("--shots-dir", default="shots")
    ap.add_argument("--out", required=True)
    ap.add_argument("--head-trim", type=float, default=0.5)
    ap.add_argument("--tail-keep", type=float, default=0.4)
    ap.add_argument("--target-lufs", type=float, default=-18.0)
    ap.add_argument("--xfade", type=float, default=0.1,
                    help="切点交叉淡化秒数；不能长，否则会把下一镜起得早的旁白首字淡掉（s15 教训）")
    ap.add_argument("--loud-thresh", type=float, default=-45.0)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--plan-out", default="")
    a = ap.parse_args()

    clips = list(a.clips)
    if a.manifest:
        base = pathlib.Path(a.manifest).parent
        clips = [str(base / a.shots_dir / f"{it['id']}.mp4") for it in json.load(open(a.manifest))]
    if len(clips) < 2:
        raise SystemExit("至少两镜")
    missing = [c for c in clips if not pathlib.Path(c).is_file()]
    if missing:
        raise SystemExit(f"缺文件: {missing}")

    plans = {c: plan_clip(c, head_trim=a.head_trim, tail_keep=a.tail_keep, target=a.target_lufs,
                          loud_thresh=a.loud_thresh) for c in clips}
    ins, fc = [], []
    for i, c in enumerate(clips):
        p = plans[c]
        ins += ["-i", c]
        fc.append(f"[{i}:v]trim=start={p['head']}:end={p['end']},setpts=PTS-STARTPTS[v{i}]")
        fc.append(f"[{i}:a]atrim=start={p['head']}:end={p['end']},asetpts=PTS-STARTPTS,volume={p['gain']}dB[a{i}]")
    prev = "a0"
    for i in range(1, len(clips)):
        nxt = f"x{i}" if i < len(clips) - 1 else "aout"
        fc.append(f"[{prev}][a{i}]acrossfade=d={a.xfade}:c1=tri:c2=tri[{nxt}]")
        prev = nxt
    fc.append("".join(f"[v{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[vout]")
    cmd = ["ffmpeg", "-y", "-v", "error"] + ins + ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[-800:])
    if a.plan_out:
        json.dump(plans, open(a.plan_out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"out": a.out, "clips": len(clips), "duration": round(duration(a.out), 2),
                      "gains_db": [plans[c]["gain"] for c in clips]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
