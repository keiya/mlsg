# mlsg2 Architecture

このドキュメントは mlsg2 (Multi-Layered Story Generator) の設計詳細を記述する。
コーディング規約やエラーハンドリングの一般原則は `CLAUDE.md` を参照。

---

## 設計原則

### Library-first, UI-thin

- コアロジックは Python パッケージ (`src/mlsg`) に集約し、純粋な型付き関数として公開する
- CLI (`mlsg` コマンド) は薄いレイヤーとして:
  - フラグ / stdin をパース
  - ライブラリ関数を呼び出し
  - `Result[StoryState, StoryError]` を exit code と human-readable メッセージに変換
- 将来の UI (TUI, web) はライブラリのみに依存し、ドメインロジックを再実装しない

### Result-based Orchestration

- 各レイヤーは `StoryState -> Result[StoryState, StoryError]` のシグネチャを持つ
- オーケストレーション層は `Result` の明示的な分岐で構成（隠れた例外なし）
- パイプラインは設定可能: 「MPBV まで実行」「既存 state から Chapter を再実行」等

### LLM Integration as Infrastructure

- LLM 呼び出しはインフラストラクチャとして抽象化 (`LLMClient`)
- ドメイン / パイプラインコードは DI で `LLMClient` を受け取る
- プロンプトテンプレート (`prompts/`) はインフラ層でロード・合成

### Testability

- 各レイヤーは単体テスト可能:
  - 小さな synthetic `StoryState` を渡す
  - fake / stub `LLMClient` を注入
  - 結果の `StoryState` または `StoryError` を assert
- CLI レベルのテストは引数パースとエラー表示のみ検証

---

## レイヤー構成

物語生成は以下の 8 レイヤーで構成される:

```
User Input (seed)
    │
    ▼
┌─────────────────┐
│  1. Plot Layer  │  → MasterPlot (Markdown)
└─────────────────┘
    │
    ▼
┌─────────────────────┐
│  2. Backstory Layer │  → Backstories (Markdown)
└─────────────────────┘
    │
    ▼
┌─────────────────┐
│  3. MPBV Layer  │  → MPBV (validated, Markdown)
└─────────────────┘
    │
    ▼
┌─────────────────────┐
│  4. Character Layer │  → list[Character] (Markdown)
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│  5. Stylist Layer   │  → Stylist (Markdown: 文体ガイドライン)
└─────────────────────┘
    │
    ├──────────────────────────────────────┐
    ▼                                      │
┌───────────────────┐                      │
│  6. Chapter Layer │  → list[Chapter]     │ (stylist は Scene へ)
└───────────────────┘     (JSON)           │
    │                                      │
    ├─── per chapter ───┐                  │
    ▼                   ▼                  ▼
┌────────────────────┐ ┌─────────────────────┐
│  7. Timeline Layer │ │  8. Scene Layer     │ ← stylist を参照
│  → TimelineSlice   │ │  → list[Scene]      │
│     (JSON)         │ │     (Markdown)      │
└────────────────────┘ └─────────────────────┘
    │                   │
    └───────────────────┘
            │
            ▼
      Final Story Output
```

### 各レイヤーの責務

| Layer | 入力 | 出力 | 形式 | Temperature | Thinking |
|-------|------|------|------|-------------|----------|
| Plot | seed_input | MasterPlot | Markdown | 高め (1.0) | OFF |
| Backstory | seed_input + master_plot | Backstories | Markdown | 高め (1.0) | OFF |
| MPBV | master_plot + backstories | MPBV | Markdown | - | **ON** |
| Character | mpbv | list[Character] | Markdown | 高め (1.0) | OFF |
| Stylist | mpbv | Stylist | Markdown | 標準 (0.7) | OFF |
| Chapter | mpbv + characters + prev_chapter | Chapter | JSON | 標準 (0.7) | **ON** |
| Timeline | chapter + prev_timeline | TimelineSlice | JSON | 低め (0.3) | **ON** |
| Scene | **stylist** + chapter + timeline + prev_scenes | list[Scene] | Markdown | 標準 (0.7) | OFF |

**Thinking の原則:**
- ON = 論理整合性・構造設計・検証が必要なレイヤー
- OFF = 創造的生成・散文執筆

**Stylist → Scene の連携:**
- Stylist Layer は「作家ペルソナ」と「文体ガイドライン」を生成する
- Scene Layer はこのガイドラインを **最優先指示** として受け取り、全シーンで一貫した文体を保つ
- 具体的には: ナレーターの性格、文のリズム、語彙選択、比喩の傾向、禁止事項（AI的悪癖の排除）など

### イテレーティブ生成

Chapter と Scene は反復的に生成される:

```python
# Chapter 生成ループ
chapter_index = 0
while chapter_index < MAX_CHAPTERS:
    chapter = generate_chapter(state, chapter_index)
    state = state.with_chapter(chapter)
    if chapter.is_final_chapter:
        break
    chapter_index += 1

# Scene 生成ループ (各 Chapter 内)
for chapter in state.chapters:
    scene_index = 0
    while scene_index < MAX_SCENES_PER_CHAPTER:
        scene = generate_scene(state, chapter.index, scene_index)
        state = state.with_scene(scene)
        if scene.is_final_scene:
            break
        scene_index += 1
```

### 上限値

| 項目 | デフォルト値 | 設定キー |
|------|-------------|----------|
| 最大章数 | 20 | `limits.max_chapters` |
| 章あたり最大シーン数 | 10 | `limits.max_scenes_per_chapter` |
| LLM リトライ回数 | 3 | `limits.max_retries` |
| パースリトライ回数 | 2 | `limits.max_parse_retries` |

---

## ドメイン型

すべての型は `src/mlsg/domain.py` に定義:

```python
@dataclass(slots=True)
class StoryState:
    seed_input: str
    run_name: str  # 自動生成または --name で指定
    master_plot: MasterPlot | None = None
    backstories: Backstories | None = None
    mpbv: MPBV | None = None
    characters: list[Character] = field(default_factory=list)
    stylist: Stylist | None = None
    chapters: list[Chapter] = field(default_factory=list)
    timelines: list[TimelineSlice] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
```

### 補助型

- `TimelineEvent`: 単一イベント (`datetime`, `description`)
- `CharacterTimeline`: キャラクター別タイムライン
- `TimelineSlice`: 章ごとのタイムライン集約
- `Stylist`: 作家ペルソナと文体ガイドライン

---

## LLMClient プロトコル

```python
from typing import Protocol

class LLMClient(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Result[str, StoryError]:
        """Send a prompt and return the completion text."""
        ...

    def complete_stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool = False,
        thinking_budget: int | None = None,
    ) -> Iterator[Result[str, StoryError]]:
        """Stream completion chunks."""
        ...
```

### モデル使い分け

| 用途 | モデル | 備考 |
|------|--------|------|
| 初期生成 | Claude Sonnet 4.5 | Thinking 時は Budget Tokens 指定可 |
| 検証 (MPBV) | Claude Opus 4.5 | Extended Thinking で矛盾検出・統合 |
| Run 名生成 | Claude Haiku | 軽量・高速 |

---

## リトライ戦略

### エラー種別と対応

| エラー種別 | リトライ | 対応 |
|-----------|---------|------|
| Rate limit (429) | Yes | Exponential backoff |
| Server error (5xx) | Yes | Exponential backoff |
| Network error | Yes | Exponential backoff |
| Parse error | Yes | 再生成を依頼 (最大 `max_parse_retries` 回) |
| Invalid API key | No | 即座に失敗 |
| Context too long | No | 即座に失敗 (将来: 要約して再試行) |

### Backoff 設定

```python
@dataclass
class RetryConfig:
    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0
    exponential_base: float = 2.0
```

---

## 設定管理

### config.toml

```toml
[general]
language = "ja"
runs_dir = "runs"

[limits]
max_chapters = 20
max_scenes_per_chapter = 10
max_retries = 3
max_parse_retries = 2

[models]
default = "claude-sonnet-4-5-20250929"
validation = "claude-opus-4-5-20251101"
naming = "claude-3-5-haiku-20241022"

[layers.plot]
model = "claude-sonnet-4-5-20250514"
temperature = 1.0
max_tokens = 64000
thinking = false

[layers.backstory]
model = "claude-sonnet-4-5-20250514"
temperature = 1.0
max_tokens = 64000
thinking = false

[layers.mpbv]
model = "claude-opus-4-5-20251101"
temperature = 0.7
max_tokens = 64000
thinking = true
thinking_budget = 31999

[layers.character]
model = "claude-sonnet-4-5-20250514"
temperature = 1.0
max_tokens = 64000
thinking = false

[layers.stylist]
model = "claude-sonnet-4-5-20250514"
temperature = 0.7
max_tokens = 64000
thinking = false

[layers.chapter]
model = "claude-sonnet-4-5-20250514"
temperature = 0.7
max_tokens = 64000
thinking = true
thinking_budget = 31999

[layers.timeline]
model = "claude-sonnet-4-5-20250514"
temperature = 0.3
max_tokens = 64000
thinking = true
thinking_budget = 31999

[layers.scene]
model = "claude-sonnet-4-5-20250514"
temperature = 0.7
max_tokens = 64000
thinking = false

[retry]
max_retries = 3
initial_delay = 1.0
max_delay = 60.0
exponential_base = 2.0
```

### 環境変数

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...  # MPBV 用
```

---

## CLI コマンド体系

### 基本コマンド

```bash
# 新規ストーリー開始 + 実行
mlsg run "ファンタジー世界で魔法使いの少年が..."
mlsg run -f seed.txt
mlsg run "seed text" --name my_story    # 名前を明示指定

# 途中まで実行
mlsg run "seed text" --until mpbv
mlsg run "seed text" --until chapter

# 特定レイヤーのみ
mlsg run --from runs/my_story/ --only scene

# 既存から再開
mlsg run --from runs/my_story/
mlsg run --from runs/my_story/ --until character
```

### 出力オプション

```bash
mlsg run "seed" --stream      # Scene をリアルタイム表示
mlsg run "seed" --quiet       # 進捗バーのみ
mlsg run "seed" --verbose     # 全レイヤー出力を表示
```

### 確認・エクスポート

```bash
mlsg status                   # 最新 run の状態
mlsg status runs/my_story/    # 特定 run の状態

mlsg export                   # 最新 run を Markdown 出力
mlsg export runs/my_story/ -o story.md
```

### 設定

```bash
mlsg config show              # 現在の設定を表示
mlsg config path              # config.toml のパスを表示
```

---

## Run ディレクトリ

### 命名規則

1. `--name` 指定時: `runs/{name}/`
2. 未指定時: Claude Haiku で seed から短い名前を自動生成
   - 例: `runs/魔法使いの旅立ち/`, `runs/forgotten_kingdom/`
   - 記号は除去、日本語・英数字は許可
   - 正規表現: `[^\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]` を除去

### ディレクトリ構造

```
runs/
└── 魔法使いの旅立ち/
    ├── config.toml           # この run で使用した設定のスナップショット
    ├── state_00_init.json
    ├── state_01_plot.json
    ├── state_02_backstory.json
    ├── state_03_mpbv.json
    ├── state_04_character.json
    ├── state_05_stylist.json
    ├── state_06_chapter_01.json
    ├── state_06_chapter_02.json
    ├── ...
    ├── state_07_timeline_01.json
    ├── state_08_scene_01_01.json
    ├── state_08_scene_01_02.json
    ├── ...
    ├── state_final.json      # 最終状態
    └── story.md              # エクスポートされた物語
```

---

## 永続化

### StoryState のシリアライズ

```python
def to_json(state: StoryState) -> str:
    """Serialize StoryState to JSON."""
    ...

def from_json(json_str: str) -> Result[StoryState, StoryError]:
    """Deserialize StoryState from JSON."""
    ...
```

---

## パイプライン API

### 基本シグネチャ

```python
def run_pipeline(
    state: StoryState,
    client: LLMClient,
    config: Config,
    *,
    until: LayerName | None = None,
    only: LayerName | None = None,
    stream: bool = False,
    on_progress: Callable[[str, float], None] | None = None,
) -> Result[StoryState, StoryError]:
    """Run the story generation pipeline."""
    ...

LayerName = Literal[
    "plot", "backstory", "mpbv", "character",
    "stylist", "chapter", "timeline", "scene"
]
```

### 個別レイヤー関数

```python
def generate_master_plot(
    state: StoryState, client: LLMClient, config: LayerConfig
) -> Result[StoryState, StoryError]: ...

def generate_backstories(
    state: StoryState, client: LLMClient, config: LayerConfig
) -> Result[StoryState, StoryError]: ...

def validate_mpbv(
    state: StoryState, client: LLMClient, config: LayerConfig
) -> Result[StoryState, StoryError]: ...

def generate_characters(
    state: StoryState, client: LLMClient, config: LayerConfig
) -> Result[StoryState, StoryError]: ...

def generate_stylist(
    state: StoryState, client: LLMClient, config: LayerConfig
) -> Result[StoryState, StoryError]: ...

def generate_chapter(
    state: StoryState, client: LLMClient, config: LayerConfig, chapter_index: int
) -> Result[StoryState, StoryError]: ...

def generate_timeline(
    state: StoryState, client: LLMClient, config: LayerConfig, chapter_index: int
) -> Result[StoryState, StoryError]: ...

def generate_scene(
    state: StoryState, client: LLMClient, config: LayerConfig,
    chapter_index: int, scene_index: int
) -> Result[StoryState, StoryError]: ...
```

---

## プロンプトテンプレート

### テンプレート形式

Jinja2 を使用:

```markdown
# prompts/05_chapter.md
あなたは中編小説の「シリーズ構成作家」です。
...

## Master Plot & Backstories
{{ mpbv }}

## Characters
{{ characters }}

## Previous Chapter
{{ previous_chapter_summary }}
```

### テンプレート変数

| 変数名 | 型 | 説明 |
|--------|-----|------|
| `seed_input` | str | ユーザー入力のシード |
| `master_plot` | str | MasterPlot.raw_markdown |
| `backstories` | str | Backstories.raw_markdown |
| `mpbv` | str | MPBV の結合 Markdown |
| `characters` | str | Character リストの Markdown |
| `stylist` | str | Stylist.raw_markdown |
| `chapter_index` | int | 現在の章番号 |
| `previous_chapter_summary` | str | 前章の要約 |
| `previous_chapter_intent` | str | 前章の next_chapter_intent |
| `timeline` | str | TimelineSlice の JSON 文字列 |
| `scene_index` | int | 現在のシーン番号 |
| `previous_scenes` | str | 前シーンのテキスト (直近 3 シーン) |

---

## ロギング

### ログレベル

| レベル | 用途 |
|--------|------|
| DEBUG | LLM リクエスト/レスポンス詳細、テンプレート展開結果 |
| INFO | レイヤー開始/完了、進捗、トークン使用量 |
| WARNING | リトライ発生、パース再試行 |
| ERROR | 最終的な失敗 |

### 構造化ログ

```python
logger.info(
    "layer_completed",
    layer="chapter",
    chapter_index=3,
    tokens_used=1523,
    duration_ms=4521,
)
```

### 進捗表示 (CLI)

```
[1/8] Plot Layer... ✓ (2.3s, 1.2k tokens)
[2/8] Backstory Layer... ✓ (3.1s, 2.1k tokens)
[3/8] MPBV Layer... ✓ (5.2s, 3.4k tokens)
[4/8] Character Layer... ✓ (2.8s, 1.8k tokens)
[5/8] Stylist Layer... ✓ (1.5s, 0.9k tokens)
[6/8] Chapter Layer...
      Chapter 1/5 ✓
      Chapter 2/5 ✓
      Chapter 3/5 (generating...)
```

---

## パース責務

各レイヤー関数がパースを担当:

```python
def parse_chapter_json(raw: str) -> Result[Chapter, StoryError]:
    """Parse the JSON output from Chapter Layer prompt."""
    ...

def parse_timeline_json(raw: str, chapter_index: int) -> Result[TimelineSlice, StoryError]:
    """Parse the JSON output from Timeline Layer prompt."""
    ...

def parse_scene_markdown(raw: str) -> Result[tuple[str, str], StoryError]:
    """Parse Scene output into (text, next_scene_intent)."""
    ...
```

### パース失敗時のリカバリ

1. JSON/Markdown のパースに失敗した場合、LLM に再生成を依頼
2. プロンプトにエラー内容を含めて再試行
3. `max_parse_retries` 回失敗したら `Failure` を返す

---

## ディレクトリ構造

```
src/mlsg/
├── __init__.py
├── domain.py          # ドメイン型定義
├── errors.py          # エラー型定義
├── result.py          # Result ラッパー
├── config.py          # 設定読み込み
├── cli.py             # CLI エントリポイント
├── pipeline.py        # オーケストレーション
├── layers/            # 各レイヤー実装
│   ├── __init__.py
│   ├── plot.py
│   ├── backstory.py
│   ├── mpbv.py
│   ├── character.py
│   ├── stylist.py
│   ├── chapter.py
│   ├── timeline.py
│   └── scene.py
├── llm/               # LLM クライアント
│   ├── __init__.py
│   ├── client.py      # LLMClient 実装
│   ├── prompts.py     # テンプレート読み込み・展開
│   └── retry.py       # リトライロジック
├── persistence.py     # シリアライズ
└── logging.py         # ロギング設定

config.toml            # デフォルト設定
prompts/
├── 01_master_plot.md
├── 02_backstory.md
├── 03_master_plot_and_backstory_validation.md
├── 04_charactor.md
├── 05_chapter.md
├── 06_timeline.md
├── 07_stylist.md
└── 08_scene.md
```
