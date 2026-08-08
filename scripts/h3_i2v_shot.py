#!/usr/bin/env python3
"""Single-shot H3 i2v with LoRA stack — winner recipe from 2026-08-08 A/B matrix.

Default stack: HMNSFW 0.5 + Motion Booster 0.7, 20 steps (motion mean 5.16 on the
calibrated ruler: dead fl2v morph = 0.25, best historical r2v = 2.4-4.9).
--turbo: swap in 4-step turbo LoRA for 3x faster drafts (quality holds).

Run from Mac via tunnel (default 127.0.0.1:18190) or on the box with
--h3 http://127.0.0.1:8190.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import time
import urllib.parse
import urllib.request
import uuid

H3_DEFAULT = "http://127.0.0.1:18190"
TASK = "i2v — 图生视频(Image to Video)"
UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
HM = "HMNSFW_AIO_V2.safetensors"
BOOST = "H3_Motion_Booster.safetensors"
TURBO = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"


def http_json(url, data=None, method=None, timeout=120):
    body = None if data is None else json.dumps(data).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def upload_image(h3, path: pathlib.Path, name: str) -> str:
    boundary = uuid.uuid4().hex
    data = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{h3}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    up = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return f"{up['subfolder']}/{up['name']}" if up.get("subfolder") else up["name"]


def build_graph(*, start_name, prompt, w, h, frames, fps, seed, loras, steps, prefix, unet):
    dur = frames / fps
    timeline = {
        "version": 4, "editMode": "global", "timelineMode": "i2v",
        "totalFrames": frames, "frameRate": fps, "width": w, "height": h,
        "refMaxSize": max(w, h),
        "output": {"mode": "fixed", "longEdge": max(w, h), "width": w, "height": h,
                   "maxExportFrames": 0, "exportMode": "all",
                   "continuityEnabled": False, "continuityOverlapFrames": 9},
        "videoClips": [],
        "video": {"fileName": "", "videoFile": "", "subfolder": "", "type": "input",
                  "frames": [], "frameMap": []},
        "global": {"taskType": TASK, "prompt": prompt, "refs": [], "referenceVideo": {},
                   "continuousReference": False,
                   "genImage": {"imageFile": start_name, "width": w, "height": h}},
        "shots": [{"id": "s0", "durationSec": dur, "prompt": prompt,
                   "startImage": {"imageFile": start_name, "width": w, "height": h}}],
        "segments": [{"id": "s0", "start": 0, "length": frames, "frameCount": frames,
                      "durationSec": dur, "prompt": prompt, "taskType": TASK,
                      "refs": [], "referenceVideo": {},
                      "genImage": {"imageFile": start_name, "width": w, "height": h},
                      "negativePrompt": ""}],
        "gen": {"defaultFrameCount": frames},
        "runSelectEnabled": False, "runSelection": [],
    }
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                         "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
    }
    prev = ["1", 0]
    for i, (lname, s) in enumerate(loras):
        nid = f"1{i}"
        g[nid] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": prev, "lora_name": lname, "strength_model": s}}
        prev = [nid, 0]
    g["5"] = {"class_type": "MiniMaxH3Director", "inputs": {
        "model": prev, "video_vae": ["3", 0], "audio_vae": ["4", 0], "clip": ["2", 0],
        "task_type": TASK, "global_prompt": prompt,
        "bd_grp_sample": "采样设置", "cfg": 1.0, "seed": seed, "frame_rate": fps,
        "width": w, "height": h, "ref_max_size": max(w, h), "total_frames": frames,
        "timeline_data": json.dumps(timeline, ensure_ascii=False),
        "bd_grp_advanced": "高级采样 Advanced", "steps": steps,
        "sampler": "res_multistep", "scheduler": "simple",
        "shift_video": 12.0, "shift_audio": 3.0,
        "bd_grp_perf": "性能 Performance",
        "clear_vram_between_segments": True, "export_source_images": False}}
    g["6"] = {"class_type": "CreateVideo",
              "inputs": {"images": ["5", 0], "fps": ["5", 2], "audio": ["5", 1], "bit_depth": 8}}
    g["7"] = {"class_type": "SaveVideo",
              "inputs": {"video": ["6", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return g


def wait_prompt(h3, pid, timeout_s=2400):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        hist = http_json(f"{h3}/history/{pid}", timeout=30)
        if pid in hist:
            h = hist[pid]
            st = h.get("status") or {}
            if st.get("status_str") == "error":
                for m in st.get("messages") or []:
                    if m[0] == "execution_error":
                        raise RuntimeError(
                            f"{m[1].get('exception_type')}: {(m[1].get('exception_message') or '')[:1500]}")
                raise RuntimeError(json.dumps(st, ensure_ascii=False)[:1500])
            if st.get("completed") or h.get("outputs"):
                return h
        time.sleep(10)
    raise TimeoutError(pid)


def motion_mean(video: pathlib.Path):
    cmd = ["ffmpeg", "-v", "error", "-i", str(video),
           "-vf", "format=gray,tblend=all_mode=difference,signalstats,"
                  "metadata=print:key=lavfi.signalstats.YAVG:file=-",
           "-an", "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    vals = [float(l.split("YAVG=")[1]) for l in r.stdout.splitlines() if "YAVG=" in l][1:]
    return round(sum(vals) / len(vals), 2) if vals else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h3", default=H3_DEFAULT)
    ap.add_argument("--start", help="local image path (uploaded + resized)")
    ap.add_argument("--input-name", help="image already in ComfyUI input/ (skips upload)")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--prompt-file", default="")
    ap.add_argument("--lora", action="append", default=[],
                    help="file.safetensors:strength — repeatable; overrides default stack")
    ap.add_argument("--turbo", action="store_true", help="draft mode: +turbo LoRA, 4 steps")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--frames", type=int, default=124, help="must be on the 17k+5 grid")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=864)
    ap.add_argument("--fps", type=float, default=24)
    ap.add_argument("--seed", type=int, default=20260804)
    ap.add_argument("--prefix", default="video/i2v_shot/shot")
    ap.add_argument("--out", default=".")
    ap.add_argument("--unet", default=UNET)
    args = ap.parse_args()

    if (args.frames - 5) % 17:
        raise SystemExit(f"frames {args.frames} not on 17k+5 grid (37/54/71/88/105/124/...)")
    prompt = pathlib.Path(args.prompt_file).read_text(encoding="utf-8").strip() if args.prompt_file else args.prompt
    if not prompt:
        raise SystemExit("need --prompt or --prompt-file (register format, see references/hmnsfw-register.md)")

    loras = [(f, float(s)) for f, s in (l.rsplit(":", 1) for l in args.lora)] if args.lora \
        else [(HM, 0.5), (BOOST, 0.7)]
    steps = args.steps
    if args.turbo:
        loras = loras + [(TURBO, 1.0)]
        steps = steps or 4
    steps = steps or 20

    if args.input_name:
        start_name = args.input_name
    elif args.start:
        src = pathlib.Path(args.start)
        work = pathlib.Path(args.out) / "work"
        work.mkdir(parents=True, exist_ok=True)
        resized = work / f"{src.stem}_{args.width}x{args.height}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                        "-vf", f"scale={args.width}:{args.height}:flags=lanczos", str(resized)],
                       check=True)
        start_name = upload_image(args.h3, resized, resized.name)
        print("uploaded", start_name)
    else:
        raise SystemExit("need --start or --input-name")

    http_json(f"{args.h3}/free", {"unload_models": True, "free_memory": True}, method="POST", timeout=60)
    time.sleep(2)
    g = build_graph(start_name=start_name, prompt=prompt, w=args.width, h=args.height,
                    frames=args.frames, fps=args.fps, seed=args.seed, loras=loras,
                    steps=steps, prefix=args.prefix, unet=args.unet)
    print("loras:", loras, "| steps:", steps, "| seed:", args.seed)
    t0 = time.time()
    resp = http_json(f"{args.h3}/prompt", {"prompt": g, "client_id": str(uuid.uuid4())}, timeout=60)
    if resp.get("node_errors"):
        raise SystemExit(json.dumps(resp["node_errors"], ensure_ascii=False)[:2000])
    pid = resp["prompt_id"]
    print("queued", pid)
    h = wait_prompt(args.h3, pid)
    print(f"done in {round(time.time()-t0,1)}s")

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = pathlib.Path(args.prefix).name
    for _n, o in (h.get("outputs") or {}).items():
        for key in ("gifs", "videos", "images"):
            for item in o.get(key) or []:
                qs = urllib.parse.urlencode({"filename": item["filename"],
                                             "subfolder": item.get("subfolder", ""),
                                             "type": item.get("type", "output")})
                data = urllib.request.urlopen(f"{args.h3}/view?{qs}", timeout=600).read()
                p = out / f"{stem}{pathlib.Path(item['filename']).suffix or '.mp4'}"
                p.write_bytes(data)
                print("saved", p, len(data))
                if p.suffix == ".mp4":
                    mm = motion_mean(p)
                    if mm is not None:
                        print(f"motion_mean={mm}  (ruler: dead=0.25 / alive=2.4-4.9 / target>=3.5 / action=10)")


if __name__ == "__main__":
    main()
