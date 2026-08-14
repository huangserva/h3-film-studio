# 衔接硬门（Continuity Gate）— 禁止跳过

> **存在理由**：skill 里早就写了「起态=上镜终态」「chain / fl2v」，但 agent 仍会手搓独立母图 + 纯 i2v，导致坐站硬切。  
> 本文把衔接从「建议」升级为 **写文件 + 校验脚本不过不许跑生成**。

---

## 0. 一条铁律

```
没有通过 preflight 的 shot 表 / storyboard → 禁止调用 H3 / Krea 出片。
手搓脚本、scratchpad、单独 h3_i2v_shot.py 都不例外。
```

---

## 1. 两层保证（顺序固定）

### 层 A — 剧本/分镜先锁（必须）

在**任何母图、任何视频**之前，项目目录必须有：

| 文件 | 作用 |
|------|------|
| `INTENT.md` | 意图（步骤0） |
| **`shot_table.json`** | **姿态状态机**（本门专管；可从 storyboard 导出） |

每镜必须写清结构化状态（不是散文）：

```json
{
  "id": "k07",
  "duration_frames": 243,
  "start": {
    "man": "sit",
    "woman": "sit",
    "prop_silver": "table",
    "blocking": "man_left_table woman_right_stool"
  },
  "end": {
    "man": "stand",
    "woman": "sit",
    "prop_silver": "table",
    "blocking": "man_beside_woman woman_on_stool"
  },
  "action": "man stands and walks to her; she stays seated",
  "gen_mode": "fl2v",
  "chain_from_previous": false,
  "notes": "坐→站大变，禁止纯 i2v 独立母图"
}
```

**硬校验（`scripts/preflight_continuity.py`）：**

1. 每镜有 `start` / `end`，字段齐全  
2. 对相邻镜：`shots[i].end` 的姿态/道具键 **必须等于** `shots[i+1].start` 的同名键  
3. 若 `start.man != end.man` 或 `start.woman != end.woman`（坐↔站等）→ `gen_mode` 必须是 **`fl2v`** 或 **`chain`**（上镜尾帧续），**禁止 `i2v_solo`**  
4. `gen_mode=chain` 时上一镜必须存在且本镜 `chain_from_previous=true`  
5. 失败 → exit code ≠ 0，打印断点镜号

### 层 B — 生成手段（层 A 过了才选）

| 情况 | `gen_mode` | 含义 |
|------|------------|------|
| 同姿态连续往下演 | `i2v` 或 `chain` | 单帧起步；强连续用上镜**真视频尾帧**当首帧 |
| 坐↔站 / 大位移 / 大表情差 | **`fl2v`** | **首帧图 + 尾帧图**硬约束中间过程 |
| 仅换景别、故事时刻相同 | `i2v` | 起终姿态键仍须与邻镜一致 |

**禁止：**

- 独立出 10 张「好看但状态互不继承」的母图再纯 i2v  
- 用剪辑溶解掩盖坐站跳  
- prompt 写「缓缓站起」但首帧已经站着（preflight 比的是 start/end 键，出图前还要人工看母图是否匹配 start）

---

## 2. 为什么有 skill 仍会手搓（根因）

| 根因 | 表现 | 对策（本 skill 采用） |
|------|------|----------------------|
| **散文规则无硬门** | 「必须…」写在长文里，agent 不读完就跑 | **preflight 脚本** exit 1 拦生成 |
| **旁路比主路快** | scratchpad / 直接 Comfy 出片 | 规定：**唯一入口** `preflight` → 官方 runner；旁路=违规 |
| **主路径缺能力** | provider 只有 i2v，fl2v 未接好 → 只能手搓或跳过 | 文档标明 fl2v 脚本；缺口用 `gen_mode` 显式要求，不能默默降级为 i2v_solo |
| **多 skill 竞争** | adult-krea2 vs h3-film-studio | 成人叙事以 **h3-film-studio** 为准；旧 skill 只作参考 |
| **用户催进度** | 「快做」→ 跳过状态表 | 步骤 0.5：无 shot_table **禁止**开跑，先交状态表给用户或自检 |
| **SKILL 过长** | 1800 行 Seedance 细节淹没 H3 铁律 | 顶部 **违禁清单 + 门禁** 先于长流程 |

---

## 3. 强制操作顺序（agent checklist）

```
□ 1. INTENT.md 存在且本轮纠正已写入
□ 2. 写 shot_table.json（姿态状态机）
□ 3. python3 scripts/preflight_continuity.py --table <项目>/shot_table.json
     → 必须 exit 0
□ 4. 按 gen_mode 出母图（start 匹配；fl2v 还要 end 母图）
□ 5. 再 H3；chain 镜用上段 mp4 尾帧
□ 6. 交付前：抽相邻镜尾/首帧，坐站不一致 → 返工
```

**任何一步跳过 = 手搓 = 本 skill 视为流程失败。**

---

## 4. 与旧文档的关系

- 详细分镜字段仍见 `SKILL.md` 4.11 / `pose_contract` / `chain_from_previous`  
- H3 手法见 `narrative-adult-film.md`、`fl2v_build.py`  
- **冲突时以本文件 + preflight 为准**（可执行 > 散文）

---

## 5. 最小 shot_table 模板

见 `templates/shot_table.template.json`。
