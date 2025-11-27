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

今後、このプロンプト群を呼び出すオーケストレータや StoryState の型定義などを追加していく予定です。
