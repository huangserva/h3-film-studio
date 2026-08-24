#!/bin/bash
# 一眼看清 4090 秩序（在盒上跑，或 ssh newgpu bash 这份）
echo "== 显存 =="; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
echo "== 占卡进程 =="
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | while read l; do
  pid=$(echo "$l" | cut -d, -f1)
  echo "$l | $(ps -p "$pid" -o args= 2>/dev/null | cut -c1-90)"
done
echo "== 服务 =="
systemctl --user is-active h3.service krea2.service 2>/dev/null | paste - - | sed 's/^/h3\/krea2: /'
for p in 8190 8188; do
  q=$(curl -s -m 3 "http://127.0.0.1:$p/queue" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("run",len(d.get("queue_running",[])),"pend",len(d.get("queue_pending",[])))' 2>/dev/null)
  echo ":$p → ${q:-不通}"
done
