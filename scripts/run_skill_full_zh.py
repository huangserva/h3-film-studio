#!/usr/bin/env python3
"""h3-film-studio 合规全片 runner。
顺序：preflight assert → 仅用 Qwen stills → H3 8v8a → chain/fl2v。
禁止：外源静帧、中文台词、「no subtitle」依赖、preflight 跳过。
"""
from __future__ import annotations
import json, pathlib, subprocess, sys, time, urllib.parse, urllib.request, uuid

H3 = "http://127.0.0.1:18190"
KREA = "http://127.0.0.1:18188"
W, H, FPS = 480, 864, 24
UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
TURBO = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
HM = "HMNSFW_AIO_V2.safetensors"
BOOST = "H3_Motion_Booster.safetensors"
ROOT = pathlib.Path("/tmp/skill_full")
STILLS = ROOT / "stills"
SEGS = ROOT / "segs"
WORK = ROOT / "work"
TABLE = ROOT / "shot_table.json"
PREFLIGHT = pathlib.Path.home() / ".claude/skills/h3-film-studio/scripts/preflight_continuity.py"
VIDEO_STEPS, AUDIO_STEPS = 8, 8

# 2026-08-12 黄佬：提示词一律中文（更强）。禁止整段英文。
# 体位禁写 doggy；合戏写全裸；男仅网巾短须。
MAN_ID = "男子全程戴黑色网巾、留短黑须，宽肩成熟脸，禁止变成年轻人或摘掉网巾"
WOMAN_ID = "女子全程发髻整齐、黑发挽起，成年女子面容，禁止散发现代发型"
ROOM = "同一间明代烛光卧房：红漆架子床、白纱帐、小几、铜烛台、桌上银锭，男左女右，电影级写实，空间光影全程不变。"

# end still key per shot for fl2v; chain uses only prev last
SHOTS = {
    "S1": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"全景缓推中景。两人在桌边对坐。他先把银锭推向桌心，神色冰冷逼视她，嘴唇开合说道：「武大的事，我都晓得。」"
            f"她低头看银锭，脸色发白，嘴唇闭合不说话。"
            f"他身子前倾继续说道：「你若肯从了我，这事便烂在我肚子里。」"
            f"她摇头，嘴唇开合说道：「官人饶了妾身罢，妾身实在不敢。」"
            f"他又把银锭往前推了推，说道：「跟了我，绫罗绸缎，吃穿用度，少不了你的。」"
            f"她慢慢垂下眼帘，眼神动摇。两人始终坐着，银锭始终在桌上。"
        ),
        "length": 362, "task": "I2VA", "seed": 2026081401, "lora": "turbo", "end": None,
    },
    "S2": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"男子双手撑膝缓缓站起，绕过小几走到仍坐着的女子面前站定低头看她；"
            f"她始终坐着低头绞衣角，嘴唇闭合。两人都不说话。"
        ),
        "length": 243, "task": "FL2VA", "seed": 2026081402, "lora": "turbo", "end": "S2_end.png",
    },
    "S3": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"站着的男子伸手握住坐着的女子手腕，把她轻轻拉起来站到他面前；"
            f"她轻声说道：「官人……」"
        ),
        "length": 192, "task": "FL2VA", "seed": 2026081403, "lora": "turbo", "end": "S3_end.png",
    },
    "S4": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"两人近距离站立：他揽住她的腰；她双手抵在他胸口推拒，低声说道：「使不得……」"
            f"她挣扎渐弱，手慢慢松开；他低头吻她，她闭眼未再推开。始终站立，不坐下。"
        ),
        "length": 362, "task": "I2VA", "seed": 2026081404, "lora": "turbo", "end": None,
    },
    "S5": {
        "prompt": (
            f"{ROOM}{MAN_ID}，网巾不摘。{WOMAN_ID}。"
            f"两人站立。他为她宽衣解带，衣衫层层褪去直至两人全身赤裸；"
            f"她半推半就。男只保留黑色网巾与短须，女衣物尽褪。始终站立。无长对白。"
        ),
        "length": 362, "task": "FL2VA", "seed": 2026081405, "lora": "turbo", "end": "S5_end.png",
    },
    "S6": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"两人已全身赤裸（男仅网巾短须）。他拥她退至红漆架子床边，她躺倒在床上，"
            f"他俯身亲吻爱抚。仅两位成年人类，无动物。无对白。"
        ),
        "length": 362, "task": "FL2VA", "seed": 2026081406, "lora": "sex", "end": "S6_end.png",
    },
    "S7": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"保持首帧人物与房间一致。床上正常位交合：男在上女在下，全身赤裸，男戴网巾留短须。"
            f"侧面中景，结合处在画面中下部，动作缓慢有节奏抽送，肌肤汗光。"
            f"仅两位成年人类，无动物、无宠物。镜头稳定。"
        ),
        "length": 362, "task": "FL2VA", "seed": 2026081407, "lora": "sex", "end": "S7_end.png",
    },
    "S8": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"同一床上正常位交合加快，全身赤裸，男网巾短须锁死。侧面中景，有力节奏抽送，"
            f"乳房与腰肢随动作晃动。仅两位成年人类，无动物。"
        ),
        "length": 362, "task": "I2VA", "seed": 2026081408, "lora": "sex", "end": None,
    },
    "S9": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"女上位：赤裸女子跨坐在赤裸男子身上，男仍戴黑色网巾留短须。"
            f"侧面中景，她上下起伏节奏加快。仅两位成年人类，无动物、无宠物。"
        ),
        "length": 362, "task": "FL2VA", "seed": 2026081409, "lora": "sex", "end": "S9_end.png",
    },
    "S10": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"后入式交合：女在床上双手撑床跪姿，男在其身后，两人均全身赤裸，男戴网巾留短须。"
            f"侧面中景，前后抽送节奏明确。严禁出现狗、猫或任何动物，画面中只有这两位成年人类。"
        ),
        "length": 362, "task": "FL2VA", "seed": 2026081410, "lora": "sex", "end": "S10_end.png",
    },
    "S11": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"后入式高潮段落：女跪姿男在后，全身赤裸，男网巾短须锁死，抽送加快后余势渐缓。"
            f"仅两位成年人类，严禁任何动物。"
        ),
        "length": 362, "task": "I2VA", "seed": 2026081411, "lora": "sex", "end": None,
    },
    "S12": {
        "prompt": (
            f"{ROOM}{MAN_ID}。{WOMAN_ID}。"
            f"事后余韵：两人赤裸依偎躺在床上轻喘，男仍戴网巾，嘴唇闭合，无对白。"
        ),
        "length": 243, "task": "FL2VA", "seed": 2026081412, "lora": "turbo", "end": "S12_end.png",
    },
}
ORDER = [f"S{i}" for i in range(1, 13)]


def http_json(url, data=None, method=None, timeout=120):
    body = None if data is None else json.dumps(data).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def assert_preflight():
    r = subprocess.run([sys.executable, str(PREFLIGHT), "--table", str(TABLE), "--strict-pose-change"],
                       capture_output=True, text=True)
    print(r.stdout, flush=True)
    print(r.stderr, flush=True)
    if r.returncode != 0:
        raise SystemExit(f"PREFLIGHT FAILED exit={r.returncode} — refuse H3")


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
        f"{H3}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    up = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return f"{up['subfolder']}/{up['name']}" if up.get("subfolder") else up["name"]


def build_t8(*, first, last, prompt, seed, length, task, prefix, lora):
    g = {
        "1": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "2": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                         "type": "minimax", "device": "default"}},
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "img0": {"class_type": "LoadImage", "inputs": {"image": first}},
        "5": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["4", 0], "lora_name": TURBO, "strength_model": 1.0}},
    }
    model_out = ["5", 0]
    if lora == "sex":
        g["5a"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["5", 0], "lora_name": HM, "strength_model": 0.5}}
        g["5b"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["5a", 0], "lora_name": BOOST, "strength_model": 0.7}}
        model_out = ["5b", 0]
    cond = {
        "clip": ["3", 0], "video_vae": ["1", 0], "audio_vae": ["2", 0],
        "prompt": prompt, "width": W, "height": H, "length": length,
        "task_type": task, "audio_mode": "native", "audio_denoise_strength": 1.0,
        "add_source_as_reference": False, "prompt_primary_audio_ordinal": 0,
        "strict_prompt_tags": True, "ref_image_size": "match",
        "reference_video_policy": "official_2_to_15s",
        "first_frame": ["img0", 0],
    }
    if last:
        g["img1"] = {"class_type": "LoadImage", "inputs": {"image": last}}
        cond["last_frame"] = ["img1", 0]
    g["6"] = {"class_type": "MiniMaxH3AudioConditioningT8", "inputs": cond}
    g["7"] = {"class_type": "MiniMaxH3MultiRateSamplerEXPT8", "inputs": {
        "model": model_out, "av_latent": ["6", 1],
        "video_steps": VIDEO_STEPS, "audio_steps": AUDIO_STEPS,
        "shift_video": 12.0, "shift_audio": 3.0}}
    g["8"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["9"] = {"class_type": "BasicGuider",
              "inputs": {"model": ["7", 0], "conditioning": ["6", 0]}}
    g["10"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["8", 0], "guider": ["9", 0],
        "sampler": ["7", 1], "sigmas": ["7", 2], "latent_image": ["6", 1]}}
    g["11"] = {"class_type": "MiniMaxH3AVDecodeT8", "inputs": {
        "av_latent": ["10", 0], "video_vae": ["1", 0], "audio_vae": ["2", 0]}}
    g["12"] = {"class_type": "CreateVideo",
               "inputs": {"images": ["11", 0], "fps": FPS, "audio": ["11", 1], "bit_depth": 8}}
    g["13"] = {"class_type": "SaveVideo", "inputs": {
        "video": ["12", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return g


def wait(pid, timeout_s=7200):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        hist = http_json(f"{H3}/history/{pid}", timeout=30)
        if pid in hist:
            h = hist[pid]
            st = h.get("status") or {}
            if st.get("status_str") == "error":
                for m in st.get("messages") or []:
                    if m[0] == "execution_error":
                        raise RuntimeError(f"{m[1].get('exception_type')}: {(m[1].get('exception_message') or '')[:2000]}")
                raise RuntimeError(json.dumps(st, ensure_ascii=False)[:2000])
            if st.get("completed") or h.get("outputs"):
                return h
        time.sleep(10)
    raise TimeoutError(pid)


def download_mp4(hist, dest):
    for o in (hist.get("outputs") or {}).values():
        for key in ("gifs", "videos", "images"):
            for item in o.get(key) or []:
                if not str(item.get("filename", "")).endswith(".mp4"):
                    continue
                qs = urllib.parse.urlencode({
                    "filename": item["filename"], "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output")})
                dest.write_bytes(urllib.request.urlopen(f"{H3}/view?{qs}", timeout=600).read())
                return dest
    raise RuntimeError("no mp4")


def extract_last(video, out_png):
    dur = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(video)], text=True).strip())
    t = max(0.0, dur - 0.05)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(video),
        "-vframes", "1", "-vf", f"scale={W}:{H}:flags=lanczos", str(out_png)], check=True)


def free_h3():
    try:
        http_json(f"{H3}/free", {"unload_models": False, "free_memory": True}, method="POST", timeout=30)
    except Exception as e:
        print("free warn", e, flush=True)


def free_krea():
    try:
        http_json(f"{KREA}/free", {"unload_models": False, "free_memory": True}, method="POST", timeout=30)
    except Exception as e:
        print("krea free warn", e, flush=True)


def run_one(sid, first, last, cfg):
    dest = SEGS / f"{sid}.mp4"
    if dest.exists() and dest.stat().st_size > 80_000:
        print(f"SKIP {sid}", flush=True)
        return dest
    print(f"\n===== {sid} {cfg['task']} {cfg['length']/FPS:.1f}s lora={cfg['lora']} =====", flush=True)
    free_h3()
    time.sleep(1)
    f = upload(first)
    l = upload(last) if last else None
    g = build_t8(first=f, last=l, prompt=cfg["prompt"], seed=cfg["seed"], length=cfg["length"],
                 task=cfg["task"], prefix=f"video/skill_full/{sid}", lora=cfg["lora"])
    t0 = time.time()
    resp = http_json(f"{H3}/prompt", {"prompt": g, "client_id": str(uuid.uuid4())}, timeout=60)
    if resp.get("node_errors"):
        raise RuntimeError(json.dumps(resp["node_errors"], ensure_ascii=False)[:1500])
    pid = resp["prompt_id"]
    print("queued", pid, flush=True)
    (WORK / f"{sid}_pid.txt").write_text(pid)
    hist = wait(pid)
    download_mp4(hist, dest)
    print(f"OK {sid} {time.time()-t0:.1f}s {dest.stat().st_size}b", flush=True)
    return dest


def main():
    for d in (STILLS, SEGS, WORK):
        d.mkdir(parents=True, exist_ok=True)

    # 同步 shot_table 到项目根（skill 要求）
    proj_table = pathlib.Path("/Users/serva/Desktop/jinpingmei_i2v/shot_table.json")
    proj_table.write_text(TABLE.read_text())
    assert_preflight()

    # 母图必须齐（Qwen 已出）
    need = ["S1_start.png", "S2_end.png", "S3_end.png", "S5_end.png", "S6_end.png",
            "S7_end.png", "S9_end.png", "S10_end.png", "S12_end.png"]
    for n in need:
        p = STILLS / n
        if not p.exists() or p.stat().st_size < 50_000:
            raise SystemExit(f"missing Qwen still {p} — run qwen_edit.py first")

    free_krea()  # 切换 H3 前释放 Krea
    time.sleep(2)

    prev = STILLS / "S1_start.png"
    for sid in ORDER:
        cfg = SHOTS[sid]
        end = STILLS / cfg["end"] if cfg["end"] else None
        first = prev if sid != "S1" else STILLS / "S1_start.png"
        last = end if cfg["task"] == "FL2VA" else None
        run_one(sid, first, last, cfg)
        last_png = STILLS / f"{sid}_last.png"
        extract_last(SEGS / f"{sid}.mp4", last_png)
        prev = last_png

    paths = [SEGS / f"S{i}.mp4" for i in range(1, 13)]
    lst = WORK / "concat.txt"
    lst.write_text("\n".join(f"file '{p.resolve()}'" for p in paths) + "\n")
    final = ROOT / "金瓶梅_全片_skill_8v8a.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k", str(final)], check=True)
    desk = pathlib.Path("/Users/serva/Desktop/jinpingmei_i2v/final/金瓶梅_全片_skill_8v8a.mp4")
    desk.parent.mkdir(parents=True, exist_ok=True)
    desk.write_bytes(final.read_bytes())
    dur = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(final)], text=True).strip()
    print("FINAL", final, "dur", dur, flush=True)
    print("SKILL_FULL_DONE", flush=True)


if __name__ == "__main__":
    main()
