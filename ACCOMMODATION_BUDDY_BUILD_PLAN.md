# Accommodation Buddy — Build Plan for Claude Code

## 1. Project Overview

**Accommodation Buddy** is a web application that helps teachers accommodate lesson materials for multilingual learners (MLLs). Teachers upload documents (PDFs, DOCX, PPTX, worksheets) and the system uses LLMs to generate targeted accommodations based on each student's English and heritage-language (L1) proficiency.

### Core Workflow

1. **Teacher uploads lesson materials** (PDF, DOCX, PPTX, images).
2. **OCR / text extraction pass** using DeepSeek via Ollama extracts structured text.
3. **Teacher reviews extracted content** in a UI showing the document alongside accommodation "bubbles."
4. **Accommodation modules** (powered by a user-selected Ollama model) generate scaffolding suggestions.
5. **Teacher accepts, revises, or rejects** each suggestion; accepted items are compiled into modified materials.

### Architecture Principles

The system is designed around **three key extensibility goals:**

1. **Plugin-based feature modules.** Every feature (sentence frames, cognates, vocabulary, etc.) is a self-registering plugin that conforms to a shared protocol. Adding a new feature means dropping a single Python file into `plugins/` — the registry discovers it automatically. No edits to routers, templates, or config files required.

2. **Composable document view.** The document view is a **panel host** — the main content pane on the left, and a dynamic right sidebar that renders whichever plugin panels the teacher has enabled. Each plugin declares its own HTMX partial template and toolbar icon. Plugins can inject UI into the document view without touching the document view's own template.

3. **Toggleable features via main menu.** A global **Feature Manager** (accessible from the main nav) lets teachers turn modules on/off per-class. This is persisted in the database and controls which plugins appear in the document view sidebar, which accommodation types are generated, and which student-facing tools are available. Future features (like the live-video "Pause the Teacher" mode) can be added as disabled-by-default plugins that teachers opt into.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Package / env manager | `uv` (Python) |
| Language | Python 3.12+ |
| Web framework | FastAPI + Jinja2 templates (server-rendered with HTMX for interactivity) |
| LLM runtime | Ollama (local) |
| OCR model | `deepseek-r1` or `deepseek-v2` via Ollama (for initial document OCR/extraction) |
| Scaffolding model | User-specified at launch (e.g., `llama3`, `mistral`, `deepseek-v2`) |
| Database | PostgreSQL 16 (student profiles, class rosters, proficiency data, documents) |
| Task queue | Redis + Celery (async document processing) |
| File storage | Local volume mount (`./data/uploads`) |
| Containerization | Docker Compose |
| Frontend interactivity | HTMX + Alpine.js (minimal JS, server-driven UI) |

---

## 3. Service Architecture (Docker Compose)

```yaml
# docker-compose.yml — services overview
services:
  app:           # FastAPI web server
  worker:        # Celery worker for async LLM / OCR jobs
  ollama:        # Ollama model server
  postgres:      # PostgreSQL database
  redis:         # Message broker for Celery
```

### 3.1 `app` — FastAPI Web Server

- Serves the teacher-facing UI.
- Exposes REST + HTMX endpoints for document upload, accommodation generation, student management.
- Communicates with Ollama via HTTP (`http://ollama:11434`).
- Connects to Postgres for persistence and Redis for task dispatch.

### 3.2 `worker` — Celery Worker

- Runs long-running tasks: OCR extraction, accommodation generation, batch proficiency evaluation.
- Same Python codebase as `app`, different entrypoint.

### 3.3 `ollama` — LLM Server

- Runs Ollama with GPU passthrough (if available) or CPU fallback.
- On first boot, pulls the DeepSeek model for OCR and the user-specified scaffolding model.
- Exposed only to internal Docker network.

### 3.4 `postgres` — Database

- Stores all persistent state (users, students, classes, documents, accommodations, proficiency data).

### 3.5 `redis` — Message Broker

- Celery broker + result backend.

---

## 4. Directory Structure

```
accommodation-buddy/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml              # uv / Python project config
├── uv.lock
├── README.md
├── .env.example
├── scripts/
│   ├── entrypoint.sh           # App entrypoint (run migrations, start uvicorn)
│   ├── worker_entrypoint.sh    # Celery worker entrypoint
│   └── pull_models.sh          # Pull Ollama models on first run
├── src/
│   └── accommodation_buddy/
│       ├── __init__.py
│       ├── main.py             # FastAPI app factory + plugin loader
│       ├── config.py           # Settings (env vars, model names)
│       ├── cli.py              # CLI entrypoint (argparse for model selection)
│       │
│       ├── db/
│       │   ├── models.py       # SQLAlchemy ORM models
│       │   ├── session.py      # DB session factory
│       │   └── migrations/     # Alembic migrations
│       │
│       ├── api/
│       │   ├── routes/
│       │   │   ├── auth.py
│       │   │   ├── documents.py
│       │   │   ├── students.py
│       │   │   ├── classes.py
│       │   │   ├── features.py         # Feature toggle CRUD endpoints
│       │   │   └── assessment.py
│       │   └── deps.py                 # Dependency injection
│       │
│       ├── core/                        # ← Plugin architecture core
│       │   ├── __init__.py
│       │   ├── registry.py             # PluginRegistry — discovers + manages all plugins
│       │   ├── base_plugin.py          # Abstract base class / protocol for plugins
│       │   ├── feature_manager.py      # Per-class feature toggle logic
│       │   └── panel_host.py           # Document view panel composition engine
│       │
│       ├── plugins/                     # ← Each feature is a self-contained plugin
│       │   ├── __init__.py             # Auto-discovery: imports all .py in this dir
│       │   ├── ocr.py                  # DeepSeek OCR (always-on, not toggleable)
│       │   ├── sentence_frames.py      # Sentence Frames Generator
│       │   ├── frontloaded_vocab.py    # Frontloaded Language Identifier
│       │   ├── instruction_explainer.py
│       │   ├── cognates.py             # Cognates Identifier
│       │   ├── teacher_strategy.py     # Teacher Strategy Talk
│       │   ├── language_assessment.py  # Language Assessment Dialogue
│       │   ├── new_language_dialogue.py
│       │   ├── glossary.py             # Personal Language Glossary
│       │   └── pause_teacher.py        # Future: Pause-the-Teacher video mode (stub)
│       │
│       ├── services/                    # Shared, non-plugin services
│       │   ├── ollama_client.py        # Shared Ollama HTTP client
│       │   └── document_parser.py      # DOCX/PPTX text extraction (non-LLM)
│       │
│       ├── tasks/
│       │   ├── __init__.py
│       │   ├── celery_app.py
│       │   └── plugin_tasks.py         # Generic task runner that dispatches to any plugin
│       │
│       ├── templates/
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   ├── document_view.html      # Panel host — left doc + right sidebar of plugin panels
│       │   ├── feature_manager.html    # Main menu feature toggles UI
│       │   ├── student_list.html
│       │   ├── assessment_chat.html
│       │   └── plugin_panels/          # Each plugin registers its own partial here
│       │       ├── _panel_wrapper.html # Shared wrapper: collapse/expand, loading state
│       │       ├── sentence_frames.html
│       │       ├── vocab_card.html
│       │       ├── instruction_explainer.html
│       │       ├── cognates.html
│       │       ├── strategy_panel.html
│       │       └── pause_teacher.html  # Future stub
│       └── static/
│           ├── css/
│           ├── js/
│           │   ├── panel_host.js       # Alpine.js: sidebar panel management
│           │   └── feature_toggles.js  # Alpine.js: toggle switch interactions
│           └── img/
├── tests/
│   ├── conftest.py
│   ├── test_registry.py
│   ├── test_feature_manager.py
│   ├── test_ocr.py
│   ├── test_sentence_frames.py
│   └── ...
└── data/
    └── uploads/                # Volume-mounted file storage
```

---

## 5. Database Schema (Core Models)

```
Teacher
  id, name, email, password_hash, created_at

Class
  id, teacher_id (FK), name, grade_level, created_at

Student
  id, class_id (FK), pseudonym, heritage_language, 
  english_proficiency_level, l1_proficiency_level,
  proficiency_notes (JSON), created_at

Document
  id, class_id (FK), teacher_id (FK), filename, 
  file_path, file_type (pdf/docx/pptx/image),
  extracted_text, ocr_status (pending/processing/complete/failed),
  created_at

Accommodation
  id, document_id (FK), plugin_id (string — matches plugin registry key),
  target_student_id (FK, nullable — null means class-wide),
  input_context (JSON), generated_output (JSON),
  status (pending/generated/accepted/revised/rejected),
  revised_text (nullable), created_at

LanguageAssessment
  id, student_id (FK), conversation_log (JSON),
  english_score, l1_score, assessed_at

GlossaryEntry
  id, student_id (FK), term, definition, 
  l1_translation, context_sentence, source_document_id (FK),
  created_at

FeatureToggle                    ← NEW: per-class feature enable/disable
  id, class_id (FK), plugin_id (string),
  enabled (bool, default=true),
  config_overrides (JSON, nullable — plugin-specific settings),
  updated_at

PluginState                      ← NEW: plugin runtime state per document session
  id, document_id (FK), plugin_id (string),
  panel_order (int — position in sidebar),
  collapsed (bool, default=false),
  last_run_at (datetime, nullable)
```

### Feature Toggle Behavior

- When a teacher enables/disables a feature via the Feature Manager, a `FeatureToggle` row is upserted.
- The document view queries `FeatureToggle` to determine which plugin panels to render in the sidebar.
- Some plugins are **always-on** (OCR) and are not toggleable.
- New plugins default to **disabled** unless explicitly opted into — this is important for experimental features like "Pause the Teacher."
- `config_overrides` allows per-class customization (e.g., cognates module configured for Spanish vs. French).

---

## 6. Plugin Architecture

### 7.0 Plugin Registry + Base Class (`core/`)

This is the foundation for all features. Build this FIRST in Phase 1.

#### `base_plugin.py` — Abstract Base Class

Every feature plugin inherits from this. The base class defines the contract for how features register themselves, declare their UI, and execute.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

class PluginCategory(Enum):
    DOCUMENT_ACCOMMODATION = "document_accommodation"  # Shows in doc view sidebar
    STUDENT_TOOL = "student_tool"                      # Student-facing (assessment, dialogue)
    TEACHER_TOOL = "teacher_tool"                      # Teacher-facing (strategy talk)
    LIVE_MODE = "live_mode"                            # Real-time features (pause teacher)

@dataclass
class PluginManifest:
    """Declarative metadata — each plugin defines one of these."""
    id: str                          # Unique key, e.g. "sentence_frames"
    name: str                        # Human-readable, e.g. "Sentence Frames Generator"
    description: str                 # Shown in Feature Manager UI
    category: PluginCategory
    icon: str                        # Lucide icon name for toolbar/sidebar
    default_enabled: bool = True     # Whether enabled by default for new classes
    always_on: bool = False          # If True, cannot be disabled (e.g., OCR)
    requires_student_profile: bool = True  # Needs per-student proficiency data
    requires_document: bool = True         # Needs uploaded doc context
    panel_template: str | None = None      # Path to Jinja2 partial for doc view sidebar
    config_schema: dict | None = None      # JSON Schema for config_overrides
    order_hint: int = 50             # Default sort position in sidebar (lower = higher)

class BasePlugin(ABC):
    """All plugins inherit from this."""

    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Return the plugin's declarative manifest."""
        ...

    @abstractmethod
    async def generate(
        self,
        document_text: str,
        student_profile: "StudentProfile | None",
        class_profile: "ClassProfile | None",
        options: dict,
    ) -> "AccommodationResult":
        """Run the plugin's core logic. Options include config_overrides from FeatureToggle."""
        ...

    def get_panel_context(self, document_id: int, student_id: int | None) -> dict:
        """Optional: return extra template context for the sidebar panel."""
        return {}

    def register_routes(self, router: "APIRouter") -> None:
        """Optional: register any plugin-specific API routes (e.g., chat endpoints)."""
        pass

    def register_tasks(self) -> list["CeleryTask"]:
        """Optional: register Celery tasks for async processing."""
        return []
```

#### `registry.py` — Plugin Discovery + Management

```python
class PluginRegistry:
    """
    Singleton registry. On app startup:
    1. Scans the plugins/ directory
    2. Imports each module
    3. Finds all BasePlugin subclasses
    4. Instantiates and registers them
    5. Calls register_routes() and register_tasks() for each
    """

    _plugins: dict[str, BasePlugin]  # keyed by manifest.id

    def discover(self, plugins_dir: Path) -> None: ...
    def get(self, plugin_id: str) -> BasePlugin | None: ...
    def get_all(self) -> list[BasePlugin]: ...
    def get_by_category(self, cat: PluginCategory) -> list[BasePlugin]: ...
    def get_enabled_for_class(self, class_id: int, db: Session) -> list[BasePlugin]: ...
```

Auto-discovery in `plugins/__init__.py`:
```python
# Automatically import all .py files in this directory so that
# subclasses of BasePlugin are registered when the package loads.
from pathlib import Path
import importlib

for f in Path(__file__).parent.glob("*.py"):
    if f.name != "__init__.py":
        importlib.import_module(f".{f.stem}", package=__name__)
```

#### `feature_manager.py` — Toggle Logic

```python
class FeatureManager:
    """
    Provides the business logic for enabling/disabling plugins per class.
    Used by:
      - Feature Manager UI (main menu)
      - Document view (which panels to render)
      - Accommodation generation (which plugins to run)
    """

    async def get_enabled_plugins(self, class_id: int) -> list[PluginManifest]: ...
    async def set_enabled(self, class_id: int, plugin_id: str, enabled: bool) -> None: ...
    async def set_config(self, class_id: int, plugin_id: str, config: dict) -> None: ...
    async def get_toggle_state(self, class_id: int) -> list[FeatureToggleView]: ...
```

#### `panel_host.py` — Document View Composition

```python
class PanelHost:
    """
    Composes the document view sidebar.
    Queries FeatureManager for enabled plugins, then for each:
      1. Resolves the plugin's panel_template
      2. Calls get_panel_context() for template variables
      3. Renders the panel inside _panel_wrapper.html
      4. Returns ordered HTML fragments for HTMX injection
    """

    async def render_sidebar(
        self, document_id: int, class_id: int, student_id: int | None
    ) -> list[RenderedPanel]: ...

    async def render_single_panel(
        self, plugin_id: str, document_id: int, student_id: int | None
    ) -> str: ...
```

### How the Document View Works

```
┌─────────────────────────────────────────────────────────────────┐
│  Toolbar: [📄 Doc] [👤 Student Picker] [⚡ Run All] [⚙ Manage] │
├──────────────────────────────┬──────────────────────────────────┤
│                              │  Plugin Sidebar (via PanelHost)  │
│   Document Content           │  ┌────────────────────────────┐  │
│   (extracted text,           │  │ ▾ Sentence Frames      [▶] │  │
│    original formatting)      │  │   Level 1: "The main..."   │  │
│                              │  │   Level 2: "The framers..." │  │
│   Questions:                 │  │   [Accept] [Revise] [Skip] │  │
│   1. What were the main...   │  ├────────────────────────────┤  │
│   2. What were some of...    │  │ ▾ Frontloaded Vocab    [▶] │  │
│   3. Why was the principle.. │  │   • "amendment" — rare     │  │
│                              │  │   • "ratify" — academic    │  │
│                              │  │   [Accept] [Revise] [Skip] │  │
│                              │  ├────────────────────────────┤  │
│                              │  │ ▾ Cognates             [▶] │  │
│                              │  │   quadratic → cuadrático   │  │
│                              │  │   [Accept] [Revise] [Skip] │  │
│                              │  ├────────────────────────────┤  │
│                              │  │ ▸ Instruction Explainer    │  │
│                              │  │   (collapsed — click to    │  │
│                              │  │    expand and run)         │  │
│                              │  └────────────────────────────┘  │
└──────────────────────────────┴──────────────────────────────────┘
```

- Each panel is an HTMX partial loaded on demand.
- `[▶]` button triggers the plugin's `generate()` via `POST /api/plugins/{plugin_id}/run`.
- "Run All" triggers every enabled plugin in parallel via Celery tasks.
- `[⚙ Manage]` opens the Feature Manager to toggle modules.
- Panels are **draggable** to reorder (order saved to `PluginState.panel_order`).
- Panels remember collapsed/expanded state across sessions.

### How to Add a New Plugin (Developer Guide)

To add a new feature to Accommodation Buddy:

1. **Create `plugins/my_feature.py`** — implement `BasePlugin`:
```python
class MyFeaturePlugin(BasePlugin):
    def manifest(self):
        return PluginManifest(
            id="my_feature",
            name="My Feature",
            description="Does something useful for MLL teachers",
            category=PluginCategory.DOCUMENT_ACCOMMODATION,
            icon="sparkles",
            panel_template="plugin_panels/my_feature.html",
            default_enabled=False,  # teacher opts in
        )

    async def generate(self, document_text, student_profile, class_profile, options):
        # Your LLM call or logic here
        ...
```

2. **Create `templates/plugin_panels/my_feature.html`** — the sidebar panel partial:
```html
{# Extends _panel_wrapper.html automatically #}
<div class="accommodation-result">
  {{ result.generated_output | safe }}
  {% include "plugin_panels/_accept_reject_buttons.html" %}
</div>
```

3. **Done.** The registry auto-discovers it. It appears in the Feature Manager. Teachers can toggle it on.

No changes needed to: `main.py`, `document_view.html`, any router files, or Docker config.

---

## 7. Feature Modules — Implementation Breakdown

### 7.1 OCR / Text Extraction (`services/ocr.py`)

**Purpose:** Extract structured text from uploaded documents.

**Implementation:**
- **PDF/Images:** Send to DeepSeek model via Ollama with a vision prompt. For multi-page PDFs, convert each page to an image using `pdf2image` (poppler), then send each page sequentially to DeepSeek.
- **DOCX:** Use `python-docx` for direct text extraction (no LLM needed).
- **PPTX:** Use `python-pptx` for direct text extraction (no LLM needed).
- Fall back to DeepSeek OCR for scanned/image-heavy documents.

**Ollama call pattern:**
```python
# POST http://ollama:11434/api/generate
{
    "model": "deepseek-r1",  # or configured OCR model
    "prompt": "Extract all text from this document image. Preserve structure, headings, and formatting. Return as markdown.",
    "images": ["<base64_encoded_page>"]
}
```

**Celery task:** `ocr_tasks.process_document` — runs asynchronously after upload.

---

### 7.2 Language Assessment Dialogue (`services/language_assessment.py`)

**Purpose:** Chat-based proficiency evaluation for new students in English and L1.

**Implementation:**
- Multi-turn chat via Ollama's `/api/chat` endpoint.
- System prompt instructs the model to:
  - Ask progressively complex questions in English.
  - Switch to L1 and repeat.
  - Internally rate responses on a rubric (e.g., WIDA-aligned levels 1–6).
  - After N turns, output a structured JSON proficiency summary.
- Conversation log stored in `LanguageAssessment.conversation_log`.
- Final proficiency scores written to `Student.english_proficiency_level` and `Student.l1_proficiency_level`.

**UI:** Chat interface at `/assessment/{student_id}` — rendered with HTMX for streaming responses.

**System prompt template:**
```
You are a friendly, patient language assessment assistant. Your goal is to evaluate
a student's reading and writing proficiency in {language}.

Rubric levels:
1 - Entering: Single words, memorized phrases
2 - Emerging: Short phrases, simple sentences with errors
3 - Developing: Expanded sentences, emerging paragraph-level writing
4 - Expanding: Organized paragraphs, some academic language
5 - Bridging: Near grade-level, cohesive and varied language
6 - Reaching: Grade-level proficiency

Ask questions that progress from Level 1 to Level 6. Stop when the student
consistently struggles. After {max_turns} turns, output:
{"proficiency_level": <int>, "evidence": "<summary>", "strengths": [...], "areas_for_growth": [...]}
```

---

### 7.3 New Language Dialogue (`services/new_language_dialogue.py`)

**Purpose:** Practice conversations requiring use of newly taught language concepts.

**Implementation:**
- Teacher specifies target language skills (vocabulary, grammar structures, etc.).
- LLM conducts a dialogue that naturally elicits use of those skills.
- Provides feedback in both English and L1.
- On completion, new terms are automatically added to the student's glossary.

**Inputs:** Target skills list, student proficiency data, L1.
**Outputs:** Conversation transcript, feedback summary, glossary entries.

---

### 7.4 Personal Language Glossary (`services/glossary.py`)

**Purpose:** Non-LLM tool tracking each student's vocabulary acquisition.

**Implementation:**
- CRUD operations on `GlossaryEntry` model.
- Entries are created automatically from New Language Dialogue and Frontloaded Vocab modules.
- Teachers and students can manually add entries.
- Searchable and filterable by source document, date, language.

---

### 7.5 Sentence Frames Generator (`services/sentence_frames.py`)

**Purpose:** Generate scaffolded sentence frames/starters based on passage + questions + student proficiency.

**Prompt template:**
```
Given the following passage and comprehension questions, generate sentence frames
at proficiency level {level} (1=most scaffolded, 6=least scaffolded).

Passage:
{document_text}

Questions:
{questions}

Student English proficiency: {english_level}
Student L1: {heritage_language}
Student L1 proficiency: {l1_level}

Generate:
1. Sentence frames for each question (appropriate scaffolding level)
2. Sentence starters as alternatives
3. Optional: L1 bridge phrases if L1 proficiency > English proficiency

Output as JSON:
{
  "frames": [{"question": "...", "frame": "...", "starter": "...", "l1_bridge": "..."}],
  "scaffolding_rationale": "..."
}
```

---

### 7.6 Frontloaded Language Identifier (`services/frontloaded_vocab.py`)

**Purpose:** Identify vocabulary that should be pre-taught before a lesson.

**Implementation — two-stage pipeline:**

1. **Non-LLM stage:**
   - Tokenize document text.
   - Score each token against word frequency data (use `wordfreq` Python library as a proxy for n-gram rarity).
   - Cross-reference against an academic vocabulary gazetteer (e.g., Averil Coxhead's Academic Word List or NGSL).
   - Flag words above a rarity threshold OR in the academic gazetteer.

2. **LLM stage:**
   - Send flagged words + document context to the scaffolding model.
   - Prompt for: definitions, L1 analogues, suggested images/graphic organizers, teaching strategies.

**Outputs:** List of vocabulary cards with definitions, L1 connections, and teaching strategy suggestions.

---

### 7.7 Instruction Explainer (`services/instruction_explainer.py`)

**Purpose:** Generate L1 explanations of activity instructions at appropriate proficiency level.

**Prompt template:**
```
You are helping a teacher create accessible instructions for a multilingual learner.

Original instructions (English):
{instructions}

Student L1: {heritage_language}
Student L1 proficiency level: {l1_level}
Student English proficiency level: {english_level}

Generate:
1. Instructions rewritten in {heritage_language} at proficiency level {l1_level}
2. A simple diagram or description of the task flow (text-based)
3. Two comprehension check questions the teacher can ask to verify understanding
   (e.g., "Once your group finishes data collection, what should the recorder do?")

Output as JSON.
```

---

### 7.8 Cognates Identifier (`services/cognates.py`)

**Purpose:** Find words with shared etymological roots between English and the student's L1.

**Implementation — two approaches (configurable):**

1. **Non-LLM approach:**
   - Maintain a multilingual cognates lookup table (start with English–Spanish, English–French, English–Portuguese).
   - Store as a simple JSON or SQLite table keyed by `(english_word, target_language) → cognate`.
   - Query for each content word in the document.

2. **LLM approach (fallback for unsupported language pairs):**
   - Few-shot structured prompt with examples of cognate identification.
   - Model outputs: `{"english_term": "quadratic", "l1_cognate": "cuadrático", "root": "Latin quadratus", "teaching_note": "Link to 'cuadrado' (square) in Spanish"}`

**Outputs:** Cognate pairs with teaching notes for the teacher's materials.

---

### 7.9 Teacher Strategy Talk (`services/teacher_strategy.py`)

**Purpose:** Given class-wide proficiency data and lesson materials, suggest grouping strategies and activities.

**Prompt template:**
```
You are an expert MLL instructional coach. Given the following class data and lesson
materials, suggest teaching strategies.

Class roster (pseudonyms):
{roster_json}

Lesson materials summary:
{document_summary}

Accepted accommodations so far:
{accommodations_summary}

Generate:
1. Recommended grouping strategy (heterogeneous/homogeneous) with rationale
2. Suggested group compositions (using student pseudonyms)
3. Group-specific activity modifications
4. Materials to generate (slides with group members, instruction cards, etc.)

Output as JSON.
```

---

## 8. Future / Experimental Features

These features are **stubbed as plugins** so the architecture is ready, but implementation is deferred.

### 8.1 Pause the Teacher — Live Video Mode (`plugins/pause_teacher.py`)

**Category:** `PluginCategory.LIVE_MODE`
**Default enabled:** `False`
**Requires:** WebRTC or screen-capture integration

**Concept:** During live instruction (video call or in-person with a projected screen), the teacher can "pause" their delivery and the system captures the current visual (slide, whiteboard, demo) plus recent audio transcript. The accommodation plugins then run in real-time against the captured frame to generate on-the-fly scaffolding for MLLs — sentence frames for the current discussion, vocabulary highlights, L1 bridges.

**Plugin stub:**

```python
class PauseTeacherPlugin(BasePlugin):
    def manifest(self):
        return PluginManifest(
            id="pause_teacher",
            name="Pause the Teacher",
            description="Live video pause mode — capture current instruction and generate real-time accommodations",
            category=PluginCategory.LIVE_MODE,
            icon="pause-circle",
            default_enabled=False,       # Experimental — teacher must opt in
            always_on=False,
            requires_student_profile=True,
            requires_document=False,      # Works from live capture, not uploaded docs
            panel_template="plugin_panels/pause_teacher.html",
            order_hint=90,               # Appears last in sidebar
        )

    async def generate(self, document_text, student_profile, class_profile, options):
        # Phase 1 stub: raise NotImplementedError
        # Phase 2: accept a base64 frame + transcript from the client
        # Phase 3: fan out to enabled accommodation plugins against the captured content
        raise NotImplementedError("Pause the Teacher is planned for a future release")
```

**Architecture notes for future implementation:**
- Client-side: JavaScript captures the current video frame (via `canvas.toDataURL()`) and buffers recent audio (via Web Audio API or MediaRecorder).
- On "pause," client POSTs frame + audio to `POST /api/plugins/pause_teacher/capture`.
- Server transcribes audio (Whisper via Ollama or a dedicated service), combines with OCR of the frame.
- The combined text is then fanned out to whichever accommodation plugins the teacher has enabled — reusing the exact same `generate()` interface as document-mode plugins.
- Results stream back to the teacher's screen via SSE/HTMX as real-time accommodation cards.

**Infrastructure hooks already in place:**
- The plugin registers in the Feature Manager so teachers can toggle it on.
- `PluginCategory.LIVE_MODE` is a distinct category so the UI can render live-mode plugins differently (e.g., full-screen overlay vs. sidebar panel).
- The `requires_document=False` flag tells PanelHost to skip this plugin when rendering the document view, but include it in a separate "Live Tools" toolbar.

### 8.2 Adding Your Own Future Features

Because of the plugin architecture, any future feature follows the same pattern:

1. Create `plugins/your_feature.py` with a `BasePlugin` subclass
2. Set `default_enabled=False` in the manifest
3. Create `templates/plugin_panels/your_feature.html`
4. The Feature Manager picks it up automatically
5. Teachers toggle it on when ready

Examples of potential future plugins:
- **Reading Level Adjuster** — rewrite passages at a specific Lexile/grade level
- **Visual Vocabulary Cards** — generate images for new vocabulary using a multimodal model
- **Parent Communication** — generate L1 letters home summarizing what was learned
- **Speech Practice** — voice-based pronunciation exercises using speech recognition
- **Collaborative Translation** — students contribute translations that improve the system

---

## 9. CLI Interface

The application is launched via a Python CLI that accepts the scaffolding model name:

```bash
# Using uv to run
uv run accommodation-buddy serve \
    --scaffolding-model mistral \
    --ocr-model deepseek-r1 \
    --port 8000

# Or via docker compose (model specified in .env)
SCAFFOLDING_MODEL=mistral OCR_MODEL=deepseek-r1 docker compose up
```

**`cli.py` arguments:**

| Flag | Default | Description |
|---|---|---|
| `--scaffolding-model` | `llama3` | Ollama model name for accommodation generation |
| `--ocr-model` | `deepseek-r1` | Ollama model name for OCR/text extraction |
| `--port` | `8000` | Web server port |
| `--host` | `0.0.0.0` | Web server bind address |
| `--workers` | `1` | Uvicorn worker count |
| `--db-url` | `postgresql://...` | Database connection string |
| `--redis-url` | `redis://redis:6379` | Redis connection string |
| `--ollama-url` | `http://ollama:11434` | Ollama server URL |

---

## 10. Docker Compose Configuration

```yaml
version: "3.9"

services:
  app:
    build: .
    command: >
      uv run accommodation-buddy serve
        --scaffolding-model ${SCAFFOLDING_MODEL:-llama3}
        --ocr-model ${OCR_MODEL:-deepseek-r1}
    ports:
      - "${APP_PORT:-8000}:8000"
    volumes:
      - ./data/uploads:/app/data/uploads
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      ollama:
        condition: service_started

  worker:
    build: .
    command: >
      uv run celery -A accommodation_buddy.tasks.celery_app worker
        --loglevel=info --concurrency=2
    volumes:
      - ./data/uploads:/app/data/uploads
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      ollama:
        condition: service_started

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    # Pull models on start
    entrypoint: >
      sh -c "ollama serve &
             sleep 5 &&
             ollama pull ${OCR_MODEL:-deepseek-r1} &&
             ollama pull ${SCAFFOLDING_MODEL:-llama3} &&
             wait"

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: accommodation_buddy
      POSTGRES_USER: ${DB_USER:-buddy}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-buddypass}
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-buddy}"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  pg_data:
  redis_data:
  ollama_data:
```

---

## 11. Dockerfile

```dockerfile
FROM python:3.12-slim

# Install system deps (poppler for pdf2image, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files and install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY scripts/ scripts/
COPY alembic.ini ./

RUN chmod +x scripts/*.sh

EXPOSE 8000

CMD ["scripts/entrypoint.sh"]
```

---

## 12. Build Phases

### Phase 1 — Foundation (Infrastructure + Plugin Architecture + OCR)
- [ ] Initialize `pyproject.toml` with `uv init`
- [ ] Set up Docker Compose with all five services
- [ ] Implement `config.py` with CLI argument parsing
- [ ] Set up PostgreSQL with Alembic migrations for core models (`Teacher`, `Class`, `Student`, `Document`, `FeatureToggle`, `PluginState`)
- [ ] **Implement `core/base_plugin.py`** — the `BasePlugin` ABC and `PluginManifest` dataclass
- [ ] **Implement `core/registry.py`** — auto-discovery of plugins from the `plugins/` directory
- [ ] **Implement `core/feature_manager.py`** — per-class toggle logic with DB persistence
- [ ] **Implement `core/panel_host.py`** — document view sidebar composition engine
- [ ] Wire plugin discovery into `main.py` app startup (scan plugins, register routes/tasks)
- [ ] Implement `services/ollama_client.py` — shared async HTTP client for Ollama
- [ ] Implement `plugins/ocr.py` — DeepSeek OCR as an always-on plugin
- [ ] Implement document upload endpoint + Celery task dispatch
- [ ] Build basic UI: login, dashboard, document upload, extracted text viewer
- [ ] **Milestone:** Teacher can upload a PDF and see extracted text. Plugin registry loads OCR plugin automatically.

### Phase 2 — Feature Manager UI + Document View Shell
- [ ] Build **Feature Manager page** (`feature_manager.html`) — grid of all discovered plugins with toggle switches, descriptions, icons, and per-class config
- [ ] Build **document view** as a two-column panel host: left = document content, right = dynamic sidebar
- [ ] Implement `_panel_wrapper.html` with collapse/expand, loading spinner, run button
- [ ] Wire HTMX: `POST /api/plugins/{plugin_id}/run` → triggers `generate()` → returns partial HTML to the panel
- [ ] Implement "Run All" button that dispatches Celery tasks for all enabled plugins
- [ ] Implement drag-to-reorder for sidebar panels (persist to `PluginState.panel_order`)
- [ ] **Milestone:** Teacher sees Feature Manager with toggles. Document view renders empty panels for enabled plugins with working run buttons.

### Phase 3 — Student Management + Assessment
- [ ] Implement student/class CRUD endpoints and UI
- [ ] Implement `plugins/language_assessment.py` — chat-based proficiency assessment (student-facing plugin)
- [ ] Build assessment chat UI with HTMX streaming
- [ ] Store proficiency results in `Student` model
- [ ] **Milestone:** Teacher can add students, run assessment dialogues, see proficiency levels

### Phase 4 — Core Accommodation Plugins
- [ ] Implement `plugins/sentence_frames.py`
- [ ] Implement `plugins/frontloaded_vocab.py` (non-LLM frequency analysis + LLM strategies)
- [ ] Implement `plugins/instruction_explainer.py`
- [ ] Implement `plugins/cognates.py` (lookup table + LLM fallback)
- [ ] Create corresponding `templates/plugin_panels/*.html` for each
- [ ] Implement accept/revise/reject workflow per accommodation (shared component)
- [ ] **Milestone:** Teacher uploads a doc, selects students, toggles on modules, and receives accommodation suggestions in the sidebar. Each plugin "just works" via the registry.

### Phase 5 — Advanced Plugins
- [ ] Implement `plugins/teacher_strategy.py` — grouping and strategy recommendations
- [ ] Implement `plugins/new_language_dialogue.py` — student practice dialogues
- [ ] Implement `plugins/glossary.py` — personal language glossary CRUD
- [ ] Auto-populate glossary from other plugins
- [ ] Stub `plugins/pause_teacher.py` — registers in Feature Manager as disabled, raises NotImplementedError on generate()
- [ ] **Milestone:** Full feature parity with planning document. Pause the Teacher visible in Feature Manager but flagged as experimental.

### Phase 6 — Polish + Export
- [ ] Export accommodated materials as modified DOCX/PPTX/PDF
- [ ] Batch accommodation generation for entire class
- [ ] Teacher dashboard with class-wide proficiency overview
- [ ] Error handling, logging, retry logic for Ollama calls
- [ ] Tests: `test_registry.py`, `test_feature_manager.py`, `test_panel_host.py`, + each plugin
- [ ] Documentation and README

---

## 13. Key Python Dependencies

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "celery[redis]>=5.4",
    "httpx>=0.27",
    "python-multipart>=0.0.9",
    "python-docx>=1.1",
    "python-pptx>=1.0",
    "pdf2image>=1.17",
    "Pillow>=10.0",
    "wordfreq>=3.1",
    "python-magic>=0.4",
    "passlib[bcrypt]>=1.7",
    "pydantic-settings>=2.0",
]
```

---

## 14. Environment Variables (`.env.example`)

```bash
# Models
SCAFFOLDING_MODEL=llama3
OCR_MODEL=deepseek-r1

# Database
DB_USER=buddy
DB_PASSWORD=buddypass
DB_HOST=postgres
DB_PORT=5432
DB_NAME=accommodation_buddy
DATABASE_URL=postgresql+asyncpg://buddy:buddypass@postgres:5432/accommodation_buddy

# Redis
REDIS_URL=redis://redis:6379/0

# Ollama
OLLAMA_URL=http://ollama:11434

# App
APP_PORT=8000
SECRET_KEY=change-me-in-production
```

---

## 15. Notes for Claude Code Implementation

- **Build the plugin architecture FIRST (Phase 1).** `base_plugin.py`, `registry.py`, `feature_manager.py`, and `panel_host.py` are the foundation. Every feature depends on them. Get a single plugin (OCR) registering and discoverable before building any other feature.
- **Test with a dummy plugin.** Before implementing real features, create a `plugins/_test_plugin.py` that returns hardcoded output. Verify it shows up in the Feature Manager, renders a panel in the document view, and can be toggled on/off.
- **Start with Phase 1.** Get Docker Compose running with all services healthy before writing any feature code.
- **Test Ollama connectivity first.** Write a small script that hits the Ollama API and generates a response before building the OCR pipeline.
- **Use async throughout.** FastAPI + `httpx.AsyncClient` for Ollama calls, `asyncpg` for database.
- **HTMX for interactivity.** Avoid building a separate SPA frontend. Server-render HTML, use HTMX for dynamic updates (panel loading, chat streaming, accept/reject actions, feature toggles).
- **Prompt templates belong in their plugin files**, not in a separate prompts directory. Keep prompt + logic co-located within each plugin.
- **The document view is a panel host**, not a monolithic template. The left side shows the extracted document. The right sidebar is composed dynamically by `PanelHost` based on which plugins are enabled. Each plugin owns its own partial template.
- **Feature Manager UI** should be a clean grid/list of all discovered plugins with: icon, name, description, toggle switch, optional "Configure" button for plugins with `config_schema`. Group by `PluginCategory`.
- **The mockup shows** a document viewer on the right with the original content (questions) and accommodation overlays (sentence starters at different levels, L1 phrase links). This maps directly to the panel host model: each overlay is a plugin panel.
- **Proficiency levels** should follow WIDA framework (levels 1–6) as a sensible default, but make the rubric configurable via `FeatureToggle.config_overrides`.
- **Cognate tables** — start with English–Spanish only (largest MLL population in US), then expand. Seed data can be generated by prompting the LLM to produce a cognates list and then manually curating.
- **The `wordfreq` library** provides word frequency data for 40+ languages and is a good proxy for identifying rare/academic vocabulary without an external API dependency (replacing the Google Ngram API mentioned in the planning doc).
- **"Pause the Teacher"** should be stubbed as a plugin immediately (Phase 5) so it appears in the Feature Manager as "Coming Soon" / disabled. The actual WebRTC/capture implementation comes later but the architectural hooks (LIVE_MODE category, `requires_document=False`) should be in place from the start.
- **Every new feature is a plugin.** If you find yourself adding a feature that isn't a plugin, refactor it into one. The only non-plugin code should be infrastructure (auth, DB, Ollama client, file upload).

---
---

# Appendix A — AWS Deployment

## A.1 Architecture Overview

```
                         ┌──────────────┐
                         │  CloudFront  │
                         │   (CDN)      │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │     ALB      │
                         │ (public, HTTPS)│
                         └──────┬───────┘
                                │
                 ┌──────────────┼──────────────┐
                 │              │              │
          ┌──────▼──────┐ ┌────▼────┐  ┌──────▼──────┐
          │  ECS Fargate│ │  ECS    │  │  ECS Fargate│
          │  App Service│ │ Fargate │  │  App Service│
          │  (FastAPI)  │ │ (Celery │  │  (FastAPI)  │
          │  Task x2    │ │ Worker) │  │  Task x2    │
          └──────┬──────┘ └────┬────┘  └──────┬──────┘
                 │             │              │
      ┌──────────┼─────────────┼──────────────┼──────────┐
      │          │    Private Subnets (VPC)    │          │
      │  ┌───────▼────────┐  ┌────────▼──────────────┐   │
      │  │  Internal ALB  │  │                        │   │
      │  │  (LLM traffic) │  │                        │   │
      │  └───────┬────────┘  │                        │   │
      │          │           │                        │   │
      │  ┌───────▼────────┐  │  ┌──────────────────┐  │   │
      │  │  EC2 g5.xlarge │  │  │  RDS PostgreSQL  │  │   │
      │  │  (Ollama +     │  │  │  (Multi-AZ)      │  │   │
      │  │   GPU models)  │  │  └──────────────────┘  │   │
      │  │  ASG: 1-3      │  │                        │   │
      │  └────────────────┘  │  ┌──────────────────┐  │   │
      │                      │  │  ElastiCache      │  │   │
      │                      │  │  Redis (cluster)  │  │   │
      │                      │  └──────────────────┘  │   │
      │                      │                        │   │
      │         ┌────────────▼──────────────┐         │   │
      │         │          S3               │         │   │
      │         │  (document uploads,       │         │   │
      │         │   exported materials)     │         │   │
      │         └───────────────────────────┘         │   │
      └───────────────────────────────────────────────────┘
```

## A.2 Docker Compose → AWS Service Mapping

| Docker Compose Service | AWS Service | Config Notes |
|---|---|---|
| `app` (FastAPI) | **ECS Fargate** | Same Dockerfile. 2+ tasks behind ALB. 512 CPU / 1024 MiB per task is fine to start. |
| `worker` (Celery) | **ECS Fargate** | Same Dockerfile, different command. Scale tasks based on SQS/Redis queue depth. |
| `ollama` | **EC2 g5.xlarge** (Option A) | Ollama on a GPU instance behind an internal ALB. See §A.4 for alternatives. |
| `postgres` | **RDS PostgreSQL 16** | db.t4g.medium for dev, db.r6g.large for prod. Multi-AZ. |
| `redis` | **ElastiCache Redis 7** | cache.t4g.micro for dev, cache.r7g.large for prod. Single-node or cluster. |
| `data/uploads` volume | **S3** | Private bucket, server-side encryption, lifecycle rules for cleanup. |

## A.3 Code Changes Required

### A.3.1 LLM Client Abstraction (`services/llm_client.py`)

Rename `ollama_client.py` to `llm_client.py` and introduce a backend strategy pattern so the plugin layer is completely decoupled from the inference provider:

```python
from abc import ABC, abstractmethod

class LLMBackend(ABC):
    """All LLM backends implement this interface."""

    @abstractmethod
    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str: ...

    @abstractmethod
    async def chat(self, model: str, messages: list[dict], stream: bool = False) -> AsyncIterator[str] | str: ...

class OllamaBackend(LLMBackend):
    """Local or remote Ollama server. Used for Docker Compose + EC2 GPU deployments."""

    def __init__(self, base_url: str = "http://ollama:11434"):
        self.base_url = base_url

    async def generate(self, model, prompt, images=None):
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/api/generate", json={
                "model": model, "prompt": prompt, "images": images or [], "stream": False
            })
            return resp.json()["response"]

    async def chat(self, model, messages, stream=False):
        # ... same pattern with /api/chat
        ...

class BedrockBackend(LLMBackend):
    """AWS Bedrock. Use for serverless inference with no GPU management."""

    MODEL_MAP = {
        "llama3": "meta.llama3-1-70b-instruct-v1:0",
        "mistral": "mistral.mistral-large-2407-v1:0",
        "claude": "anthropic.claude-sonnet-4-20250514",
    }

    def __init__(self):
        import boto3
        self.client = boto3.client("bedrock-runtime")

    async def generate(self, model, prompt, images=None):
        # Map model name → Bedrock model ID, call invoke_model
        ...

class SageMakerBackend(LLMBackend):
    """SageMaker real-time endpoints. Use for dedicated model hosting with autoscaling."""

    def __init__(self, endpoint_name: str):
        import boto3
        self.client = boto3.client("sagemaker-runtime")
        self.endpoint_name = endpoint_name

    async def generate(self, model, prompt, images=None):
        # Call invoke_endpoint with the prompt payload
        ...
```

**Config selection** in `config.py`:

```python
class Settings(BaseSettings):
    llm_backend: str = "ollama"  # "ollama" | "bedrock" | "sagemaker"
    ollama_url: str = "http://ollama:11434"
    sagemaker_endpoint: str = ""
    scaffolding_model: str = "llama3"
    ocr_model: str = "deepseek-r1"

def get_llm_backend(settings: Settings) -> LLMBackend:
    match settings.llm_backend:
        case "ollama":
            return OllamaBackend(settings.ollama_url)
        case "bedrock":
            return BedrockBackend()
        case "sagemaker":
            return SageMakerBackend(settings.sagemaker_endpoint)
```

Every plugin receives the `LLMBackend` via dependency injection — plugins never know or care which backend is active.

### A.3.2 File Storage Abstraction (`services/file_storage.py`)

Same pattern — abstract the storage layer:

```python
class StorageBackend(ABC):
    @abstractmethod
    async def upload(self, file_path: str, content: bytes, content_type: str) -> str: ...

    @abstractmethod
    async def download(self, file_path: str) -> bytes: ...

    @abstractmethod
    async def get_url(self, file_path: str, expires_in: int = 3600) -> str: ...

    @abstractmethod
    async def delete(self, file_path: str) -> None: ...

class LocalStorageBackend(StorageBackend):
    """Filesystem storage for Docker Compose / local dev."""
    def __init__(self, base_dir: str = "./data/uploads"):
        self.base_dir = Path(base_dir)
    # ... read/write files to disk

class S3StorageBackend(StorageBackend):
    """S3 storage for AWS deployments."""
    def __init__(self, bucket: str, region: str = "us-west-2"):
        import boto3
        self.s3 = boto3.client("s3", region_name=region)
        self.bucket = bucket

    async def upload(self, file_path, content, content_type):
        self.s3.put_object(Bucket=self.bucket, Key=file_path, Body=content, ContentType=content_type)
        return f"s3://{self.bucket}/{file_path}"

    async def get_url(self, file_path, expires_in=3600):
        return self.s3.generate_presigned_url("get_object",
            Params={"Bucket": self.bucket, "Key": file_path}, ExpiresIn=expires_in)
```

### A.3.3 Summary of Code Touches

| File | Change | Lines (est.) |
|---|---|---|
| `services/ollama_client.py` → `services/llm_client.py` | Add `LLMBackend` ABC + 3 implementations | ~200 |
| NEW `services/file_storage.py` | `StorageBackend` ABC + Local + S3 | ~120 |
| `config.py` | Add `llm_backend`, `s3_bucket`, backend factory functions | ~40 |
| `api/deps.py` | Inject `LLMBackend` and `StorageBackend` via FastAPI deps | ~20 |
| `api/routes/documents.py` | Replace `open()` / `shutil` with `StorageBackend` calls | ~30 |
| `plugins/*.py` | No changes — they use `LLMBackend` via DI | 0 |
| `tasks/plugin_tasks.py` | Initialize backend from settings in worker context | ~10 |
| **Total** | | **~420 lines** |

## A.4 LLM Backend Options (Detailed)

### Option A — Ollama on EC2 GPU (Recommended for Start)

**Least code change. Best model flexibility. You keep the `--scaffolding-model` CLI flag.**

```
EC2 g5.xlarge (1x A10G, 24GB VRAM)
├── Ollama server running as systemd service
├── Models pulled on boot via user-data script
└── Exposed on port 11434 behind internal ALB
```

**Instance setup (user-data script):**

```bash
#!/bin/bash
# Install NVIDIA drivers + Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models (passed via instance tags or SSM Parameter Store)
MODELS=$(aws ssm get-parameter --name /accommodation-buddy/models --query 'Parameter.Value' --output text)
for model in $MODELS; do
    ollama pull "$model"
done

systemctl enable ollama
systemctl start ollama
```

**Auto Scaling Group config:**
- Min: 1, Max: 3, Desired: 1
- Scale on: internal ALB request count or custom CloudWatch metric (queue depth)
- Use `g5.xlarge` ($1.01/hr on-demand, ~$0.36/hr spot) for single-model workloads
- Use `g5.2xlarge` ($1.21/hr) if running OCR + scaffolding models simultaneously

**Cost estimate (dev):** ~$730/mo for a single always-on g5.xlarge. Drop to ~$260/mo with spot instances and a schedule that shuts down overnight.

### Option B — SageMaker Real-Time Endpoints

**Better for production scale. Higher ops overhead upfront.**

```python
# Deploy a model to SageMaker (one-time setup script)
import sagemaker
from sagemaker.huggingface import HuggingFaceModel

model = HuggingFaceModel(
    model_data="s3://my-bucket/models/llama3-8b/model.tar.gz",
    role="arn:aws:iam::role/SageMakerRole",
    transformers_version="4.37",
    pytorch_version="2.1",
    py_version="py310",
    image_uri="763104351884.dkr.ecr.us-west-2.amazonaws.com/huggingface-pytorch-tgi-inference:2.1-tgi1.4-gpu-py310-cu121-ubuntu22.04"
)

predictor = model.deploy(
    instance_type="ml.g5.xlarge",
    initial_instance_count=1,
    endpoint_name="accommodation-buddy-llm"
)
```

**Pros:** Managed scaling, model versioning, A/B testing, built-in monitoring.
**Cons:** Cold start latency (~60s if scaled to zero), more complex deployment pipeline, model packaging.

### Option C — Bedrock (Serverless, No GPUs)

**Simplest ops. Pay per token. No model management.**

**Pros:** Zero infrastructure for LLM serving. Scales instantly. Models maintained by AWS/providers.
**Cons:** No custom fine-tuned models (unless you use Bedrock Custom Model Import). Per-token cost is higher than self-hosted for heavy usage. No DeepSeek models available (as of early 2025 — check current availability). Loses the `--scaffolding-model` flexibility.

**Bedrock model availability relevant to this project:**
- Llama 3 / 3.1 (Meta) — good general scaffolding model
- Mistral Large — good multilingual capabilities
- Claude (Anthropic) — excellent at structured output and instruction following
- **DeepSeek is NOT on Bedrock** — you'd need a different OCR strategy (see §A.5)

**Cost estimate:** For a school with 5 teachers processing ~20 documents/day, roughly $50-150/mo depending on model and output length.

### Option D — Hybrid (Recommended for Production)

**Bedrock for scaffolding + EC2 GPU for OCR/specialized models.**

Use Bedrock for the accommodation generation plugins (sentence frames, instruction explainer, strategy talk — these work great with Llama/Mistral/Claude). Keep a single EC2 GPU instance running DeepSeek for OCR, since DeepSeek isn't available on Bedrock.

This gives you serverless scaling for the bulk of requests while keeping GPU costs contained to a single instance for OCR only.

```python
class Settings(BaseSettings):
    llm_backend: str = "bedrock"
    ocr_backend: str = "ollama"          # DeepSeek still on Ollama/EC2
    ollama_url: str = "http://internal-alb:11434"  # Only used for OCR
```

## A.5 OCR Without DeepSeek (If Fully Serverless)

If you go fully Bedrock/serverless and want to eliminate the GPU instance entirely, alternatives for the OCR pass:

| Approach | Pros | Cons |
|---|---|---|
| **Amazon Textract** | Managed, excellent OCR, table extraction, no GPU needed | $1.50/1000 pages, no LLM reasoning over layout |
| **Claude Vision (Bedrock)** | Can reason about document structure, great at markdown extraction | Higher per-page cost (~$0.01-0.05/page depending on size) |
| **Textract + LLM post-processing** | Best of both: Textract for raw OCR, LLM for structuring | Two-step pipeline, slightly more complex |

Recommended for serverless: **Textract for raw text extraction → Claude/Llama on Bedrock for structuring into markdown.** This replaces the DeepSeek OCR plugin without changing the plugin interface.

```python
class TextractOCRBackend:
    """Drop-in replacement for DeepSeek OCR when running on AWS without GPU."""

    def __init__(self):
        import boto3
        self.textract = boto3.client("textract")
        self.llm: LLMBackend  # injected

    async def extract(self, file_bytes: bytes) -> str:
        # Step 1: Textract raw extraction
        response = self.textract.detect_document_text(Document={"Bytes": file_bytes})
        raw_text = "\n".join(
            block["Text"] for block in response["Blocks"] if block["BlockType"] == "LINE"
        )
        # Step 2: LLM structures the raw text
        structured = await self.llm.generate(
            model="claude",  # or llama3
            prompt=f"Structure this OCR output into clean markdown, preserving headings and formatting:\n\n{raw_text}"
        )
        return structured
```

## A.6 Terraform Module Structure

```
infra/
├── main.tf                  # Provider config, state backend
├── variables.tf             # All configurable inputs
├── outputs.tf               # ALB URL, RDS endpoint, etc.
├── vpc.tf                   # VPC, subnets, NAT gateway, security groups
├── ecs.tf                   # ECS cluster, task definitions, services
│                            #   - app (FastAPI)
│                            #   - worker (Celery)
├── alb.tf                   # Public ALB for app, internal ALB for LLM
├── rds.tf                   # PostgreSQL instance, subnet group, security group
├── elasticache.tf           # Redis cluster
├── s3.tf                    # Upload bucket, lifecycle rules, CORS
├── ecr.tf                   # Container registry for app image
├── gpu.tf                   # EC2 GPU instance, ASG, launch template (Option A)
│                            #   OR SageMaker endpoint config (Option B)
├── iam.tf                   # Task execution roles, instance profiles
│                            #   - ECS task role (S3, Bedrock, SSM access)
│                            #   - EC2 instance role (SSM for model config)
├── cloudwatch.tf            # Log groups, alarms, dashboards
├── ssm.tf                   # Parameter Store for model names, secrets
├── cloudfront.tf            # Optional: CDN for static assets
│
├── environments/
│   ├── dev.tfvars           # Dev: small instances, single-AZ, spot GPU
│   ├── staging.tfvars       # Staging: prod-like but smaller
│   └── prod.tfvars          # Prod: multi-AZ, reserved instances
│
└── modules/                 # Reusable sub-modules
    ├── ecs-service/         # Generic ECS Fargate service
    ├── ollama-gpu/          # GPU instance + Ollama setup
    └── sagemaker-endpoint/  # SageMaker model deployment
```

**Key Terraform variables:**

```hcl
variable "environment" {
  type    = string
  default = "dev"
}

variable "llm_backend" {
  type        = string
  default     = "ollama"
  description = "LLM inference backend: ollama | bedrock | sagemaker"
  validation {
    condition     = contains(["ollama", "bedrock", "sagemaker"], var.llm_backend)
    error_message = "Must be one of: ollama, bedrock, sagemaker"
  }
}

variable "scaffolding_model" {
  type    = string
  default = "llama3"
}

variable "ocr_model" {
  type    = string
  default = "deepseek-r1"
}

variable "gpu_instance_type" {
  type    = string
  default = "g5.xlarge"
}

variable "gpu_use_spot" {
  type    = bool
  default = true  # Spot for dev, on-demand for prod
}

variable "app_desired_count" {
  type    = number
  default = 2
}

variable "worker_desired_count" {
  type    = number
  default = 1
}
```

## A.7 CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml (simplified)
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE }}
          aws-region: us-west-2

      - name: Build and push to ECR
        run: |
          aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY
          docker build -t $ECR_REGISTRY/accommodation-buddy:${{ github.sha }} .
          docker push $ECR_REGISTRY/accommodation-buddy:${{ github.sha }}

      - name: Run migrations
        run: |
          aws ecs run-task \
            --cluster accommodation-buddy \
            --task-definition accommodation-buddy-migrate \
            --overrides '{"containerOverrides":[{"name":"app","command":["alembic","upgrade","head"]}]}'

      - name: Deploy ECS services
        run: |
          # Update app service
          aws ecs update-service \
            --cluster accommodation-buddy \
            --service app \
            --force-new-deployment

          # Update worker service
          aws ecs update-service \
            --cluster accommodation-buddy \
            --service worker \
            --force-new-deployment
```

## A.8 Cost Estimates

### Dev / Pilot (1-5 teachers, ~20 docs/day)

| Resource | Spec | Monthly Cost |
|---|---|---|
| ECS Fargate (app, 2 tasks) | 0.5 vCPU / 1GB each | ~$30 |
| ECS Fargate (worker, 1 task) | 0.5 vCPU / 1GB | ~$15 |
| RDS PostgreSQL | db.t4g.micro, single-AZ | ~$13 |
| ElastiCache Redis | cache.t4g.micro | ~$12 |
| EC2 g5.xlarge (Ollama, spot) | Spot, schedule off nights/weekends | ~$120 |
| S3 | <1GB storage | ~$1 |
| ALB | 1 public + 1 internal | ~$35 |
| **Total (Option A, spot)** | | **~$226/mo** |

### Alternative: Bedrock-only (no GPU)

| Resource | Spec | Monthly Cost |
|---|---|---|
| ECS + RDS + Redis + ALB | Same as above | ~$105 |
| Bedrock inference | ~500 requests/day, mixed models | ~$75-150 |
| Textract (OCR) | ~600 pages/mo | ~$1 |
| **Total (Option C)** | | **~$180-255/mo** |

### Production (50+ teachers, district deployment)

| Resource | Spec | Monthly Cost |
|---|---|---|
| ECS Fargate (app, 4 tasks) | 1 vCPU / 2GB each | ~$120 |
| ECS Fargate (workers, 3 tasks) | 1 vCPU / 2GB each | ~$90 |
| RDS PostgreSQL | db.r6g.large, multi-AZ | ~$350 |
| ElastiCache Redis | cache.r7g.large, cluster | ~$200 |
| EC2 g5.2xlarge (Ollama, 2x, reserved) | Reserved 1yr | ~$650 |
| S3 + CloudFront | ~50GB, CDN for static | ~$15 |
| ALB + WAF | Public ALB + basic WAF rules | ~$55 |
| CloudWatch + alarms | Logs, metrics, dashboards | ~$30 |
| **Total (Option A, reserved)** | | **~$1,510/mo** |

## A.9 Security Considerations

- **VPC isolation:** All backend services (RDS, Redis, Ollama EC2, ECS tasks) in private subnets. Only the public ALB is internet-facing.
- **FERPA compliance:** S3 bucket encrypted with KMS. RDS encrypted at rest. No student PII in CloudWatch logs (scrub before logging). VPC flow logs for audit trail.
- **IAM least privilege:** ECS task roles scoped to specific S3 prefixes, specific Bedrock models, specific SSM parameters. No `*` policies.
- **Secrets management:** Database credentials, API keys, and `SECRET_KEY` stored in AWS Secrets Manager, injected into ECS tasks via `secrets` in task definition (not env vars in Terraform state).
- **Network:** Security groups restrict Ollama EC2 to only accept traffic from ECS tasks on port 11434. RDS accepts only from ECS tasks on 5432. Redis accepts only from ECS tasks on 6379.
- **Student data:** All document uploads and assessment logs are scoped to a teacher's account. Consider enabling S3 Object Lock for compliance if required by district policy.

## A.10 Migration Checklist

```
Phase 1 — Abstractions (do BEFORE touching AWS)
  [ ] Implement LLMBackend ABC + OllamaBackend (refactor from ollama_client.py)
  [ ] Implement StorageBackend ABC + LocalStorageBackend (refactor from file I/O)
  [ ] Wire both through FastAPI dependency injection
  [ ] Verify all tests pass with new abstractions (zero behavior change)

Phase 2 — AWS Backends
  [ ] Implement S3StorageBackend
  [ ] Implement BedrockBackend and/or SageMakerBackend
  [ ] Add integration tests with localstack (S3, Bedrock mock)

Phase 3 — Infrastructure
  [ ] Write Terraform modules (VPC, ECS, RDS, ElastiCache, S3)
  [ ] Write gpu.tf for Ollama EC2 (if Option A)
  [ ] Create ECR repository, push first image
  [ ] Deploy to dev environment
  [ ] Run Alembic migrations against RDS
  [ ] Smoke test: upload a document, run OCR, generate accommodations

Phase 4 — CI/CD + Hardening
  [ ] Set up GitHub Actions deploy pipeline
  [ ] Configure CloudWatch alarms (5xx rate, task failures, GPU utilization)
  [ ] Enable WAF on ALB with basic rule set
  [ ] Security review: IAM policies, security groups, encryption
  [ ] Load test: simulate 50 concurrent teachers

Phase 5 — Production
  [ ] Switch to reserved instances for steady-state resources
  [ ] Enable RDS Multi-AZ
  [ ] Set up automated backups (RDS snapshots, S3 versioning)
  [ ] Configure auto-scaling policies for ECS and GPU ASG
  [ ] Runbook documentation for ops team
```
