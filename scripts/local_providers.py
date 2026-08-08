"""Local ComfyUI providers for h3-film-studio.

Plugs the MiniMax-H3 (video) and Krea2 (image) local ComfyUI engines into the
xyz pipeline's provider dispatch. No cloud API — everything runs against a
local ComfyUI (default via SSH tunnel 18190/18188, or 8190/8188 on the box).

Contract (matches video_gen.py / image_gen.py dispatch):
  video:  async video_h3(provider_name, image_path, prompt, output, *, duration,
                         last_frame_path, video_references, cfg, provider_config,
                         get_session, download, normalize_usage) -> bool
  image:  async image_krea(prompt, output, *, cfg, provider_config, get_session,
                          download, storyboard, characters_in_shot, scene_image) -> bool

The provider maps xyz's video_references usage protocol onto H3's native modes:
  first_frame only            -> i2v
  first_frame + target_state  -> fl2v (first+last frame)
  many reference_* subjects    -> r2v (multi-reference)  [P2; P1 falls back to i2v]
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import aiohttp

logger = logging.getLogger(__name__)

# ---- H3 constants (match adult skill's h3_i2v_shot.py, validated on the box) ----
H3_UNET_I2V = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
H3_UNET_R2V = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
H3_CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
H3_VVAE = "minimax_h3_video_vae_fp16.safetensors"
H3_AVAE = "minimax_h3_audio_vae_fp32.safetensors"
H3_TURBO = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"

# 17k+5 frame grid (H3 align_frame_count); training range 37..362, 15s cap
FRAME_GRID = [37 + 17 * k for k in range(0, 20)]  # 37,54,...,360 ; plus 362 tail


def frames_for_duration(sec: float, fps: int = 24) -> int:
    target = max(1, round(sec * fps))
    grid = FRAME_GRID + [362]
    return min(grid, key=lambda g: abs(g - target))


def _seed_for(output: Path, base: int = 20260808) -> int:
    return base + (abs(hash(output.name)) % 900000)


# ---------------------------- ComfyUI async helpers ----------------------------

async def _comfy_upload(session: aiohttp.ClientSession, endpoint: str, path: Path) -> str:
    """Upload an image to ComfyUI input/, return the server-side filename."""
    form = aiohttp.FormData()
    form.add_field("image", path.read_bytes(), filename=path.name, content_type="image/png")
    form.add_field("overwrite", "true")
    async with session.post(f"{endpoint}/upload/image", data=form,
                            timeout=aiohttp.ClientTimeout(total=180)) as r:
        r.raise_for_status()
        up = await r.json()
    return f"{up['subfolder']}/{up['name']}" if up.get("subfolder") else up["name"]


async def _comfy_submit(session: aiohttp.ClientSession, endpoint: str, graph: dict) -> str:
    async with session.post(f"{endpoint}/prompt",
                            json={"prompt": graph, "client_id": str(uuid.uuid4())},
                            timeout=aiohttp.ClientTimeout(total=60)) as r:
        r.raise_for_status()
        data = await r.json()
    if data.get("node_errors"):
        raise RuntimeError(f"comfy node_errors: {json.dumps(data['node_errors'])[:800]}")
    return data["prompt_id"]


async def _comfy_poll(session: aiohttp.ClientSession, endpoint: str, pid: str,
                      *, interval: float, max_attempts: int) -> dict:
    import asyncio
    for _ in range(max_attempts):
        await asyncio.sleep(interval)
        async with session.get(f"{endpoint}/history/{pid}",
                               timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                continue
            hist = await r.json()
        if pid not in hist:
            continue
        h = hist[pid]
        st = h.get("status") or {}
        if st.get("status_str") == "error":
            for m in st.get("messages") or []:
                if m[0] == "execution_error":
                    raise RuntimeError(f"{m[1].get('exception_type')}: "
                                       f"{(m[1].get('exception_message') or '')[:800]}")
            raise RuntimeError(json.dumps(st, ensure_ascii=False)[:800])
        if st.get("completed") or h.get("outputs"):
            return h
    raise TimeoutError(pid)


def _first_output(h: dict, keys: tuple[str, ...]) -> dict | None:
    for _n, out in (h.get("outputs") or {}).items():
        for key in keys:
            items = out.get(key) or []
            if items:
                return items[0]
    return None


def _view_url(endpoint: str, item: dict) -> str:
    qs = urllib.parse.urlencode({
        "filename": item["filename"],
        "subfolder": item.get("subfolder", ""),
        "type": item.get("type", "output"),
    })
    return f"{endpoint}/view?{qs}"


# ------------------------------- H3 video graph -------------------------------

def build_h3_i2v_graph(*, start_name: str, prompt: str, width: int, height: int,
                       frames: int, fps: int, seed: int,
                       loras: list[tuple[str, float]], steps: int, prefix: str) -> dict:
    task = "i2v — 图生视频(Image to Video)"
    dur = frames / fps
    timeline = {
        "version": 4, "editMode": "global", "timelineMode": "i2v",
        "totalFrames": frames, "frameRate": fps, "width": width, "height": height,
        "refMaxSize": max(width, height),
        "output": {"mode": "fixed", "longEdge": max(width, height), "width": width, "height": height,
                   "maxExportFrames": 0, "exportMode": "all",
                   "continuityEnabled": False, "continuityOverlapFrames": 9},
        "videoClips": [],
        "video": {"fileName": "", "videoFile": "", "subfolder": "", "type": "input",
                  "frames": [], "frameMap": []},
        "global": {"taskType": task, "prompt": prompt, "refs": [], "referenceVideo": {},
                   "continuousReference": False,
                   "genImage": {"imageFile": start_name, "width": width, "height": height}},
        "shots": [{"id": "s0", "durationSec": dur, "prompt": prompt,
                   "startImage": {"imageFile": start_name, "width": width, "height": height}}],
        "segments": [{"id": "s0", "start": 0, "length": frames, "frameCount": frames,
                      "durationSec": dur, "prompt": prompt, "taskType": task,
                      "refs": [], "referenceVideo": {},
                      "genImage": {"imageFile": start_name, "width": width, "height": height},
                      "negativePrompt": ""}],
        "gen": {"defaultFrameCount": frames}, "runSelectEnabled": False, "runSelection": [],
    }
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": H3_UNET_I2V, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": H3_CLIP, "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": H3_VVAE}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": H3_AVAE}},
    }
    prev = ["1", 0]
    for i, (lname, s) in enumerate(loras):
        nid = f"1{i}"
        g[nid] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": prev, "lora_name": lname, "strength_model": float(s)}}
        prev = [nid, 0]
    g["5"] = {"class_type": "MiniMaxH3Director", "inputs": {
        "model": prev, "video_vae": ["3", 0], "audio_vae": ["4", 0], "clip": ["2", 0],
        "task_type": task, "global_prompt": prompt, "bd_grp_sample": "采样设置",
        "cfg": 1.0, "seed": seed, "frame_rate": fps, "width": width, "height": height,
        "ref_max_size": max(width, height), "total_frames": frames,
        "timeline_data": json.dumps(timeline, ensure_ascii=False),
        "bd_grp_advanced": "高级采样 Advanced", "steps": steps,
        "sampler": "res_multistep", "scheduler": "simple",
        "shift_video": 12.0, "shift_audio": 3.0, "bd_grp_perf": "性能 Performance",
        "clear_vram_between_segments": True, "export_source_images": False}}
    g["6"] = {"class_type": "CreateVideo", "inputs": {"images": ["5", 0], "fps": ["5", 2],
                                                       "audio": ["5", 1], "bit_depth": 8}}
    g["7"] = {"class_type": "SaveVideo", "inputs": {"video": ["6", 0], "filename_prefix": prefix,
                                                     "format": "auto", "codec": "auto"}}
    return g


def _loras_from_cfg(pcfg: dict) -> list[tuple[str, float]]:
    """Read the LoRA stack from provider config; supports NSFW profile + turbo."""
    out: list[tuple[str, float]] = []
    for entry in pcfg.get("loras", []) or []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            out.append((str(entry[0]), float(entry[1])))
        elif isinstance(entry, dict):
            out.append((str(entry["name"]), float(entry.get("strength", 1.0))))
    if pcfg.get("turbo", True):
        steps = int(pcfg.get("steps", 4))
        out.append((H3_TURBO, 1.0))
        return out, steps
    return out, int(pcfg.get("steps", 20))


async def video_h3(
    provider_name: str,
    image_path: Path,
    prompt: str,
    output: Path,
    *,
    duration: int = 10,
    last_frame_path: Path | None = None,
    video_references: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any],
    provider_config: Callable[[str], dict[str, Any]],
    get_session: Callable[[], Awaitable[aiohttp.ClientSession]],
    download: Callable[[aiohttp.ClientSession, str, Path], Awaitable[bool]],
    normalize_usage: Callable[[Any], str],
) -> bool:
    """H3 local i2v provider. Maps video_references -> H3 mode (P1: i2v)."""
    pcfg = provider_config(provider_name) or {}
    endpoint = str(pcfg.get("endpoint", "http://127.0.0.1:18190")).rstrip("/")
    width = int(pcfg.get("width", 480))
    height = int(pcfg.get("height", 864))
    fps = int(pcfg.get("fps", 24))
    frames = frames_for_duration(duration, fps)
    loras, steps = _loras_from_cfg(pcfg)

    # choose the first_frame source
    start_path = image_path
    for ref in (video_references or []):
        if normalize_usage(ref.get("usage")) == "first_frame" and isinstance(ref.get("path"), Path):
            if ref["path"].exists():
                start_path = ref["path"]
                break
    if not start_path or not Path(start_path).exists():
        logger.warning("video_h3: no valid first_frame image, abort")
        return False

    try:
        session = await get_session()
        start_name = await _comfy_upload(session, endpoint, Path(start_path))
        prefix = f"h3film/{output.stem}"
        graph = build_h3_i2v_graph(
            start_name=start_name, prompt=prompt, width=width, height=height,
            frames=frames, fps=fps, seed=_seed_for(output), loras=loras, steps=steps, prefix=prefix,
        )
        logger.info(f"video_h3: i2v {width}x{height} {frames}f steps={steps} "
                    f"loras={[l[0].split('.')[0] for l in loras]} -> {output.name}")
        pid = await _comfy_submit(session, endpoint, graph)
        h = await _comfy_poll(session, endpoint, pid,
                              interval=float(pcfg.get("poll_interval", 6)),
                              max_attempts=int(pcfg.get("poll_max_attempts", 120)))
        item = _first_output(h, ("gifs", "videos", "images"))
        if not item:
            logger.warning("video_h3: no output in history")
            return False
        return await download(session, _view_url(endpoint, item), output)
    except (aiohttp.ClientError, RuntimeError, TimeoutError, KeyError, OSError) as e:
        logger.warning(f"video_h3 error: {e}")
        return False


# ------------------------------- Krea image graph -----------------------------

def build_krea_graph(*, prompt: str, seed: int, width: int, height: int,
                     lora: str, strength: float, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "krea2_turbo_fp8.safetensors", "weight_dtype": "default"}},
        "13": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "40": {"class_type": "LoraLoaderModelOnly",
               "inputs": {"model": ["1", 0], "lora_name": str(lora), "strength_model": float(strength)}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": str(prompt), "clip": ["13", 0]}},
        "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "10": {"class_type": "EmptyLatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
        "2": {"class_type": "KSampler",
              "inputs": {"model": ["40", 0], "seed": int(seed), "steps": 8, "cfg": 1.0,
                         "sampler_name": "euler_ancestral", "scheduler": "sgm_uniform",
                         "positive": ["6", 0], "negative": ["8", 0], "latent_image": ["10", 0], "denoise": 1.0}},
        "3": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["4", 0]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": str(prefix)}},
    }


async def image_krea(
    prompt: str,
    output: Path,
    *,
    cfg: dict[str, Any],
    provider_config: Callable[[str], dict[str, Any]],
    get_session: Callable[[], Awaitable[aiohttp.ClientSession]],
    download: Callable[[aiohttp.ClientSession, str, Path], Awaitable[bool]],
    storyboard: dict[str, Any] | None = None,
    characters_in_shot: list[str] | None = None,
    scene_image: Path | None = None,
) -> bool:
    """Krea2 local t2i provider (P1: text-to-image; i2i from character ref = P2)."""
    pcfg = provider_config("local_krea") or {}
    endpoint = str(pcfg.get("endpoint", "http://127.0.0.1:18188")).rstrip("/")
    width = int(pcfg.get("width", 720))
    height = int(pcfg.get("height", 1280))
    lora = str(pcfg.get("lora", "krea2_lora 通行证刀斧手版.safetensors"))
    strength = float(pcfg.get("lora_strength", 0.5))
    try:
        session = await get_session()
        prefix = f"h3film/{output.stem}"
        graph = build_krea_graph(prompt=prompt, seed=_seed_for(output), width=width, height=height,
                                 lora=lora, strength=strength, prefix=prefix)
        logger.info(f"image_krea: t2i {width}x{height} lora={lora.split('.')[0]}@{strength} -> {output.name}")
        pid = await _comfy_submit(session, endpoint, graph)
        h = await _comfy_poll(session, endpoint, pid,
                              interval=float(pcfg.get("poll_interval", 1.5)),
                              max_attempts=int(pcfg.get("poll_max_attempts", 120)))
        item = _first_output(h, ("images",))
        if not item:
            logger.warning("image_krea: no output in history")
            return False
        return await download(session, _view_url(endpoint, item), output)
    except (aiohttp.ClientError, RuntimeError, TimeoutError, KeyError, OSError) as e:
        logger.warning(f"image_krea error: {e}")
        return False
