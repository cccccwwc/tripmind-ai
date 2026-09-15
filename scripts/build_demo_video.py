#!/usr/bin/env python3
"""Build a short, silent TripMind product walkthrough from UI screenshots."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps


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


def gradient() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            mix = (x / WIDTH + y / HEIGHT) / 2
            pixels[x, y] = (
                int(248 - 18 * mix),
                int(251 - 20 * mix),
                int(255 - 7 * mix),
            )
    return image


def centered(draw: ImageDraw.ImageDraw, text: str, y: int, text_font, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=text_font)
    draw.text(((WIDTH - (box[2] - box[0])) / 2, y), text, font=text_font, fill=fill)


def title_slide(title: str, subtitle: str) -> Image.Image:
    image = gradient()
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((72, 64, 1208, 656), radius=40, fill="#ffffff", outline="#e3e8f0", width=2)
    draw.rounded_rectangle((536, 160, 744, 212), radius=26, fill="#0a7aff")
    centered(draw, "TRIPMIND AI", 174, font(23), "#ffffff")
    centered(draw, title, 286, font(50), "#121826")
    centered(draw, subtitle, 368, font(25), "#697386")
    centered(draw, "对话澄清 · 数据校验 · LangGraph 编排 · 实时进度", 514, font(20), "#0a70e8")
    return image


def screenshot_slide(path: Path, title: str, subtitle: str) -> Image.Image:
    image = gradient()
    draw = ImageDraw.Draw(image)
    draw.text((54, 30), title, font=font(34), fill="#121826")
    draw.text((56, 77), subtitle, font=font(19), fill="#66758a")

    shot = Image.open(path).convert("RGB")
    shot.thumbnail((1170, 560), Image.Resampling.LANCZOS)
    card = Image.new("RGB", (shot.width + 28, shot.height + 28), "white")
    card.paste(shot, (14, 14))
    x = (WIDTH - card.width) // 2
    y = 130 + max(0, (550 - card.height) // 2)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((x + 8, y + 12, x + card.width + 8, y + card.height + 12), radius=24, fill=(20, 40, 70, 32))
    image = Image.alpha_composite(image.convert("RGBA"), shadow).convert("RGB")
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width, card.height), radius=24, fill=255)
    image.paste(card, (x, y), mask)
    return image


def fade(left: Image.Image, right: Image.Image, count: int):
    for index in range(1, count + 1):
        yield Image.blend(left, right, index / count)


def encode(slides: list[Image.Image], output: Path) -> None:
    import imageio_ffmpeg

    output.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio_ffmpeg.write_frames(
        str(output),
        (WIDTH, HEIGHT),
        fps=FPS,
        codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        output_params=["-movflags", "+faststart", "-crf", "24"],
    )
    writer.send(None)
    hold = int(3.2 * FPS)
    transition = int(0.45 * FPS)
    try:
        for index, slide in enumerate(slides):
            for _ in range(hold):
                writer.send(slide.tobytes())
            if index + 1 < len(slides):
                for frame in fade(slide, slides[index + 1], transition):
                    writer.send(frame.tobytes())
    finally:
        writer.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("screenshots", nargs=4, type=Path)
    args = parser.parse_args()
    missing = [str(path) for path in args.screenshots if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing screenshots: {', '.join(missing)}")

    slides = [
        title_slide("先聊清楚，再开始规划", "TripMind AI 智能旅行规划 Agent"),
        screenshot_slide(args.screenshots[0], "01 · 多轮需求澄清", "自然语言提取目的地、日期、预算和偏好，生成可确认的 Planning Brief"),
        screenshot_slide(args.screenshots[1], "02 · 可追溯用户画像", "自动发现偏好与避雷项，保留原话证据，并由用户审批、编辑或忘记"),
        screenshot_slide(args.screenshots[2], "03 · 真实数据与逐日天气", "高德 POI、天气与坐标校验进入规划，远期天气明确降级而不编造"),
        screenshot_slide(args.screenshots[3], "04 · 行程总览与路线地图", "按天组织景点、酒店、餐饮和路线，并支持历史规划与继续生成"),
        title_slide("TripMind AI", "从旅行需求到可执行行程的一站式 Agent 工作流"),
    ]
    encode(slides, args.output)
    poster = args.output.with_name("tripmind-demo-poster.png")
    slides[3].save(poster, optimize=True)
    print(f"Created {args.output}")
    print(f"Created {poster}")


if __name__ == "__main__":
    sys.path.insert(0, "/tmp/tripmind-media")
    main()
