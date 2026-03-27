#!/usr/bin/env python3
"""
novel2pdf — Markdown小説をA5文庫本風PDFに変換するジェネレータ

Usage:
    python novel2pdf.py input.md [-o output.pdf] [--title タイトル] [--subtitle サブタイトル]

Markdownの構造:
    ## 第1章 - シーン1
    *章のサブタイトル*

    本文テキスト...

    ---          ← シーンブレイク

    ```
    // コメント行（作中コード等）
    ```

依存:
    pip install reportlab

フォント:
    初回実行時に Zen Old Mincho を自動ダウンロードします。
    手動で配置する場合は fonts/ZenOldMincho-Regular.ttf に置いてください。
"""

import argparse
import os
import re
import sys
import urllib.request
from pathlib import Path

from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ---------------------------------------------------------------------------
# Config — ここを変えるとデザインが変わります
# ---------------------------------------------------------------------------
class Config:
    # ページ
    PAGE_SIZE = A5
    MARGIN_TOP = 28 * mm
    MARGIN_BOTTOM = 22 * mm
    MARGIN_LEFT = 18 * mm
    MARGIN_RIGHT = 16 * mm

    # 色
    TEXT_COLOR = HexColor("#1a1a1a")
    SUBTITLE_COLOR = HexColor("#5a5a5a")
    ACCENT_COLOR = HexColor("#8B7355")  # 装飾線・シーンラベル
    LIGHT_GRAY = HexColor("#999999")
    BG_COLOR = HexColor("#f5f0e8")  # クリーム色の紙面

    # フォントサイズ
    BODY_SIZE = 9.5
    CHAPTER_SIZE = 18
    TITLE_SIZE = 20
    SCENE_LABEL_SIZE = 10
    SUBTITLE_SIZE = 9
    CODE_SIZE = 8.5
    HEADER_SIZE = 6.5
    PAGE_NUM_SIZE = 7

    # 行間（BODY_SIZE の倍率）
    LINE_HEIGHT_RATIO = 1.85

    # フォント
    FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/zenoldmincho/ZenOldMincho-Regular.ttf"
    FONT_NAME = "ZenOldMincho"


CFG = Config()
PAGE_W, PAGE_H = CFG.PAGE_SIZE
TEXT_W = PAGE_W - CFG.MARGIN_LEFT - CFG.MARGIN_RIGHT
LINE_HEIGHT = CFG.BODY_SIZE * CFG.LINE_HEIGHT_RATIO
FONT = CFG.FONT_NAME


# ---------------------------------------------------------------------------
# フォント管理
# ---------------------------------------------------------------------------
def ensure_font(script_dir: Path) -> str:
    """フォントを探し、なければダウンロードして登録する。パスを返す。"""
    fonts_dir = script_dir / "fonts"
    font_path = fonts_dir / "ZenOldMincho-Regular.ttf"

    if font_path.exists():
        pdfmetrics.registerFont(TTFont(FONT, str(font_path)))
        return str(font_path)

    # ダウンロード
    fonts_dir.mkdir(parents=True, exist_ok=True)
    print(f"フォントをダウンロード中... → {font_path}")
    try:
        urllib.request.urlretrieve(CFG.FONT_URL, str(font_path))
    except Exception as e:
        print(f"エラー: フォントのダウンロードに失敗しました: {e}", file=sys.stderr)
        print(f"手動で {font_path} に Zen Old Mincho を配置してください。", file=sys.stderr)
        sys.exit(1)

    pdfmetrics.registerFont(TTFont(FONT, str(font_path)))
    print("フォント登録完了")
    return str(font_path)


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------
def string_width(text: str, size: float) -> float:
    return pdfmetrics.stringWidth(text, FONT, size)


def wrap_text(text: str, size: float, max_width: float) -> list[str]:
    lines = []
    current = ""
    for char in text:
        test = current + char
        if string_width(test, size) > max_width:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Markdownパーサー
# ---------------------------------------------------------------------------
def parse_markdown(filepath: str) -> tuple[list[dict], dict]:
    """
    Markdownを解析して (scenes, meta) を返す。

    meta: {"title": str | None, "subtitle": str | None}
    scenes: [{"chapter": str, "scene": str, "subtitle": str, "body": [...]}]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    # トップレベルの # タイトル を探す
    meta = {"title": None, "subtitle": None}
    title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
    if title_match:
        meta["title"] = title_match.group(1).strip()

    scenes = []
    parts = re.split(r"^## ", text, flags=re.MULTILINE)

    for part in parts:
        if not part.strip():
            continue
        lines = part.strip().split("\n")
        header = lines[0].strip()

        chapter_match = re.match(r"(第\d+章)\s*[-ー]\s*(シーン\d+)", header)
        if not chapter_match:
            continue

        chapter = chapter_match.group(1)
        scene = chapter_match.group(2)

        subtitle = ""
        body_lines = []
        in_code = False
        code_block = []

        for line in lines[1:]:
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code:
                    body_lines.append(("code", "\n".join(code_block)))
                    code_block = []
                    in_code = False
                else:
                    in_code = True
                continue

            if in_code:
                code_block.append(line)
                continue

            if stripped.startswith("*") and stripped.endswith("*") and not subtitle:
                subtitle = stripped.strip("*")
                if not meta["subtitle"]:
                    meta["subtitle"] = subtitle
                continue

            if stripped == "---":
                body_lines.append(("break", ""))
                continue

            if not stripped:
                body_lines.append(("empty", ""))
                continue

            body_lines.append(("text", stripped))

        # 連続する空行・ブレイクを整理
        cleaned = []
        prev_type = None
        for typ, content in body_lines:
            if typ == "empty" and prev_type in ("empty", "break", None):
                continue
            if typ == "break" and prev_type == "break":
                continue
            cleaned.append((typ, content))
            prev_type = typ

        while cleaned and cleaned[-1][0] in ("empty", "break"):
            cleaned.pop()
        while cleaned and cleaned[0][0] in ("empty", "break"):
            cleaned.pop(0)

        scenes.append({
            "chapter": chapter,
            "scene": scene,
            "subtitle": subtitle,
            "body": cleaned,
        })

    return scenes, meta


# ---------------------------------------------------------------------------
# PDF描画ヘルパー
# ---------------------------------------------------------------------------
def new_page(c: canvas.Canvas):
    c.setFillColor(CFG.BG_COLOR)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def draw_page_number(c: canvas.Canvas, page_num: int):
    c.setFont(FONT, CFG.PAGE_NUM_SIZE)
    c.setFillColor(CFG.LIGHT_GRAY)
    c.drawCentredString(PAGE_W / 2, CFG.MARGIN_BOTTOM / 2 + 2 * mm, str(page_num))


def draw_header_line(c: canvas.Canvas, header_text: str):
    c.setFont(FONT, CFG.HEADER_SIZE)
    c.setFillColor(CFG.LIGHT_GRAY)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 14 * mm, header_text)


def draw_scene_break(c: canvas.Canvas, y: float) -> float:
    cx = PAGE_W / 2
    c.setFillColor(CFG.ACCENT_COLOR)
    for i in range(-1, 2):
        c.circle(cx + i * 6 * mm, y + 2, 0.8, fill=1, stroke=0)
    return y - LINE_HEIGHT * 0.5


def draw_diamond(c: canvas.Canvas, cx: float, cy: float, size: float = 2):
    c.setFillColor(CFG.ACCENT_COLOR)
    c.saveState()
    c.translate(cx, cy)
    c.rotate(45)
    c.rect(-size, -size, size * 2, size * 2, fill=1, stroke=0)
    c.restoreState()


# ---------------------------------------------------------------------------
# 特殊ページ
# ---------------------------------------------------------------------------
def create_title_page(c: canvas.Canvas, title: str, subtitle: str = ""):
    new_page(c)
    cx = PAGE_W / 2

    # 上部装飾
    y_top = PAGE_H - 40 * mm
    c.setStrokeColor(CFG.ACCENT_COLOR)
    c.setLineWidth(0.5)
    c.line(cx - 30 * mm, y_top, cx + 30 * mm, y_top)
    draw_diamond(c, cx, y_top)

    # タイトル — 長い場合は自動で複数行に
    title_y = PAGE_H / 2 + 15 * mm
    c.setFont(FONT, CFG.TITLE_SIZE)
    c.setFillColor(CFG.TEXT_COLOR)

    # タイトルが長い場合、「の」「を」「は」等の助詞で分割を試みる
    if string_width(title, CFG.TITLE_SIZE) > TEXT_W * 0.8:
        # 中央付近で分割
        mid = len(title) // 2
        split_pos = mid
        for i in range(mid, min(mid + 5, len(title))):
            if title[i] in "のをはがでにとも、":
                split_pos = i + 1
                break
        line1 = title[:split_pos]
        line2 = title[split_pos:]
        c.drawCentredString(cx, title_y, line1)
        c.drawCentredString(cx, title_y - 28, line2)
    else:
        c.drawCentredString(cx, title_y, title)

    # サブタイトル
    if subtitle:
        c.setFont(FONT, CFG.SUBTITLE_SIZE)
        c.setFillColor(CFG.SUBTITLE_COLOR)
        c.drawCentredString(cx, title_y - 60, f"— {subtitle} —")

    # 下部装飾
    y_bot = 45 * mm
    c.setStrokeColor(CFG.ACCENT_COLOR)
    c.setLineWidth(0.5)
    c.line(cx - 30 * mm, y_bot, cx + 30 * mm, y_bot)
    draw_diamond(c, cx, y_bot)

    c.showPage()


def create_chapter_title_page(c: canvas.Canvas, chapter: str, subtitle: str = ""):
    new_page(c)
    cx = PAGE_W / 2
    cy = PAGE_H / 2 + 10 * mm

    c.setFont(FONT, 10)
    c.setFillColor(CFG.LIGHT_GRAY)
    c.drawCentredString(cx, cy + 22, "—")

    c.setFont(FONT, CFG.CHAPTER_SIZE)
    c.setFillColor(CFG.TEXT_COLOR)
    c.drawCentredString(cx, cy, chapter)

    if subtitle:
        c.setFont(FONT, CFG.SUBTITLE_SIZE)
        c.setFillColor(CFG.SUBTITLE_COLOR)
        c.drawCentredString(cx, cy - 25, subtitle)

    c.setStrokeColor(CFG.ACCENT_COLOR)
    c.setLineWidth(0.4)
    c.line(cx - 20 * mm, cy - 40, cx + 20 * mm, cy - 40)

    c.showPage()


def create_colophon(c: canvas.Canvas):
    new_page(c)
    cx = PAGE_W / 2
    cy = PAGE_H / 2
    draw_diamond(c, cx, cy)
    c.setFont(FONT, 8)
    c.setFillColor(CFG.LIGHT_GRAY)
    c.drawCentredString(cx, cy - 20, "— 了 —")
    c.showPage()


# ---------------------------------------------------------------------------
# メインのPDF生成
# ---------------------------------------------------------------------------
def generate_pdf(
    scenes: list[dict],
    output_path: str,
    title: str = "無題",
    subtitle: str = "",
):
    c = canvas.Canvas(output_path, pagesize=CFG.PAGE_SIZE)
    c.setTitle(title)
    c.setSubject("小説")

    # 表紙
    create_title_page(c, title, subtitle)

    # 見返し（空白ページ）
    new_page(c)
    c.showPage()

    page_num = 1
    current_chapter = None

    for scene in scenes:
        # 章扉
        if scene["chapter"] != current_chapter:
            current_chapter = scene["chapter"]
            create_chapter_title_page(c, scene["chapter"], scene["subtitle"])
            page_num += 1

        # シーン本文ページ
        new_page(c)
        header_text = f'{scene["chapter"]}　{scene["scene"]}'
        draw_header_line(c, header_text)

        y = PAGE_H - CFG.MARGIN_TOP

        # シーンラベル
        c.setFont(FONT, CFG.SCENE_LABEL_SIZE)
        c.setFillColor(CFG.ACCENT_COLOR)
        c.drawString(CFG.MARGIN_LEFT, y, scene["scene"])
        y -= LINE_HEIGHT * 2

        # 本文
        for typ, content in scene["body"]:
            if typ == "break":
                if y - LINE_HEIGHT * 3 < CFG.MARGIN_BOTTOM:
                    draw_page_number(c, page_num)
                    page_num += 1
                    c.showPage()
                    new_page(c)
                    draw_header_line(c, header_text)
                    y = PAGE_H - CFG.MARGIN_TOP

                y -= LINE_HEIGHT * 0.8
                y = draw_scene_break(c, y)
                y -= LINE_HEIGHT * 0.8
                continue

            if typ == "empty":
                y -= LINE_HEIGHT * 0.6
                continue

            if typ == "code":
                c.setFont(FONT, CFG.CODE_SIZE)
                c.setFillColor(CFG.SUBTITLE_COLOR)
                for cl in content.split("\n"):
                    cl = cl.strip()
                    if not cl:
                        continue
                    display = cl[2:].strip() if cl.startswith("//") else cl

                    for wl in wrap_text(display, CFG.CODE_SIZE, TEXT_W - 12 * mm):
                        if y - LINE_HEIGHT < CFG.MARGIN_BOTTOM:
                            draw_page_number(c, page_num)
                            page_num += 1
                            c.showPage()
                            new_page(c)
                            draw_header_line(c, header_text)
                            y = PAGE_H - CFG.MARGIN_TOP
                            c.setFont(FONT, CFG.CODE_SIZE)
                            c.setFillColor(CFG.SUBTITLE_COLOR)

                        c.drawString(CFG.MARGIN_LEFT + 6 * mm, y, wl)
                        y -= LINE_HEIGHT * 0.9

                y -= LINE_HEIGHT * 0.3
                continue

            if typ == "text":
                c.setFont(FONT, CFG.BODY_SIZE)
                c.setFillColor(CFG.TEXT_COLOR)

                for wl in wrap_text(content, CFG.BODY_SIZE, TEXT_W):
                    if y - LINE_HEIGHT < CFG.MARGIN_BOTTOM:
                        draw_page_number(c, page_num)
                        page_num += 1
                        c.showPage()
                        new_page(c)
                        draw_header_line(c, header_text)
                        y = PAGE_H - CFG.MARGIN_TOP
                        c.setFont(FONT, CFG.BODY_SIZE)
                        c.setFillColor(CFG.TEXT_COLOR)

                    c.drawString(CFG.MARGIN_LEFT, y, wl)
                    y -= LINE_HEIGHT

                y -= LINE_HEIGHT * 0.15

        draw_page_number(c, page_num)
        page_num += 1
        c.showPage()

    # 奥付
    create_colophon(c)

    c.save()
    print(f"✓ {output_path} ({page_num + 3}ページ)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Markdown小説 → A5文庫本風PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python novel2pdf.py 08_scenes.md
  python novel2pdf.py 08_scenes.md -o 交差域の夕暮れ.pdf
  python novel2pdf.py 08_scenes.md --title "交差域の夕暮れ" --subtitle "あなたが書いたものが、あなたを書く"
        """,
    )
    parser.add_argument("input", help="入力Markdownファイル")
    parser.add_argument("-o", "--output", help="出力PDFパス (デフォルト: 入力ファイル名.pdf)")
    parser.add_argument("--title", help="タイトルを上書き (デフォルト: Markdownの # 見出しから自動取得)")
    parser.add_argument("--subtitle", help="サブタイトルを上書き")
    args = parser.parse_args()

    # 入力チェック
    if not os.path.exists(args.input):
        print(f"エラー: {args.input} が見つかりません", file=sys.stderr)
        sys.exit(1)

    # フォント準備
    script_dir = Path(__file__).resolve().parent
    ensure_font(script_dir)

    # パース
    scenes, meta = parse_markdown(args.input)
    if not scenes:
        print("エラー: シーンが見つかりません。## 第N章 - シーンN の形式で書いてください。", file=sys.stderr)
        sys.exit(1)

    print(f"検出: {len(scenes)} シーン")

    # タイトル決定
    title = args.title or meta.get("title") or Path(args.input).stem
    subtitle = args.subtitle or meta.get("subtitle") or ""

    # 出力パス
    output = args.output or Path(args.input).with_suffix(".pdf")

    # 生成
    generate_pdf(scenes, str(output), title=title, subtitle=subtitle)


if __name__ == "__main__":
    main()
