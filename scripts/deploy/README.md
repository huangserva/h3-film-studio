# 4090 部署档案（2026-08-15 定版：H3 独占 + Krea 客人）

## 秩序

| 角色 | 服务 | 端口 | 模式 | 显存 |
|---|---|---|---|---|
| **主人** | `h3.service` | :8190 | 常驻（lowvram + vram-headroom 8 + **--use-sage-attention**，2026-08-24 开启，白拿 24%） | 空闲 0.7G / 长镜峰值 ~26.6G |
| **客人** | `krea2.service` | :8188 | `--lowvram`，**用完即走**（arbiter 自动 /free） | 空闲 ~0.6G / Qwen-Edit 峰值 **30.6G** |
| 已下架 | `qwen38-q4-20g` + `frpc-qwen38` | :8080 | stop + disable（2026-08-15 黄佬拍板） | 原占 20G |

峰值数字说明为什么必须错峰：30.6 + 26.6 > 48。**出图一律走 `gpu_arbiter.krea_slot()`。**

## 关键事实

- Krea2 的旧 python 环境（torch 2.6.0）已丢失；现用 **H3 的 .venv（torch 2.11.0+cu128）** 跑 Krea2 检出，1757 节点全载，Qwen-Edit 验证通过。
- 两 unit 均 user-systemd（`~/.config/systemd/user/`），`Restart=on-failure`，开机自启。

## 常用命令

```bash
ssh newgpu 'bash ~/gpu_status.sh'                     # 看秩序
ssh newgpu 'systemctl --user restart h3 krea2'        # 重启双服务
ssh newgpu 'systemctl --user start qwen38-q4-20g frpc-qwen38'   # 恢复 Qwen（需要时）
```

## 2026-08-24 变更记录

- **Qwen 下架**（黄佬拍板）：`qwen38-q4-20g` + `frpc-qwen38` stop+disable，释放 20G。
- **Sage 开启**：h3.service 加 `--use-sage-attention`，启动日志确认 `Using sage attention`，T8 烟测通过（motion 0.67 与基准一致）。
- **8188 老实例已死**：其 torch 2.6.0 环境丢失。新 krea2.service 用 H3 的 .venv（torch 2.11/cu128）跑 `ComfyUI_krea2_latest` 检出，1757 节点全载。**记忆里"生产的 8188 老实例不动它"一条已过时。**
- 盒上另有 `ref2va_pruned_int8_convrot`（19.5G）→ r2v 长镜可用（定版配方：r2v 管长镜，fl2v 只做接缝）。
- 注意：定版配方的"turbo 4 步"早于 T8 音频发现——**有声镜头一律 T8 multi-rate（视频 4 步 + 音频 ≥8 步）**，纯 turbo 4 步会糊音频。
