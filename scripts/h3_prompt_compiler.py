#!/usr/bin/env python3
"""H3 官方格式 prompt 编译器（依据 MiniMaxAI/MiniMax-H3 docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md）。

规则来源：reference/official/VIDEO_PROMPT_WRITING_GUIDE_base_en.md
- 首行：I2VA / FL2VA 固定对齐指令，空一行，再三字段
- 正文全英文；只有 <d>[Chinese] …</d> 里放台词原文（逐字，不翻译）
- 说话人：稳定编号 (S1)/(S2)，身份/音色/语气写在 <d> 外；不出声的人不给编号
- 静默镜：官方句式 "... lips remain completely closed"，soundscape 只写环境/动作声
- 画面可见文字才用英文双引号；prompt 里不出现任何 <d> 之外的中文
- overall_soundscape 1–4 句；non_diegetic_music 无则 N/A

用法：
    from h3_prompt_compiler import compile_i2va, compile_fl2va, Line
    p = compile_i2va(style=..., anchor=..., beats=[...], lines=[Line("S1","the young woman with a soft, trembling voice","pleads","使不得。")], soundscape=...)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

FPS = 24
I2VA_HEAD = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."


@dataclass
class Line:
    speaker: str          # "S1"
    who: str              # 英文身份+音色，如 "the young woman with a soft, trembling voice"
    verb: str             # 英文说话方式，如 "pleads" / "says in a low, threatening voice"
    text: str             # 台词原文（中文），逐字进 <d>
    lang: str = "Chinese"
    after: str = ""       # 说完之后的动作（英文，可空）

    def render(self) -> str:
        t = self.text.strip()
        # 官方：句末用 . ? ! 之一；去掉装饰性重复标点
        t = re.sub(r"[…]+", "，", t).rstrip("，, ")
        if not re.search(r"[。？！.?!]$", t):
            t += "。"
        s = f"{self.who} ({self.speaker}) {self.verb}: <d>[{self.lang}] {t}</d>"
        if self.after:
            s += f" {self.after.strip()}"
        return s


def _assert_no_chinese_outside_d(prompt: str) -> None:
    stripped = re.sub(r"<d>.*?</d>", "", prompt, flags=re.S)
    bad = re.findall(r"[一-鿿]+", stripped)
    if bad:
        raise ValueError(f"<d> 之外出现中文（官方规范禁止，会被念/烧成字幕）: {bad[:5]}")


def _body(style: str, anchor: str, beats: list[str], lines: list[Line] | None,
          silent_subjects: list[str] | None, camera: str) -> str:
    parts = [f"[Shot 1] {style}, {anchor.strip().rstrip('.')}."]
    if camera:
        parts.append(camera.strip().rstrip(".") + ".")
    # 官方推荐：首帧锚 → 动作起始 → 持续发展 → 结果/反应；台词嵌在动作时间线里
    beats = [b.strip().rstrip(".") + "." for b in (beats or [])]
    lines = lines or []
    if lines:
        # 把台词插在第一个 beat 之后，其余 beat 跟在后面（单镜时间线）
        parts.append(beats[0] if beats else "")
        parts.extend(l.render() for l in lines)
        parts.extend(beats[1:])
    else:
        parts.extend(beats)
    for who in (silent_subjects or []):
        # 官方唯一的“闭嘴”句式（出自画外音规则），用于静默镜
        parts.append(f"{who.strip().rstrip('.')} remains silent throughout the shot, and {'her' if 'woman' in who or 'she' in who else 'his'} lips remain completely closed.")
    return " ".join(p for p in parts if p)


def compile_i2va(*, style: str, anchor: str, beats: list[str], soundscape: str,
                 lines: list[Line] | None = None, silent_subjects: list[str] | None = None,
                 camera: str = "The camera holds a static shot", music: str = "N/A") -> str:
    body = _body(style, anchor, beats, lines, silent_subjects, camera)
    prompt = (f"{I2VA_HEAD}\n\n"
              f"integrated_multimodal_description: {body}\n\n"
              f"overall_soundscape: {soundscape.strip()}\n\n"
              f"non_diegetic_music: {music.strip()}")
    _assert_no_chinese_outside_d(prompt)
    return prompt


def compile_fl2va(*, frames: int, style: str, anchor: str, beats: list[str], soundscape: str,
                  lines: list[Line] | None = None, silent_subjects: list[str] | None = None,
                  camera: str = "The camera holds a static shot", music: str = "N/A",
                  landing: str = "settles into the pose, spacing, and composition established by Picture 2 at the end of the shot") -> str:
    secs = frames / FPS
    head = (f"How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
            f"Picture 2 (from Shot 1) aligns with the {secs:.2f}-second mark of the target video.")
    body = _body(style, anchor, beats + [landing], lines, silent_subjects, camera)
    prompt = (f"{head}\n\n"
              f"integrated_multimodal_description: {body}\n\n"
              f"overall_soundscape: {soundscape.strip()}\n\n"
              f"non_diegetic_music: {music.strip()}")
    _assert_no_chinese_outside_d(prompt)
    return prompt


def density(lines: list[Line], frames: int) -> float:
    """台词密度（字/秒）——低于 1.5 会被乱码填空（2026-08-24 实证）。"""
    n = sum(len(re.sub(r"[，。、！？…\s]", "", l.text)) for l in lines)
    return n / (frames / FPS)


if __name__ == "__main__":
    ROOM = "in a candlelit Ming-dynasty bedchamber with a red lacquered canopy bed, white gauze curtains, and bronze candlesticks"
    p = compile_i2va(
        style="Live-action, cinematic",
        anchor=f"a medium side shot frames the bearded man in a black robe and the young woman in a white robe shown in <Picture 1> {ROOM}, preserving their appearance, clothing, and positions",
        beats=["He pulls her toward him by the waist while she braces both hands against his chest and turns her face away",
               "She keeps pushing against his chest as the line ends"],
        lines=[Line("S1", "The young woman with a soft, trembling voice", "pleads", "使不得，官人使不得，妾身是有夫之妇，求官人放过妾身罢。")],
        soundscape="Quiet indoor room tone with a faint candle flicker continues throughout, joined by the rustle of silk robes and a few shuffling footsteps on the wooden floor.")
    print(p)
