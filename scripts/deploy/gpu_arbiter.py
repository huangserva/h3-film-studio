#!/usr/bin/env python3
"""4090 主客仲裁器（2026-08-15 部署定版）。

秩序：H3(:8190)=主人常驻；Krea2(:8188)=客人，用完即走。
实测：Qwen-Edit 出图峰值 30.6GB，H3 长镜峰值 ~26.6GB —— 同时跑必撞车，必须错峰。

用法（所有出图脚本都该套这个）:
    from gpu_arbiter import krea_slot
    with krea_slot():          # 等 H3 空闲 → 进入
        ...提交 8188 出图...
    # 退出时自动 POST /free，显存还给 H3
"""
import json
import time
import urllib.request
from contextlib import contextmanager

H3 = "http://127.0.0.1:8190"
KREA = "http://127.0.0.1:8188"


def _get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def _post(url, body, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=timeout).read()


def h3_busy() -> bool:
    try:
        q = _get(f"{H3}/queue")
        return bool(q.get("queue_running") or q.get("queue_pending"))
    except Exception:
        return False          # H3 不在线 = 不算忙


def krea_free():
    try:
        _post(f"{KREA}/free", {"unload_models": True, "free_memory": True})
    except Exception:
        pass


@contextmanager
def krea_slot(poll_s: int = 15, max_wait_s: int = 3600):
    """客人进场：等 H3 空闲；退场：无条件归还显存。"""
    waited = 0
    while h3_busy():
        if waited == 0:
            print("[arbiter] H3 在跑，客人排队…", flush=True)
        time.sleep(poll_s)
        waited += poll_s
        if waited >= max_wait_s:
            raise TimeoutError(f"等 H3 空闲超过 {max_wait_s}s")
    try:
        yield
    finally:
        krea_free()
        print("[arbiter] 客人退场，显存已归还", flush=True)


if __name__ == "__main__":
    print("H3 busy:", h3_busy())
    krea_free()
    print("krea freed")
