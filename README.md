# mlsg2 — Multi Layered Story Generator

多層的なプロンプト設計を使って、中編レベルのフィクションを生成するための実験用リポジトリです。

現時点では主に Anthropic Claude 4.5 系と GPT-5.1 を前提にしたプロンプト群を管理しています。

## アーキテクチャ概要

このプロジェクトは「物語の生成」と「物語の管理」を分離する、多層的なアーキテクチャを取ります。

- 上位レイヤー（Plot / Backstories / Characters / Stylist）  
  物語の設計図・世界観・キャラ・文体などを **Markdown** で生成し、人間が読んで編集しやすい形で保持します。
- 中間レイヤー（Chapter / Timeline）  
  章構成（`chapter_beats`）やタイムラインなどの構造情報を **JSON** で生成し、プログラムから機械的に扱えるようにします。
- 下位レイヤー（Scene）  
  Chapter レイヤーのビートとタイムライン、これまでの本文を元に、シーン本文と「次のシーンで描くべきこと」を **Markdown** で生成します。

Python 側では、これらを `StoryState` という一つの状態オブジェクトで管理し、

- 各レイヤーは「`StoryState` を受け取り、`Result[StoryState, StoryError]` を返す純粋な関数」として実装
- CLI（`mlsg` コマンド）は、このパイプラインを順番に実行する薄いオーケストレータ

という構造を目指しています。UI はあくまで薄く、コアはライブラリとして疎結合に保つ方針です。

- `prompts/01_master_plot.md`  
  ユーザー入力からマスタープロットを Markdown で生成するレイヤー。
- `prompts/02_backstory.md`  
  世界設定（Backstories）を構築するレイヤー。
- `prompts/03_master_plot_and_backstory_validation.md`  
  Master Plot + Backstories を統合し、矛盾を解消した MPBV を生成するレイヤー。
- `prompts/04_charactor.md`  
  キャラクター設定（キャラシート）を生成するレイヤー。
- `prompts/05_chapter.md`  
  章レベルの構成（chapter_beats など）を JSON で生成するレイヤー。
- `prompts/06_timeline.md`  
  章ごとの出来事をキャラクター別タイムライン JSON に落とすレイヤー。
- `prompts/07_stylist.md`  
  作家ペルソナと文体ガイドラインを定義するレイヤー。
- `prompts/08_scene.md`  
  シーン本文と「次のシーン intent」を Markdown で生成するレイヤー。

## インストール

```bash
# 依存関係のインストール
pip install -e .

# または開発モードで実行
PYTHONPATH=src python -m mlsg --version
```

## 環境変数

`.env` ファイルに API キーを設定してください：

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

## CLI の使い方

### 基本コマンド

```bash
# 新規ストーリー生成（全レイヤー実行）
mlsg run "魔法使いの少年が魔法学校に入学する物語"

# ファイルからシードを読み込み
mlsg run -f seed.txt

# run 名を明示指定
mlsg run "シードテキスト" --name my_story
```

### 段階的な実行

```bash
# 特定レイヤーまで実行
mlsg run "シード" --until plot       # Plot のみ
mlsg run "シード" --until backstory  # Plot → Backstory
mlsg run "シード" --until mpbv       # Plot → Backstory → MPBV
mlsg run "シード" --until character  # ... → Character
mlsg run "シード" --until stylist    # ... → Stylist
mlsg run "シード" --until chapter    # ... → Chapter（反復生成）
mlsg run "シード" --until timeline   # ... → Timeline
mlsg run "シード" --until scene      # 全レイヤー（シーン本文まで）

# 既存の run から再開
mlsg run --from runs/my_story/ --only character  # Character のみ再実行
mlsg run --from runs/my_story/ --only chapter    # Chapter のみ再実行
mlsg run --from runs/my_story/                   # 続きから全実行
```

### 外部ファイルの注入（Human-in-the-Loop ワークフロー）

生成された MPBV や Stylist を人間や他の LLM（ChatGPT など）がレビュー・編集し、修正版を注入するワークフローをサポートしています。

```bash
# 1. Plot + Backstory まで生成
mlsg run "シード" --until backstory

# 2. 生成された内容をレビュー
#    runs/my_story/state_02_backstory.json の master_plot と backstories を確認
#    → 修正が必要なら、外部で mpbv.md を作成

# 3. 修正版 MPBV を注入して続行
mlsg run --from runs/my_story/ --inject-mpbv modified_mpbv.md

# Stylist も外部化する場合
mlsg run --from runs/my_story/ --inject-mpbv mpbv.md --inject-stylist stylist.md
```

**外部 MPBV ファイルのフォーマット**:

```markdown
# Master Plot

## 1. 基本情報 (Basic Information)
* **ログライン**: ...
...

# Backstories

## 1. 世界の基本構成 (World Overview)
...
```

ファイルは `# Backstories` で分割されます。このヘッダーがない場合は全体が Master Plot として扱われます。

**外部 Stylist ファイル**: ファイル全体がそのまま `raw_markdown` として使用されます。

### 再実行とリカバリー

パイプラインはレイヤーごとに状態を保存するため、エラー発生時や結果に不満がある場合に途中から再実行できます。

```bash
# 中断した run を続きから再開（完了済みレイヤーは自動スキップ）
mlsg run --from runs/my_story/

# 特定レイヤーだけ再実行（例：Character を再生成）
# → 先にそのレイヤーの状態ファイルを削除
rm runs/my_story/state_04_character.json
mlsg run --from runs/my_story/ --until character

# MPBV を再生成する場合
rm runs/my_story/state_03_mpbv.json runs/my_story/state_final.json
mlsg run --from runs/my_story/ --until mpbv

# 最新の状態ファイルから続行
# （state_02_backstory.json が最新なら mpbv から再開される）
mlsg run --from runs/my_story/
```

**状態ファイルの仕組み**:
- `--from` で指定したディレクトリ内の最新の `state_*.json` を読み込む
- 各レイヤーは状態を見て「既に完了しているか」を判定
- 完了済みレイヤーはスキップされる（ログに `layer_skipped` と表示）

**レイヤーを再実行したい場合**:
1. 再実行したいレイヤー以降の状態ファイルを削除
2. `--from` で再開

### 進捗確認とエクスポート

```bash
# 最新 run の状態を表示
mlsg status

# 特定 run の状態を表示
mlsg status runs/my_story/

# Markdown 形式でエクスポート（標準出力）
mlsg export runs/my_story/

# ファイルに出力
mlsg export runs/my_story/ -o story.md

# HTML 形式でエクスポート（単一ファイル、CSS埋め込み）
mlsg export runs/my_story/ --format html -o story.html
```

**HTML エクスポート**について:
- 明朝体ベースの小説向けレイアウト CSS を埋め込んだ単一 HTML ファイルを出力
- 外部依存なしでブラウザで直接開ける
- レスポンシブ対応（スマホでも読みやすい）

### オプション

```bash
mlsg run "シード" -v    # 詳細ログ表示
mlsg run "シード" -q    # 最小限の出力
```

## 生成されるファイル

```
runs/
└── my_story/
    ├── state_00_init.json          # 初期状態
    ├── state_01_plot.json          # Plot 完了後
    ├── state_02_backstory.json     # Backstory 完了後
    ├── state_03_mpbv.json          # MPBV 完了後
    ├── state_04_character.json     # Character 完了後
    ├── state_05_stylist.json       # Stylist 完了後
    ├── state_06_chapter_01.json    # Chapter 1 完了後
    ├── state_06_chapter_02.json    # Chapter 2 完了後
    ├── ...
    ├── state_07_timeline_01.json   # Timeline 1 完了後
    ├── state_08_scene_01_01.json   # Scene 1-1 完了後
    ├── state_08_scene_01_02.json   # Scene 1-2 完了後
    ├── ...
    └── state_final.json            # 最終状態
```

## 設定

`config.toml` でモデルや生成パラメータを変更できます：

```toml
[models]
default = "claude-sonnet-4-20250514"  # デフォルトモデル
naming = "claude-3-5-haiku-20241022"  # run 名生成用

[layers.plot]
temperature = 1.0
max_tokens = 8192
thinking = false
```
