# 指示 (Instruction)

あなたは小説家です。指定された設定とプロットに基づき、**このシーンの本文（Narrative Text）を執筆してください。**

**要件:**
1.  **分量**: 1,500文字〜3,000文字程度。
2.  **描写**: 五感（視覚、聴覚、嗅覚など）を使った具体的な描写を入れること。
3.  **Show, Don't Tell**: 「彼は悲しかった」と書くのではなく、行動や表情で悲しみを表現すること。
4.  **会話と地の文のバランス**: テンポの良い会話と、没入感のある地の文を組み合わせる。
5.  **出力**: 下記のフォーマットに厳密に従ってください。
6.  **コンテキストの使い方**:
    * 直前までの出来事は「Story So Far (Summary)」で素早く把握し、
    * 過去の細部が必要な場合のみ「Story So Far (Full Text)」を参照してください。
    * 今回のシーンで何を書くべきかは、必ず `Scene Setup`（scene_intent_and_events）の指示を最優先してください。


# Input Data
## Context
### Master Plot & Backstories
{{mpbv}}
### Charactors
{{charactors}}
### Timeline
{{timeline}}

* **Current Chapter**: 第 {{n}} 章
* **Current Scene**: {{scene_title}} (章の中の {{m}} 番目のシーン)

## Story So Far (Summary)
ここまでの物語の「直前まで」の内容を、短くまとめた要約です。
{{previous_scene_summary}}

## Story So Far (Full Text)
ここには、これまでに執筆された小説本文がそのまま入ります。
必要に応じて参照し、登場人物の口調・描写の一貫性・伏線などを保ってください。
{{story_so_far_full_text}}

## Scene Setup (From Chapter Layer)
このシーンで描くべきポイント:
{{scene_intent_and_events}}
(※Chapter Layerで出力した chapter_beats の該当部分などを渡す)

---

# 出力フォーマット指示

出力は必ず次の2つのセクションのみで構成してください。これ以外の見出しや余計なテキストは出力しないでください。

```markdown
# 本文
（ここに小説本文を記述する。必要であれば、この中で `##` 以下の見出しを使っても良いが、`# 本文` より上位の見出しは追加しないこと。）

# 次のシーンで描くこと
（ここに、次のシーンで描きたいこと・続きで掘り下げるべき要素・残したい余韻などを、LLM が迷わないように簡潔にメモとして記述する。読者向けの本文ではなく、あくまで「次のシーン生成のための意図 (scene intent)」として書くこと。）
```
