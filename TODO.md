# TODO / 設計メモ

このリポジトリで目指しているのは、「多層的物語生成装置 (Multi Layered Story Generator)」のプロトタイプ実装。
ここまでの議論で固めた方針と、これからやるべきタスクをメモしておく。

## 1. 現状の設計方針メモ

- モデル＆スコープ
  - 生成のメイン: Anthropic Claude 4.5 系（Opus / Sonnet 想定、200K コンテキスト）。
  - 検証・矛盾チェック: GPT-5.1（Reasoning Effort 高め）。
  - 対象は「中編」レベル。長編は扱わない前提。

- レイヤー構成（ざっくり）
  - Plot Layer (`01_master_plot.md`):  
    ユーザー入力からマスタープロットを Markdown で生成。
  - Backstory Layer (`02_backstory.md`):  
    世界設定（Backstories）を Markdown で生成。
  - MPBV (`03_master_plot_and_backstory_validation.md`):  
    Master Plot + Backstories を GPT-5.1 で統合・矛盾解消し、最終版の Master Plot / Backstories を出す。
  - Character Layer (`04_charactor.md`):  
    MPBV を元にキャラクター設定（キャラシート）を Markdown で生成。
  - Chapter Layer (`05_chapter.md`):  
    MPBV + Characters + 前章の intent を元に、章レベルの構成 JSON を生成。
    - `chapter_beats`（配列）で章の流れを表現。
    - 1章あたりのビート数は 3〜6 個程度。
    - 1ビートは「1シーン相当以上のボリューム感」を持つ出来事（セリフ単位など細かすぎる単位は禁止）。
    - 他のフィールド: `chapter_title`, `chapter_theme`, `active_characters`, `is_final_chapter`, `next_chapter_intent`。
  - Timeline Layer (`06_timeline.md`):  
    章プロットからキャラクター別の時系列 JSON を生成（実装済み想定）。
  - Stylist Layer (`07_stylist.md`):  
    作家ペルソナ＆文体ガイドラインを生成（System Prompt として再利用）。
  - Scene Layer (`08_scene.md`):  
    章のビートとこれまでの本文を元に、シーン本文と「次シーンの intent」を Markdown で生成。

- JSON vs Markdown の使い分け
  - 世界・キャラ・スタイル・プロットなど「内容の肉付け」レイヤー  
    → Markdown（構造化されたテキスト／見出し）。
  - Timeline / 章構成 / 各種フラグ・意図など「構造・制御」レイヤー  
    → JSON（後段コードで機械的に扱う）。
  - Scene 本文  
    → Markdown で `# 本文` セクションに出力。  
      次シーン intent は同じレスポンス内の `# 次のシーンで描くこと` セクションに書かせる。

- Chapter Layer (`05_chapter.md`) の決定事項
  - 出力は純粋な JSON。
  - `chapter_beats`:
    - 1〜3文程度の短いテキスト。
    - 各要素に改行（`\n`）を含めない。
    - ダブルクォート `"` を使わない。
    - 1章あたり 3〜6 ビート程度。
    - 1ビート = 1シーン級（目的＋状況変化を含む出来事）。
  - これにより、JSON 崩壊リスクを下げつつ、Scene Layer 側でビートをほぼそのままシーンに割り当てられる。

- Scene Layer (`08_scene.md`) の決定事項
  - 入力側の追加:
    - `## Story So Far (Summary)`  
      ここまでの「直前までの状況」を短くまとめた要約を渡す。
    - `## Story So Far (Full Text)`  
      これまでに生成された本文をすべて連結して渡す（中編＋Opus 200K 前提）。
    - `## Scene Setup (From Chapter Layer)`  
      `scene_intent_and_events` として、章全体の `chapter_beats` と、
      今回のシーンで必ずやること／やらないことを Markdown で渡す（オーケストレータ側で生成）。
  - モデルへの指示:
    - 直前までの出来事は Summary で把握し、詳細が必要なときだけ Full Text を参照。
    - 今回のシーンで何を書くべきかは `scene_intent_and_events` を最優先。
  - 出力フォーマット:
    - `# 本文`  
      シーン本文。必要なら `##` 以下の見出しを使ってもよい。
    - `# 次のシーンで描くこと`  
      次シーンで掘り下げる要素や、残したい宿題・伏線などを「LLM 向けのメモ」として書かせる。
    - この2セクション以外のトップレベル見出しは禁止。

## 2. これからやるタスク

- [ ] StoryState / モデル間共有データの型設計
  - 例: `MasterPlot`, `Backstories`, `Character`, `Chapter`, `Scene`, `Timeline` などの構造。
  - 中心となる `StoryState` 的なオブジェクトを決める。

- [ ] オーケストレータの骨組み実装
  - 想定言語（例: Python）で以下の関数群のシグネチャを作る:
    - `generate_master_plot(user_input)`
    - `generate_backstories(master_plot)`
    - `validate_mpbv(master_plot, backstories)`
    - `generate_characters(mpbv)`
    - `generate_chapters(mpbv, characters)`
    - `generate_timeline_for_chapter(mpbv, characters, chapter_beats, previous_timeline)`
    - `generate_scenes_for_chapter(mpbv, characters, chapter, timeline, previous_scenes)`
  - 各関数は `StoryState` を受け取り、更新して返す形にする。

- [ ] Scene 用の `scene_intent_and_events` 生成ロジック
  - 章の `chapter_beats`（3〜6個）をすべて含んだ Markdown を構築。
  - そのうえで、シーンごとに:
    - 「このシーンでメインで扱うビート」
    - 「このシーンではまだ描かないビート」
    - 「前シーンから引き継いだ intent」
    を明示的に書き込む。

- [ ] 08_scene の出力パースロジック
  - LLM の出力から:
    - `# 本文` セクションを抽出 → `scene.text`
    - `# 次のシーンで描くこと` セクションを抽出 → `scene.next_scene_intent`
  - これを `StoryState` のシーンリストに蓄積しつつ、次シーンの `scene_intent_and_events` に反映。

- [ ] Timeline Layer との接続方式
  - どのタイミングで `06_timeline.md` を呼ぶか（章単位での呼び出しを想定）。
  - `current_chapter_plot` として渡すテキストをどう構築するか:
    - 章の全シーン本文の結合
    - または `chapter_beats` + 要約 など。

- [ ] 簡易的な CLI / スクリプト
  - 「物語のタネを与えると、プロンプト群を順番に叩いて中編を生成する」スクリプト。
  - 入力: テキストファイル or 標準入力。
  - 出力: 中編本文、タイムライン JSON、各レイヤーの中間成果物。

## 3. 後回しでよいが検討したいこと

- [ ] Timeline を使った「矛盾検出」や「修正提案」用の追加プロンプト。
- [ ] Scene / Chapter の自動要約レイヤーを挟み、別モデル・短コンテキストでも回せるようにする設計。
- [ ] 生成途中で人間が介入できる UI（途中段階でのプロット修正など）。

