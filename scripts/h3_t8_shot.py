#!/usr/bin/env python3
"""H3 T8 multi-rate 出片器（威逼场 2026-08-24/25 验证配方，收进 skill，取代盒上散脚本）。

配方：MiniMaxH3AudioConditioningT8(audio_mode=native)
      + MiniMaxH3MultiRateSamplerEXPT8(video_steps=4, audio_steps=8)
      + turbo LoRA 1.0 + MiniMaxH3AVDecodeT8 → CreateVideo/SaveVideo
prompt 必须来自 h3_prompt_compiler.py（脚本会拒收非官方格式的 prompt）。

用法：
  单镜： python3 h3_t8_shot.py --h3 http://127.0.0.1:8190 --start kw/s01.png \
           --prompt-file shots/s01.prompt.txt --frames 192 --width 864 --height 480 --out shots/
  批量： python3 h3_t8_shot.py --h3 ... --batch manifest.json --width 864 --height 480 --out shots/
         manifest: [{id, start, prompt_file, frames, seed, task?, end?}]，路径相对 manifest 所在目录
  可选： --extra-lora name:strength（可重复，如成人合戏挂 HMNSFW/Booster）；--free 每镜前 POST /free
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.parse
import urllib.request
import uuid

TURBO = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"


def http_json(url, data=None, method=None, timeout=120):
    body = None if data is None else json.dumps(data).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def upload_image(h3: str, path: pathlib.Path) -> str:
    boundary = uuid.uuid4().hex
    data = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
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


def build_graph(*, task, first, last, prompt, w, h, frames, seed, prefix,
                extra_loras, video_steps, audio_steps, turbo_lora=TURBO):
    g = {
        "1": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                                                    "type": "minimax", "device": "default"}},
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "imgA": {"class_type": "LoadImage", "inputs": {"image": first}},
    }
    prev = ["4", 0]
    n = 40
    base_loras = [] if turbo_lora is None else [(turbo_lora, 1.0)]
    for name, strength in base_loras + list(extra_loras):
        n += 1
        g[str(n)] = {"class_type": "LoraLoaderModelOnly",
                     "inputs": {"model": prev, "lora_name": name, "strength_model": strength}}
        prev = [str(n), 0]
    cond = {"clip": ["3", 0], "video_vae": ["1", 0], "audio_vae": ["2", 0], "prompt": prompt,
            "width": w, "height": h, "length": frames,
            "task_type": "FL2VA" if task == "fl2va" else "I2VA", "audio_mode": "native",
            "audio_denoise_strength": 1.0, "add_source_as_reference": False,
            "prompt_primary_audio_ordinal": 0, "strict_prompt_tags": True,
            "ref_image_size": "match", "reference_video_policy": "official_2_to_15s",
            "first_frame": ["imgA", 0]}
    if task == "fl2va":
        g["imgB"] = {"class_type": "LoadImage", "inputs": {"image": last}}
        cond["last_frame"] = ["imgB", 0]
    g["6"] = {"class_type": "MiniMaxH3AudioConditioningT8", "inputs": cond}
    g["7"] = {"class_type": "MiniMaxH3MultiRateSamplerEXPT8",
              "inputs": {"model": prev, "av_latent": ["6", 1], "video_steps": video_steps,
                         "audio_steps": audio_steps, "shift_video": 12.0, "shift_audio": 3.0}}
    g["8"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["9"] = {"class_type": "BasicGuider", "inputs": {"model": prev, "conditioning": ["6", 0]}}
    g["10"] = {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["8", 0], "guider": ["9", 0], "sampler": ["7", 1],
                          "sigmas": ["7", 2], "latent_image": ["6", 1]}}
    g["11"] = {"class_type": "MiniMaxH3AVDecodeT8",
               "inputs": {"av_latent": ["10", 0], "video_vae": ["1", 0], "audio_vae": ["2", 0]}}
    g["12"] = {"class_type": "CreateVideo",
               "inputs": {"images": ["11", 0], "fps": 24, "audio": ["11", 1], "bit_depth": 8}}
    g["13"] = {"class_type": "SaveVideo",
               "inputs": {"video": ["12", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return g


def wait_prompt(h3: str, pid: str, timeout_s: int = 1800):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        hist = http_json(f"{h3}/history/{pid}", timeout=30)
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(f"H3 error: {json.dumps(st)[:500]}")
            if hist[pid].get("outputs"):
                return hist[pid]
        time.sleep(5)
    raise TimeoutError(pid)


def download_outputs(h3: str, hist: dict, out_dir: pathlib.Path, sid: str) -> pathlib.Path | None:
    for _node, out in hist.get("outputs", {}).items():
        for key in ("videos", "gifs", "images"):
            for item in out.get(key, []):
                if not str(item.get("filename", "")).endswith(".mp4"):
                    continue
                qs = urllib.parse.urlencode({"filename": item["filename"],
                                             "subfolder": item.get("subfolder", ""),
                                             "type": item.get("type", "output")})
                data = urllib.request.urlopen(f"{h3}/view?{qs}", timeout=600).read()
                dst = out_dir / f"{sid}.mp4"
                dst.write_bytes(data)
                return dst
    return None


def assert_official_prompt(sid: str, prompt: str) -> None:
    ok = ("integrated_multimodal_description:" in prompt and "overall_soundscape:" in prompt) or \
         ("detailed_description:" in prompt and "subject_definitions:" in prompt)
    if not ok:
        raise SystemExit(f"{sid}: prompt 不是官方格式（缺三字段/六段结构）——必须由 h3_prompt_compiler.py 生成")


def run_one(h3, *, sid, start, prompt, frames, seed, task, end, w, h, out_dir,
            extra_loras, video_steps, audio_steps, free, turbo_lora=TURBO):
    assert_official_prompt(sid, prompt)
    if free:
        try:
            http_json(f"{h3}/free", {"unload_models": False, "free_memory": True}, method="POST", timeout=60)
        except Exception:
            pass
        time.sleep(2)
    first = upload_image(h3, pathlib.Path(start))
    last = upload_image(h3, pathlib.Path(end)) if (task == "fl2va" and end) else None
    g = build_graph(task=task, first=first, last=last, prompt=prompt, w=w, h=h, frames=frames,
                    seed=seed, prefix=f"video/h3_t8/{sid}", extra_loras=extra_loras,
                    video_steps=video_steps, audio_steps=audio_steps, turbo_lora=turbo_lora)
    r = http_json(f"{h3}/prompt", {"prompt": g, "client_id": str(uuid.uuid4())}, timeout=60)
    if r.get("node_errors"):
        raise SystemExit(f"{sid}: NODE_ERR {json.dumps(r['node_errors'], ensure_ascii=False)[:400]}")
    t0 = time.time()
    hist = wait_prompt(h3, r["prompt_id"])
    dst = download_outputs(h3, hist, out_dir, sid)
    print("RESULT", json.dumps({"id": sid, "file": str(dst), "seconds": round(time.time() - t0, 1),
                                "frames": frames, "seed": seed}, ensure_ascii=False), flush=True)
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description="H3 T8 multi-rate shot runner (official-format prompts only)")
    ap.add_argument("--h3", default="http://127.0.0.1:8190")
    ap.add_argument("--batch", help="manifest.json: [{id,start,prompt_file,frames,seed,task?,end?}]")
    ap.add_argument("--id", default="shot")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--prompt-file")
    ap.add_argument("--frames", type=int, default=124)
    ap.add_argument("--seed", type=int, default=1001)
    ap.add_argument("--task", choices=["i2va", "fl2va"], default="i2va")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=864)
    ap.add_argument("--video-steps", type=int, default=4)
    ap.add_argument("--audio-steps", type=int, default=8)
    ap.add_argument("--extra-lora", action="append", default=[], help="name:strength")
    ap.add_argument("--free", action="store_true")
    ap.add_argument("--out", default=".")
    ap.add_argument("--no-turbo", action="store_true",
                    help="不挂 turbo LoRA（配合 --video-steps 20 --audio-steps 24 做质量基线）")
    ap.add_argument("--turbo-lora", default=TURBO, help="换用别的 turbo LoRA 文件名")
    a = ap.parse_args()
    if a.width % 32 or a.height % 32:
        raise SystemExit("width/height 必须 ÷32")
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    loras = [(s.split(":")[0], float(s.split(":")[1])) for s in a.extra_lora]
    common = dict(w=a.width, h=a.height, out_dir=out, extra_loras=loras,
                  video_steps=a.video_steps, audio_steps=a.audio_steps, free=a.free,
                  turbo_lora=None if a.no_turbo else a.turbo_lora)
    if a.batch:
        base = pathlib.Path(a.batch).parent
        for it in json.load(open(a.batch)):
            if (it["frames"] - 5) % 17:
                print("FAIL", json.dumps({"id": it["id"], "error": "frames 不在 17k+5 网格"}), flush=True)
                continue
            try:
                run_one(a.h3, sid=it["id"], start=str(base / it["start"]),
                        prompt=(base / it["prompt_file"]).read_text(), frames=it["frames"],
                        seed=it.get("seed", 1001), task=it.get("task", "i2va"),
                        end=str(base / it["end"]) if it.get("end") else None, **common)
            except Exception as e:  # keep the batch going; the caller reads FAIL lines
                print("FAIL", json.dumps({"id": it["id"], "error": str(e)[:300]}, ensure_ascii=False), flush=True)
        print("BATCHDONE", flush=True)
    else:
        if (a.frames - 5) % 17:
            raise SystemExit("frames 必须在 17k+5 网格上")
        run_one(a.h3, sid=a.id, start=a.start, prompt=pathlib.Path(a.prompt_file).read_text(),
                frames=a.frames, seed=a.seed, task=a.task, end=a.end, **common)


if __name__ == "__main__":
    main()
