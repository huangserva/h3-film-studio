#!/usr/bin/env python3
"""Qwen-Image-Edit-2511 身份锁（INTENT 6.1-FIX 接线，禁止文字 bible 出母图）。
image1/2 = REF_XM / REF_PJ via FluxKontextImageScale。
"""
from __future__ import annotations
import json, pathlib, time, urllib.parse, urllib.request, uuid

KREA = "http://127.0.0.1:18188"
W, H = 480, 864
KEEP = (
    "Keep faces, black wangjin hairnet, short black beard, white high-collar robe, "
    "and neat black updo EXACTLY identical to the reference pictures. "
    "Mouths FIRMLY CLOSED, lips pressed together, absolutely not speaking."
)
ROOM = (
    "in the same warm candlelit Ming-dynasty bedchamber: red lacquer canopy bed with white gauze curtains, "
    "bronze candlestick, low table, silver ingot on table, man left woman right, cinematic photoreal"
)


def http_json(url, data=None, method=None, timeout=120):
    body = None if data is None else json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json; charset=utf-8"} if data is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def upload(path: pathlib.Path) -> str:
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
        f"{KREA}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    up = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return f"{up['subfolder']}/{up['name']}" if up.get("subfolder") else up["name"]


def build(refs: list[str], prompt: str, seed: int, prefix: str):
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "qwen_image_edit_2511_fp8_lightning_4steps.safetensors", "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "msaf": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["unet", 0], "shift": 3.1}},
        "cfgn": {"class_type": "CFGNorm", "inputs": {"model": ["msaf", 0], "strength": 1.0, "pre_cfg": False}},
        "img1": {"class_type": "LoadImage", "inputs": {"image": refs[0]}},
        "scale": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["img1", 0]}},
    }
    pos_in = {"clip": ["clip", 0], "vae": ["vae", 0], "image1": ["scale", 0], "prompt": prompt}
    neg_in = {"clip": ["clip", 0], "vae": ["vae", 0], "image1": ["scale", 0], "prompt": ""}
    if len(refs) > 1:
        g["img2"] = {"class_type": "LoadImage", "inputs": {"image": refs[1]}}
        pos_in["image2"] = ["img2", 0]
        neg_in["image2"] = ["img2", 0]
    g["pos"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": pos_in}
    g["neg"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": neg_in}
    g["posref"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                   "inputs": {"conditioning": ["pos", 0], "reference_latents_method": "index_timestep_zero"}}
    g["negref"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                   "inputs": {"conditioning": ["neg", 0], "reference_latents_method": "index_timestep_zero"}}
    g["enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["scale", 0], "vae": ["vae", 0]}}
    g["ks"] = {"class_type": "KSampler", "inputs": {
        "model": ["cfgn", 0], "positive": ["posref", 0], "negative": ["negref", 0],
        "latent_image": ["enc", 0], "seed": seed, "steps": 4, "cfg": 1.0,
        "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
    g["dec"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks", 0], "vae": ["vae", 0]}}
    g["save"] = {"class_type": "SaveImage", "inputs": {"images": ["dec", 0], "filename_prefix": prefix}}
    return g


def wait(pid, timeout_s=600):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        hist = http_json(f"{KREA}/history/{pid}", timeout=30)
        if pid in hist:
            h = hist[pid]
            st = h.get("status") or {}
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st, ensure_ascii=False)[:1500])
            if st.get("completed") or h.get("outputs"):
                return h
        time.sleep(2)
    raise TimeoutError(pid)


def download(hist, dest: pathlib.Path):
    for o in (hist.get("outputs") or {}).values():
        for img in o.get("images") or []:
            qs = urllib.parse.urlencode({
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")})
            data = urllib.request.urlopen(f"{KREA}/view?{qs}", timeout=120).read()
            dest.write_bytes(data)
            return dest
    raise RuntimeError("no image")


def free():
    try:
        http_json(f"{KREA}/free", {"unload_models": False, "free_memory": True}, method="POST", timeout=30)
    except Exception as e:
        print("free warn", e, flush=True)


def gen(refs_paths: list[pathlib.Path], prompt: str, seed: int, dest: pathlib.Path, prefix: str):
    if dest.exists() and dest.stat().st_size > 50_000:
        print(f"SKIP still {dest.name}", flush=True)
        return dest
    free()
    time.sleep(0.5)
    refs = [upload(p) for p in refs_paths]
    print("qwen refs", refs, "->", dest.name, flush=True)
    g = build(refs, prompt, seed, prefix)
    r = http_json(f"{KREA}/prompt", {"prompt": g, "client_id": str(uuid.uuid4())}, timeout=60)
    if r.get("node_errors"):
        raise RuntimeError(json.dumps(r["node_errors"], ensure_ascii=False)[:1500])
    h = wait(r["prompt_id"])
    download(h, dest)
    print(f"OK still {dest} {dest.stat().st_size}b", flush=True)
    return dest


# 姿态状态机母图（全部 Qwen+REF，闭嘴）
STILL_PROMPTS = {
    "S1_start": (
        f"A cinematic WIDE two-shot {ROOM}. The man in Picture 1 sits on the LEFT at a low table, "
        f"one hand near a silver ingot, cold stare; the woman in Picture 2 sits on the RIGHT, pale, looking at the ingot. "
        f"Both mouths firmly closed. {KEEP}"
    ),
    "S2_end": (
        f"A cinematic MEDIUM shot {ROOM}. The man in Picture 1 STANDS beside the table on the LEFT looking down; "
        f"the woman in Picture 2 still SITS on the RIGHT with head lowered. Both mouths firmly closed. {KEEP}"
    ),
    "S3_end": (
        f"A cinematic MEDIUM two-shot {ROOM}. The man in Picture 1 and the woman in Picture 2 STAND close face to face; "
        f"he holds her wrist lightly. Both mouths firmly closed. {KEEP}"
    ),
    "S5_end": (
        f"A cinematic MEDIUM two-shot {ROOM}. The man in Picture 1 and the woman in Picture 2 STAND close; "
        f"her white robe half open on shoulders (still modest), he helps undress her. "
        f"His black wangjin still on. Both mouths firmly closed. {KEEP}"
    ),
    "S6_end": (
        f"A cinematic MEDIUM shot {ROOM}. The woman in Picture 2 lies back on the red canopy bed; "
        f"the man in Picture 1 leans above her kissing her neck. His black wangjin and short beard clearly visible. "
        f"Both mouths closed except soft kiss. {KEEP}"
    ),
    "S7_end": (
        f"A cinematic MEDIUM side-view shot {ROOM}. Missionary on the bed: man in Picture 1 above woman in Picture 2, "
        f"his black wangjin and short beard clearly visible, her neat updo locked. Intimate contact, mouths closed. {KEEP}"
    ),
    "S9_end": (
        f"A cinematic MEDIUM side-view shot {ROOM}. Cowgirl: woman in Picture 2 straddles man in Picture 1 on the bed; "
        f"his black wangjin and short beard locked, her neat updo locked. Mouths closed. {KEEP}"
    ),
    "S10_end": (
        f"A cinematic MEDIUM side-view shot {ROOM}. Doggy: woman in Picture 2 on hands and knees, man in Picture 1 behind; "
        f"his black wangjin and short beard locked, her neat updo locked. Mouths closed. {KEEP}"
    ),
    "S12_end": (
        f"A cinematic MEDIUM shot {ROOM}. Afterglow: man in Picture 1 and woman in Picture 2 lie embracing on the bed, "
        f"calm breath. His black wangjin still on. Both mouths firmly closed. {KEEP}"
    ),
}


def main():
    root = pathlib.Path("/tmp/skill_full")
    stills = root / "stills"
    stills.mkdir(parents=True, exist_ok=True)
    ref_xm = stills / "REF_XM.png"
    ref_pj = stills / "REF_PJ.png"
    if not ref_xm.exists() or ref_xm.stat().st_size < 1000:
        import shutil
        shutil.copy("/Users/serva/Desktop/jinpingmei_i2v/kw/REF_XM.png", ref_xm)
        shutil.copy("/Users/serva/Desktop/jinpingmei_i2v/kw/REF_PJ.png", ref_pj)

    dual = [ref_xm, ref_pj]
    seed0 = 2026081300
    for i, (name, prompt) in enumerate(STILL_PROMPTS.items()):
        dest = stills / f"{name}.png"
        gen(dual, prompt, seed0 + i * 7, dest, f"skill_full/{name}")
    print("QWEN_STILLS_DONE", flush=True)


if __name__ == "__main__":
    main()
