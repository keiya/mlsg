# novel2pdf

Markdown小説をA5文庫本風PDFに変換するジェネレータ。

## セットアップ

```bash
pip install reportlab
```

初回実行時に日本語フォント（Zen Old Mincho）を自動ダウンロードします。

## 使い方

```bash
# 基本（タイトルはMarkdownの # 見出しから自動取得）
python tools/novel2pdf/novel2pdf.py runs/my_story/08_scenes.md

# 出力ファイル名を指定
python tools/novel2pdf/novel2pdf.py runs/my_story/08_scenes.md -o my_story.pdf

# タイトル・サブタイトルを手動指定
python tools/novel2pdf/novel2pdf.py runs/my_story/08_scenes.md --title "交差域の夕暮れ" --subtitle "あなたが書いたものが、あなたを書く"
```

## Markdownの書き方

```markdown
# 作品タイトル（オプション）

## 第1章 - シーン1
*章のサブタイトル（イタリック行）*

本文テキスト。段落は空行で区切る。

「会話文はそのまま書く」

---

シーンブレイク（水平線）の後に続きを書く。

## 第1章 - シーン2
*章のサブタイトル*

次のシーンの本文...
```

### ルール

- `## 第N章 - シーンN` の形式が必須（章番号とシーン番号）
- 章の最初のイタリック行（`*テキスト*`）がサブタイトルになる
- `---` はシーン内の区切り（三点装飾が入る）
- コードブロック内の `//` コメントは装飾付きで表示
- 同じ章番号のシーンは1つの章としてグループ化

## カスタマイズ

`novel2pdf.py` 内の `Config` クラスを編集:

```python
class Config:
    PAGE_SIZE = A5          # B6, A4 なども可
    BG_COLOR = "#f5f0e8"    # 紙の色
    ACCENT_COLOR = "#8B7355" # 装飾色
    BODY_SIZE = 9.5          # 本文フォントサイズ
    LINE_HEIGHT_RATIO = 1.85 # 行間倍率
    ...
```

## ファイル構成

```
tools/novel2pdf/
├── novel2pdf.py          # ジェネレータ本体
├── README.md
└── fonts/                # 初回実行時に自動生成
    └── ZenOldMincho-Regular.ttf
```
