#!/usr/bin/env python3
"""Build the narrated TripMind AI product walkthrough."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1280
HEIGHT = 720
FPS = 24
FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


def font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#f3f7ff")
    draw = ImageDraw.Draw(image)
    draw.ellipse((-180, -260, 590, 510), fill="#e8f4ff")
    draw.ellipse((900, 390, 1520, 970), fill="#eeeaff")
    return image


def centered(draw: ImageDraw.ImageDraw, text: str, y: int, text_font, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text(((WIDTH - box[2] + box[0]) / 2, y), text, font=text_font, fill=fill)


def title_slide(title: str, subtitle: str, footer: str) -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((82, 74, 1198, 646), radius=42, fill="#ffffff", outline="#dfe6f1", width=2)
    draw.rounded_rectangle((510, 152, 770, 208), radius=28, fill="#0a7aff")
    centered(draw, "TRIPMIND AI", 168, font(24), "#ffffff")
    centered(draw, title, 286, font(52), "#121826")
    centered(draw, subtitle, 374, font(25), "#657388")
    centered(draw, footer, 520, font(20), "#0a70e8")
    return image


def feature_slide(kicker: str, title: str, bullets: list[str], metric: str = "") -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image)
    draw.text((72, 62), kicker.upper(), font=font(19), fill="#0879ec")
    draw.text((72, 100), title, font=font(42), fill="#121826")
    draw.rounded_rectangle((72, 184, 1208, 630), radius=34, fill="#ffffff", outline="#dfe6f1", width=2)
    y = 235
    for index, item in enumerate(bullets, start=1):
        draw.ellipse((118, y + 3, 162, y + 47), fill="#e8f3ff")
        number = str(index)
        box = draw.textbbox((0, 0), number, font=font(20))
        draw.text((140 - (box[2] - box[0]) / 2, y + 12), number, font=font(20), fill="#0879ec")
        draw.text((188, y + 8), item, font=font(24), fill="#26354a")
        y += 82
    if metric:
        draw.rounded_rectangle((855, 92, 1208, 150), radius=24, fill="#17191f")
        draw.text((884, 106), metric, font=font(20), fill="#ffffff")
    return image


def screenshot_slide(path: Path, kicker: str, title: str, subtitle: str) -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image)
    draw.text((54, 30), kicker.upper(), font=font(17), fill="#0879ec")
    draw.text((54, 58), title, font=font(34), fill="#121826")
    draw.text((56, 103), subtitle, font=font(18), fill="#66758a")

    shot = Image.open(path).convert("RGB")
    shot.thumbnail((1160, 525), Image.Resampling.LANCZOS)
    card = Image.new("RGB", (shot.width + 24, shot.height + 24), "#ffffff")
    card.paste(shot, (12, 12))
    x = (WIDTH - card.width) // 2
    y = 158 + max(0, (525 - card.height) // 2)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x + 8, y + 12, x + card.width + 8, y + card.height + 12),
        radius=24,
        fill=(20, 40, 70, 34),
    )
    image = Image.alpha_composite(image.convert("RGBA"), shadow).convert("RGB")
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width, card.height), radius=24, fill=255)
    image.paste(card, (x, y), mask)
    return image


def architecture_slide() -> Image.Image:
    image = background()
    draw = ImageDraw.Draw(image)
    draw.text((58, 40), "SYSTEM ARCHITECTURE", font=font(18), fill="#0879ec")
    draw.text((58, 72), "稳定、可恢复的旅行 Agent 工作流", font=font(38), fill="#121826")
    nodes = [
        (70, 190, 280, 290, "对话 Agent", "Planning Brief"),
        (355, 190, 585, 290, "用户确认", "Human-in-the-loop"),
        (660, 160, 1005, 320, "LangGraph 编排", "并行 · 重试 · 恢复"),
        (1075, 190, 1225, 290, "行程", "结构化输出"),
        (215, 440, 475, 545, "高德 POI", "景点与酒店"),
        (510, 440, 770, 545, "高德天气", "确定性查询"),
        (805, 440, 1065, 545, "可靠性校验", "失败自动补搜"),
    ]
    for x1, y1, x2, y2, label, sub in nodes:
        fill = "#17191f" if label == "LangGraph 编排" else "#ffffff"
        text_color = "#ffffff" if label == "LangGraph 编排" else "#1e2d42"
        draw.rounded_rectangle((x1, y1, x2, y2), radius=24, fill=fill, outline="#dce4ef", width=2)
        draw.text((x1 + 24, y1 + 26), label, font=font(23), fill=text_color)
        draw.text((x1 + 24, y1 + 62), sub, font=font(16), fill="#aebbd0" if fill == "#17191f" else "#708097")
    for start, end in [((280, 240), (355, 240)), ((585, 240), (660, 240)), ((1005, 240), (1075, 240)), ((830, 320), (345, 440)), ((835, 320), (640, 440)), ((840, 320), (935, 440))]:
        draw.line((*start, *end), fill="#7890ad", width=4)
        ex, ey = end
        draw.polygon([(ex, ey), (ex - 13, ey - 7), (ex - 13, ey + 7)], fill="#7890ad")
    draw.rounded_rectangle((250, 620, 1030, 674), radius=25, fill="#ffffff", outline="#dfe6f1", width=2)
    centered(draw, "SQLite · 后台任务 · SSE · 检查点 · 长期旅行记忆", 634, font(20), "#4f6179")
    return image


def audio_duration(ffmpeg: str, path: Path) -> float:
    result = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        raise RuntimeError("Unable to read narration duration")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def encode_video(slides: list[Image.Image], durations: list[float], output: Path, ffmpeg: str) -> None:
    import imageio_ffmpeg

    writer = imageio_ffmpeg.write_frames(
        str(output),
        (WIDTH, HEIGHT),
        fps=FPS,
        codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        output_params=["-movflags", "+faststart", "-crf", "23"],
    )
    writer.send(None)
    transition_frames = int(0.45 * FPS)
    try:
        for index, (slide, duration) in enumerate(zip(slides, durations)):
            hold_frames = max(FPS, int(duration * FPS) - transition_frames)
            for _ in range(hold_frames):
                writer.send(slide.tobytes())
            if index + 1 < len(slides):
                for frame_index in range(1, transition_frames + 1):
                    frame = Image.blend(slide, slides[index + 1], frame_index / transition_frames)
                    writer.send(frame.tobytes())
    finally:
        writer.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--narration", type=Path, required=True)
    parser.add_argument("screenshots", nargs=5, type=Path)
    args = parser.parse_args()
    for path in [args.narration, *args.screenshots]:
        if not path.is_file():
            raise SystemExit(f"Missing input: {path}")

    sys.path.insert(0, "/tmp/tripmind-media")
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    narration_audio = args.output.with_name("tripmind-demo-narration.mp3")
    silent_video = args.output.with_name("tripmind-demo-detailed-silent.mp4")
    narration_text = args.narration.read_text(encoding="utf-8")

    try:
        import edge_tts

        speech = edge_tts.Communicate(
            narration_text,
            "zh-CN-XiaoxiaoNeural",
            rate="+6%",
            volume="+0%",
            pitch="-2Hz",
        )
        asyncio.run(speech.save(str(narration_audio)))
    except Exception as exc:
        if not shutil.which("say"):
            raise SystemExit(f"Neural voice failed and no local fallback is available: {exc}") from exc
        narration_audio = args.output.with_name("tripmind-demo-narration.aiff")
        subprocess.run(
            ["say", "-v", "Flo (中文（中国大陆）)", "-r", "190", "-o", str(narration_audio), narration_text],
            check=True,
        )

    slides = [
        title_slide("先聊清楚，再开始规划", "完整旅行 Agent 产品演示", "约 2 分钟 · 陈稳畅个人实习项目"),
        feature_slide("PRODUCT GOAL", "为什么不是普通的行程生成器", ["先澄清需求，信息完整后再启动", "真实工具查询，减少模型幻觉", "用户确认、记忆与历史形成闭环"]),
        screenshot_slide(args.screenshots[0], "INTAKE", "多轮对话生成 Planning Brief", "自动合并目的地、日期、天数、预算和偏好；冲突信息会主动提醒"),
        screenshot_slide(args.screenshots[1], "MEMORY", "可审批的长期旅行画像", "候选偏好保留原话与消息编号，用户可确认、编辑、忘记或临时覆盖"),
        architecture_slide(),
        feature_slide("RELIABILITY", "POI 数据可靠性闭环", ["记录高德 POI ID、城市、行政区和坐标", "校验开放状态、来源、时间与置信度", "不合格地点自动补搜并重新生成路线"]),
        screenshot_slide(args.screenshots[2], "RESULT", "住宿、景点、餐饮一屏总览", "汇总每天要住的酒店、要去的景点和要吃的饭店，减少页面空白"),
        screenshot_slide(args.screenshots[3], "WEATHER", "天气与每日行程保持一致", "近期使用真实预报；远期日期明确提示暂不可用，不编造温度"),
        screenshot_slide(args.screenshots[4], "MAP", "地图路线与时间轴联动", "只展示已通过城市与坐标校验的地点，按每天的游览顺序连线"),
        feature_slide("ENGINEERING", "可恢复的后台任务", ["规划接口立即返回 job id", "SSE 推送节点级实时进度", "支持取消、重试、断线重连与中断恢复"], "FastAPI + LangGraph"),
        feature_slide("QUALITY", "自动化测试与 Agent 评测", ["55 项后端自动化测试", "22 项前端关键页面测试", "Brief、工具轨迹、POI、冲突率与成本评测"], "77 tests passed"),
        title_slide("TripMind AI", "从需求理解到可执行行程", "Vue 3 · FastAPI · LangGraph · DeepSeek · 高德 · Tavily"),
    ]
    weights = [5, 8, 9, 9, 9, 9, 8, 8, 8, 8, 8, 5]
    total = audio_duration(ffmpeg, narration_audio) + 2.0
    durations = [total * weight / sum(weights) for weight in weights]
    encode_video(slides, durations, silent_video, ffmpeg)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(narration_audio),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(args.output),
        ],
        check=True,
        capture_output=True,
    )
    silent_video.unlink(missing_ok=True)
    narration_audio.unlink(missing_ok=True)
    slides[0].save(args.output.with_name("tripmind-demo-detailed-poster.png"), optimize=True)
    print(f"Created narrated demo: {args.output}")


if __name__ == "__main__":
    main()
