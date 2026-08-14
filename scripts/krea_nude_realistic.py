#!/usr/bin/env python3
"""合戏母图 v3：真实交欢感（非摆拍写真）
Krea2 + 刀斧手；中文；S5 master → i2i 统一肤色/脸。
"""
from __future__ import annotations
import json, pathlib, statistics, time, urllib.parse, urllib.request, uuid
from PIL import Image, ImageDraw, ImageFont

KREA = "http://127.0.0.1:18188"
W, H = 480, 864
LORA = "krea2_lora 通行证刀斧手版.safetensors"
OUT = pathlib.Path("/tmp/skill_full/stills_krea_v3")
STILLS = pathlib.Path("/tmp/skill_full/stills")
DESK = pathlib.Path("/Users/serva/Desktop/jinpingmei_i2v/full_8v8a/qwen_nude_s5s12")
CONTACT = pathlib.Path("/Users/serva/Desktop/jinpingmei_i2v/full_8v8a/CONTACT_合戏母图S5S12_v3.jpg")

# 身份：统一，但禁止瓷白、禁止看镜头
ID = (
    "同一对成年男女。"
    "男：三十五岁明代商贾，黑色网巾束发、短黑须、浓眉宽肩，健康偏暖肤色，全身赤裸仅留网巾短须。"
    "女：同一成年东亚女子，鹅蛋脸柳眉，黑发略乱挽髻无精致红花，健康东亚暖肤色，禁止死白瓷白，全身赤裸。"
)
REAL = (
    "真实交欢现场感，不是写真摆拍，不是海报构图。"
    "烛光偏暗、暗部多、床单皱乱。"
    "两人互视或闭眼或脸埋肩颈，绝不看镜头、不摆表情看相机。"
    "有真实体重压迫与皮肉贴合、汗湿、呼吸急促感。"
    "仅两位成年人类，无第三人，无动物。"
)

# 各镜：写「正在发生」+ 不完美镜头
POSES = {
    "S5_end": (
        f"{ID}{REAL}"
        "明代烛光卧房，红漆架子床在后。两人刚宽衣完毕赤身站在床边，身体几乎贴在一起，"
        "他低头贴着她额侧，她侧脸靠他肩，手还搭在他腰上，衣物散落床脚。"
        "半身偏近景，略侧机位，脚和头顶可出画，不要全身站桩海报。"
    ),
    "S6_end": (
        f"{ID}{REAL}"
        "她仰躺在凌乱床单上，他俯身压在她身上正在亲吻她脖颈与嘴唇，"
        "一只手抓着床单，她一条腿抬起勾住他腰。略低机位半身，暗烛光，"
        "脸贴在一起不看镜头，像正在前戏不是摆姿势。"
    ),
    "S7_end": (
        f"{ID}{REAL}"
        "正常位交合进行中：他在上压着她，正缓慢有力地抽送，她仰躺双腿分开夹他腰，"
        "手抓他背或床单，脸偏向一侧闭眼或皱眉喘息，他脸埋她颈侧。"
        "略侧低机位，只拍到腰腹到肩的半身，有皮肉挤压形变与汗。"
        "禁止跪姿后入，禁止对镜头。"
    ),
    "S9_end": (
        f"{ID}{REAL}"
        "女上位进行中：她面对面跨坐在他骨盆上正在上下起伏，双手撑他胸口或床，"
        "头发有些散，低头看他或闭眼，绝不看镜头；他仰卧抓她腰，网巾仍在。"
        "侧面略低半身，能看出她坐在他身上而非站在他背后。床单乱。"
    ),
    "S10_end": (
        f"{ID}{REAL}"
        "后入式进行中：她双手撑在凌乱床单上跪伏，他在身后抓她腰正前后抽送，"
        "她侧脸贴着枕头喘息不看镜头，他低头看她背。略侧机位半身，暗光。"
        "只有这两人，严禁狗或任何动物。"
    ),
    "S12_end": (
        f"{ID}{REAL}"
        "事后余韵：两人赤裸并排侧躺在皱乱床单里，他仍戴网巾，她靠在他胸口，"
        "都闭着眼或半闭，轻喘，没有摆姿势。近景半身，烛光弱，真实疲惫感。"
    ),
}
ORDER = list(POSES.keys())


def http_json(url, data=None, method=None, timeout=120):
    body = None if data is None else json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json; charset=utf-8"} if data is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def free():
    try:
        http_json(f"{KREA}/free", {"unload_models": False, "free_memory": True}, method="POST", timeout=30)
    except Exception as e:
        print("free", e, flush=True)


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
        time.sleep(1.5)
    raise TimeoutError(pid)


def download(hist, dest: pathlib.Path):
    for o in (hist.get("outputs") or {}).values():
        for img in o.get("images") or []:
            qs = urllib.parse.urlencode({
                "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output")})
            dest.write_bytes(urllib.request.urlopen(f"{KREA}/view?{qs}", timeout=120).read())
            return dest
    raise RuntimeError("no image")


def gen(g, dest: pathlib.Path):
    free()
    time.sleep(0.4)
    r = http_json(f"{KREA}/prompt", {"prompt": g, "client_id": str(uuid.uuid4())}, timeout=60)
    if r.get("node_errors"):
        raise RuntimeError(json.dumps(r["node_errors"], ensure_ascii=False)[:1200])
    download(wait(r["prompt_id"]), dest)
    return dest


def build_t2i(prompt, seed, prefix, strength=0.82):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "krea2_turbo_fp8.safetensors", "weight_dtype": "default"}},
        "13": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "40": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": LORA, "strength_model": float(strength)}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["13", 0]}},
        "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "10": {"class_type": "EmptyLatentImage", "inputs": {"width": W, "height": H, "batch_size": 1}},
        "2": {"class_type": "KSampler", "inputs": {
            "model": ["40", 0], "seed": int(seed), "steps": 8, "cfg": 1.0,
            "sampler_name": "euler_ancestral", "scheduler": "sgm_uniform",
            "positive": ["6", 0], "negative": ["8", 0], "latent_image": ["10", 0], "denoise": 1.0}},
        "3": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["4", 0]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": prefix}},
    }


def build_i2i(prompt, seed, prefix, image_name, strength=0.8, denoise=0.58):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "krea2_turbo_fp8.safetensors", "weight_dtype": "default"}},
        "13": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "40": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": LORA, "strength_model": float(strength)}},
        "img": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "enc": {"class_type": "VAEEncode", "inputs": {"pixels": ["img", 0], "vae": ["4", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["13", 0]}},
        "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "2": {"class_type": "KSampler", "inputs": {
            "model": ["40", 0], "seed": int(seed), "steps": 8, "cfg": 1.0,
            "sampler_name": "euler_ancestral", "scheduler": "sgm_uniform",
            "positive": ["6", 0], "negative": ["8", 0], "latent_image": ["enc", 0],
            "denoise": float(denoise)}},
        "3": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["4", 0]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["3", 0], "filename_prefix": prefix}},
    }


def skin_luma(path: pathlib.Path) -> float:
    im = Image.open(path).convert("RGB").resize((120, 216))
    w, h = im.size
    crop = im.crop((int(w * 0.2), int(h * 0.1), int(w * 0.8), int(h * 0.55)))
    px = list(crop.getdata())
    cands = [c for c in px if 60 < c[0] < 250 and c[1] > 40 and c[0] >= c[2] - 15]
    if len(cands) < 30:
        cands = px
    return statistics.mean(0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] for c in cands)


def publish(name: str, path: pathlib.Path):
    data = path.read_bytes()
    OUT.mkdir(parents=True, exist_ok=True)
    STILLS.mkdir(parents=True, exist_ok=True)
    DESK.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.png").write_bytes(data)
    (STILLS / f"{name}.png").write_bytes(data)
    (DESK / f"{name}.png").write_bytes(data)


def contact():
    labels = {
        "S5_end": "S5 宽衣后", "S6_end": "S6 前戏", "S7_end": "S7 正常位",
        "S9_end": "S9 女上位", "S10_end": "S10 后入", "S12_end": "S12 余韵",
    }
    cell_w, cell_h, label_h, pad, cols = 280, 504, 40, 8, 3
    rows = 2
    Wc = cols * cell_w + (cols + 1) * pad
    Hc = 48 + rows * (cell_h + label_h + pad) + pad
    canvas = Image.new("RGB", (Wc, Hc), (20, 20, 24))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 17)
        font_t = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 20)
    except Exception:
        font = font_t = ImageFont.load_default()
    draw.text((pad, 12), "合戏母图 v3 真实交欢感（刀斧手+i2i）", fill=(240, 240, 240), font=font_t)
    L0 = skin_luma(OUT / "S5_end.png")
    for i, name in enumerate(ORDER):
        p = OUT / f"{name}.png"
        r, c = divmod(i, cols)
        x = pad + c * (cell_w + pad)
        y = 48 + r * (cell_h + label_h + pad)
        im = Image.open(p).convert("RGB").resize((cell_w, cell_h), Image.Resampling.LANCZOS)
        canvas.paste(im, (x, y))
        L = skin_luma(p)
        draw.rectangle([x, y + cell_h, x + cell_w, y + cell_h + label_h], fill=(36, 36, 44))
        draw.text((x + 6, y + cell_h + 10), f"{labels[name]} L={L:.0f} d={abs(L-L0):.0f}", fill=(220, 220, 220), font=font)
    canvas.save(CONTACT, quality=92)
    pathlib.Path("/tmp/skill_full/CONTACT_合戏母图S5S12_v3.jpg").write_bytes(CONTACT.read_bytes())
    print("CONTACT", CONTACT, flush=True)


def main():
    print("Krea2+刀斧手 v3 真实交欢感", flush=True)
    master_seed = 2026081901
    master = OUT / "S5_end.png"
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== S5 master t2i ===", flush=True)
    gen(build_t2i(POSES["S5_end"], master_seed, "krea_v3/S5", 0.82), master)
    publish("S5_end", master)
    L0 = skin_luma(master)
    print(f"S5 L={L0:.1f}", flush=True)
    master_name = upload(master)
    print("master uploaded", master_name, flush=True)

    dens = {"S6_end": 0.56, "S7_end": 0.60, "S9_end": 0.60, "S10_end": 0.58, "S12_end": 0.52}
    for i, name in enumerate(ORDER[1:], 1):
        dest = OUT / f"{name}.png"
        seed = master_seed + i * 19
        dn = dens[name]
        print(f"=== {name} i2i dn={dn} ===", flush=True)
        for attempt in range(3):
            gen(build_i2i(POSES[name], seed + attempt * 37, f"krea_v3/{name}_{attempt}",
                          master_name, 0.8, dn), dest)
            L = skin_luma(dest)
            d = abs(L - L0)
            print(f"  try{attempt} L={L:.1f} d={d:.1f}", flush=True)
            if d <= 16:
                break
            dn = min(0.68, dn + 0.04)
            print("  skin re-roll", flush=True)
        publish(name, dest)

    print("\n=== SKIN ===", flush=True)
    for name in ORDER:
        L = skin_luma(OUT / f"{name}.png")
        print(f"  {name} L={L:.1f} d={abs(L-L0):.1f}", flush=True)
    contact()
    print("KREA_V3_REAL_DONE", flush=True)
    print("preview:", DESK, flush=True)
    print("contact:", CONTACT, flush=True)


if __name__ == "__main__":
    main()
