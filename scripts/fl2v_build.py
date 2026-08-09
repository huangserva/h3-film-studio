"""H3 fl2v (first-last frame) graph builder — 表情戏/大姿态过渡专用。

用途：给两个差异大的表情/姿态态（首帧 F1 推拒 → 尾帧 F3 沉沦），H3 补中间过渡。
i2v 从单帧演不动微表情(motion 0.3)；fl2v 首尾差大 → 演出心理转变(motion 1.3-2.2)。
这是 fl2v 的正确用途，不是相近静帧的 morph 死。

用法：
    g = build_fl2v_graph(start="rsn_F1.png", end="rsn_F3.png",
                         prompt="她从推拒到沉沦...", seed=..., loras=[("HMNSFW_AIO_V2.safetensors",0.5)],
                         steps=4, turbo=True)
    POST {H3}/prompt {"prompt": g}
"""
import json

H3_UNET_FL2V = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
H3_CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
H3_VVAE = "minimax_h3_video_vae_fp16.safetensors"
H3_AVAE = "minimax_h3_audio_vae_fp32.safetensors"
H3_TURBO = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"


def build_fl2v_graph(*, start, end, prompt, seed, loras=None, steps=4, turbo=True,
                     width=480, height=864, frames=124, fps=24, prefix="fl2v/shot"):
    """start/end = ComfyUI input/ 里的文件名（480x864）。loras = [(name, strength), ...]。"""
    task = "fl2v — 首尾帧生视频(First-Last Frame)"
    dur = frames / fps
    tl = {
        "version": 4, "editMode": "global", "timelineMode": "fl2v",
        "totalFrames": frames, "frameRate": fps, "width": width, "height": height, "refMaxSize": max(width, height),
        "output": {"mode": "fixed", "longEdge": max(width, height), "width": width, "height": height,
                   "maxExportFrames": 0, "exportMode": "all", "continuityEnabled": False, "continuityOverlapFrames": 9},
        "videoClips": [], "video": {"fileName": "", "videoFile": "", "subfolder": "", "type": "input", "frames": [], "frameMap": []},
        "global": {"taskType": task, "prompt": prompt, "refs": [], "referenceVideo": {},
                   "continuousReference": False, "genImage": {"imageFile": start, "width": width, "height": height}},
        "shots": [{"id": "s0", "durationSec": dur, "prompt": prompt,
                   "startImage": {"imageFile": start, "width": width, "height": height},
                   "endImage": {"imageFile": end, "width": width, "height": height}}],
        "segments": [{"id": "s0", "start": 0, "length": frames, "frameCount": frames, "durationSec": dur,
                      "prompt": prompt, "taskType": task, "refs": [], "referenceVideo": {},
                      "genImage": {"imageFile": start, "width": width, "height": height},
                      "endImage": {"imageFile": end, "width": width, "height": height}, "negativePrompt": ""}],
        "gen": {"defaultFrameCount": frames}, "runSelectEnabled": False, "runSelection": [],
    }
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": H3_UNET_FL2V, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": H3_CLIP, "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": H3_VVAE}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": H3_AVAE}},
    }
    stack = list(loras or [])
    if turbo:
        stack = stack + [(H3_TURBO, 1.0)]
    prev = ["1", 0]
    for i, (lname, s) in enumerate(stack):
        nid = f"1{i}"
        g[nid] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": prev, "lora_name": lname, "strength_model": float(s)}}
        prev = [nid, 0]
    g["5"] = {"class_type": "MiniMaxH3Director", "inputs": {
        "model": prev, "video_vae": ["3", 0], "audio_vae": ["4", 0], "clip": ["2", 0],
        "task_type": task, "global_prompt": prompt, "bd_grp_sample": "采样设置", "cfg": 1.0, "seed": seed,
        "frame_rate": fps, "width": width, "height": height, "ref_max_size": max(width, height), "total_frames": frames,
        "timeline_data": json.dumps(tl, ensure_ascii=False), "bd_grp_advanced": "高级采样 Advanced", "steps": steps,
        "sampler": "res_multistep", "scheduler": "simple", "shift_video": 12.0, "shift_audio": 3.0,
        "bd_grp_perf": "性能 Performance", "clear_vram_between_segments": True, "export_source_images": False}}
    g["6"] = {"class_type": "CreateVideo", "inputs": {"images": ["5", 0], "fps": ["5", 2], "audio": ["5", 1], "bit_depth": 8}}
    g["7"] = {"class_type": "SaveVideo", "inputs": {"video": ["6", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return g
