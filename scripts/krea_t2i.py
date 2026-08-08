#!/usr/bin/env python3
"""Batch Krea2 + 刀斧手 stills from STORYBOARD.json."""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.request
import uuid

COMFY_DEFAULT = "http://127.0.0.1:18188"


def http_json(url, data=None, method=None, timeout=120):
    import urllib.error

    # Compact separators avoid rare ComfyUI validation glitches on re-submit.
    body = (
        None
        if data is None
        else json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    headers = {"Content-Type": "application/json; charset=utf-8"} if data is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}: {err[:3000]}") from e


def download_image(comfy: str, item: dict, dest: pathlib.Path):
    from urllib.parse import urlencode

    qs = urlencode(
        {
            "filename": item["filename"],
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }
    )
    data = urllib.request.urlopen(f"{comfy}/view?{qs}", timeout=120).read()
    dest.write_bytes(data)
    return dest


def build_workflow(prompt: str, *, seed: int, width: int, height: int, lora: str, strength: float, prefix: str):
    # Force pure JSON types — Comfy EmptyLatentImage is picky after long queues.
    w = int(width)
    h = int(height)
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": "krea2_turbo_fp8.safetensors", "weight_dtype": "default"},
        },
        "13": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen3vl_4b_fp8_scaled.safetensors",
                "type": "krea2",
                "device": "default",
            },
        },
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "40": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": str(lora),
                "strength_model": float(strength),
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": str(prompt), "clip": ["13", 0]},
        },
        "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "10": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": w, "height": h, "batch_size": 1},
        },
        "2": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["40", 0],
                "seed": int(seed),
                "steps": 8,
                "cfg": 1.0,
                # MemOS-validated 刀斧手 T2I: euler_ancestral / sgm_uniform (not er_sde/simple)
                "sampler_name": "euler_ancestral",
                "scheduler": "sgm_uniform",
                "positive": ["6", 0],
                "negative": ["8", 0],
                "latent_image": ["10", 0],
                "denoise": 1.0,
            },
        },
        "3": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["4", 0]}},
        "5": {
            "class_type": "SaveImage",
            "inputs": {"images": ["3", 0], "filename_prefix": str(prefix)},
        },
    }


def fill_prompt(template: str, story: dict) -> str:
    ident = story["identity"]
    male = story.get("male_identity") or {}
    face = ident.get("face_block_zh") or ident.get("face_block_en") or ""
    face_en = ident.get("face_block_en") or face
    # Face/hair only — do NOT bake robe into every shot
    male_base_zh = male.get("lock_zh") or male.get("lock_en") or ""
    male_base_en = male.get("lock_en") or male_base_zh
    clothed_zh = male.get("clothed_zh") or ""
    clothed_en = male.get("clothed_en") or ""
    nude_zh = male.get("nude_zh") or (
        "全身赤裸一丝不挂，袍服已完全脱掉，仅保留头上黑色网巾或幞头与胡须，赤裸身体与阴茎可见"
    )
    nude_en = male.get("nude_en") or (
        "fully naked completely nude male, robes fully removed, only black wangjin or futou and beard, bare body and penis visible"
    )
    male_clothed_zh = f"{male_base_zh}，{clothed_zh}".strip("，")
    male_clothed_en = f"{male_base_en}, {clothed_en}".strip(", ")
    male_nude_zh = f"{male_base_zh}，{nude_zh}".strip("，")
    male_nude_en = f"{male_base_en}, {nude_en}".strip(", ")
    style = story.get("global_style_zh") or story.get("global_style_en") or ""
    text = (
        template.replace("{face_en}", face_en)
        .replace("{face}", face)
        .replace("{male_nude_en}", male_nude_en)
        .replace("{male_nude}", male_nude_zh)
        .replace("{male_en}", male_clothed_en)
        .replace("{male}", male_clothed_zh)
        .replace("{style}", style)
        .replace("{limbs}", "")
        .replace("{limbs_en}", "")
    )
    # Safety-only negatives (underage etc). Prefer detailed positive description for era/limbs.
    safety = ident.get("negative_safety_only") or ident.get("negative") or ""
    if safety:
        text = f"{text}. {safety}"
    return text


def wait_prompt(comfy: str, pid: str, timeout_s: int = 300):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        hist = http_json(f"{comfy}/history/{pid}", timeout=30)
        if pid not in hist:
            time.sleep(1.5)
            continue
        h = hist[pid]
        st = h.get("status") or {}
        if st.get("status_str") == "error":
            raise RuntimeError(json.dumps(st, ensure_ascii=False)[:2000])
        if st.get("completed") or h.get("outputs"):
            return h
        time.sleep(1.5)
    raise TimeoutError(pid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--comfy", default=COMFY_DEFAULT)
    ap.add_argument("--only", default="", help="comma shot ids, empty=all")
    ap.add_argument(
        "--seed-offset",
        type=int,
        default=0,
        help="add to master_seed+index for re-rolls without changing storyboard",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="regenerate even if output png already exists",
    )
    args = ap.parse_args()

    story = json.loads(pathlib.Path(args.storyboard).read_text(encoding="utf-8"))
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    krea = story.get("krea") or {}
    lora = krea.get("lora", "krea2_lora 通行证刀斧手版.safetensors")
    # MemOS default 0.5; see references/krea2-lora-doctrine.md
    strength = float(krea.get("lora_strength", 0.5))
    w = int(story.get("krea_width", 720))
    h = int(story.get("krea_height", 1280))
    base_seed = int(story.get("master_seed", 42))
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    http_json(
        f"{args.comfy}/free",
        {"unload_models": True, "free_memory": True},
        method="POST",
        timeout=60,
    )
    time.sleep(1)

    meta = {"shots": []}
    for i, shot in enumerate(story["shots"]):
        sid = shot["id"]
        if only and sid not in only:
            continue
        dest = out / f"{sid}.png"
        if (
            not args.force
            and dest.exists()
            and dest.stat().st_size > 1000
        ):
            print(f"skip existing {dest}")
            meta["shots"].append({"id": sid, "path": str(dest), "skipped": True})
            continue
        prompt = fill_prompt(shot["prompt_krea"], story)
        seed = base_seed + i + int(args.seed_offset)
        prefix = f"{story.get('slug', 'adult')}/{sid}"
        # union/sex stills: stronger 刀斧手 when story provides lora_strength_sex
        shot_strength = strength
        if shot.get("phase") == "union" or shot.get("sexgod_strength") is not None:
            shot_strength = float(krea.get("lora_strength_sex", strength))
        if shot.get("krea_lora_strength") is not None:
            shot_strength = float(shot["krea_lora_strength"])
        wf = build_workflow(
            prompt,
            seed=seed,
            width=w,
            height=h,
            lora=lora,
            strength=shot_strength,
            prefix=prefix,
        )
        print(f"strength={shot_strength} seed={seed}")
        client_id = str(uuid.uuid4())
        # retry transient 400/502 a few times
        resp = None
        last_err = None
        for attempt in range(4):
            try:
                resp = http_json(
                    f"{args.comfy}/prompt",
                    {"prompt": wf, "client_id": client_id},
                    timeout=60,
                )
                break
            except Exception as e:
                last_err = e
                print(f"prompt attempt {attempt+1} failed for {sid}: {e}")
                time.sleep(2 + attempt * 2)
        if resp is None:
            raise RuntimeError(last_err)
        if resp.get("node_errors"):
            raise RuntimeError(resp["node_errors"])
        pid = resp["prompt_id"]
        print(f"queued {sid} {pid} seed={seed}")
        h = wait_prompt(args.comfy, pid)
        saved = None
        for _node, outputs in (h.get("outputs") or {}).items():
            for img in outputs.get("images") or []:
                download_image(args.comfy, img, dest)
                saved = str(dest)
                print("saved", dest)
        meta["shots"].append({"id": sid, "seed": seed, "path": saved, "prompt_id": pid})
        (out / f"{sid}.json").write_text(
            json.dumps({"id": sid, "seed": seed, "prompt": prompt, "prompt_id": pid}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # brief pause so Comfy queue/validation settles between long prompts
        time.sleep(1.5)

    (out / "META.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done", out)


if __name__ == "__main__":
    main()
