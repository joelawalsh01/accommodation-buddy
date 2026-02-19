# Architecture Guide

This document describes the internal architecture of Accommodation Buddy for engineers working on or extending the codebase.

## System Overview

Accommodation Buddy is a server-rendered web application built with FastAPI, Jinja2, and HTMX. It uses local LLMs via Ollama to generate educational accommodations for multilingual learners. There is no SPA frontend — the server renders full HTML pages with HTMX providing partial-page updates where interactivity is needed.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (HTMX)                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│                     FastAPI App (:8000)                          │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐  │
│  │  Routes   │  │  Deps.py  │  │ PanelHost │  │  Templates   │  │
│  │ (auth,    │  │ (session, │  │ (sidebar  │  │  (Jinja2     │  │
│  │  docs,    │  │  teacher, │  │  renderer)│  │   HTML)      │  │
│  │  classes) │  │  registry)│  │           │  │              │  │
│  └────┬─────┘  └─────┬─────┘  └─────┬─────┘  └──────────────┘  │
│       │              │              │                            │
│  ┌────▼──────────────▼──────────────▼─────────────────────────┐ │
│  │                    Plugin Registry                          │ │
│  │  (auto-discovers plugins/ at startup, singleton)            │ │
│  └────┬───────────────────────────────────────────────────────┘ │
│       │                                                         │
│  ┌────▼──────────────────────────────────────────────────┐      │
│  │               FeatureManager                           │      │
│  │  (queries feature_toggles table per class)             │      │
│  └────────────────────────────────────────────────────────┘      │
└──────┬──────────────────┬───────────────────┬───────────────────┘
       │                  │                   │
       ▼                  ▼                   ▼
┌──────────────┐  ┌───────────────┐  ┌────────────────┐
│  PostgreSQL  │  │    Redis      │  │    Ollama      │
│  (models,    │  │  (Celery      │  │  (qwen3:8b,    │
│   state)     │  │   broker)     │  │   deepseek-ocr,│
│  :5432       │  │  :6379        │  │   aya:8b)      │
└──────────────┘  └───────┬───────┘  │  :11434        │
                          │          └───────▲────────┘
                  ┌───────▼───────┐          │
                  │ Celery Worker │──────────┘
                  │ (OCR tasks,   │  HTTP API calls
                  │  plugin exec) │
                  └───────────────┘
```

## Request Lifecycle

### Page Load (e.g., Document View)

```
Browser GET /documents/5/12
    │
    ▼
FastAPI Route (documents.py:document_view)
    │
    ├── get_current_teacher() ← cookie auth via itsdangerous
    ├── db.get(Document, 12)
    ├── SELECT students WHERE class_id = 5
    ├── SELECT accommodations WHERE document_id = 12
    │
    ├── PanelHost.render_sidebar(doc_id, class_id, student_id, db)
    │       │
    │       ├── FeatureManager.get_enabled_plugins(class_id, db)
    │       │       │
    │       │       ├── PluginRegistry.get_all()  → all 11 manifests
    │       │       └── SELECT feature_toggles WHERE class_id = 5
    │       │               → filter to enabled-only manifests
    │       │
    │       └── For each enabled plugin with a panel_template:
    │               jinja_env.get_template(manifest.panel_template)
    │               template.render(plugin_id, result, accommodation, ...)
    │               → list of HTML panel strings
    │
    └── templates.TemplateResponse("document_view.html", {panels, ...})
            │
            ▼
        Full HTML page with sidebar panels
```

### Plugin Execution (HTMX "Run" button)

```
Browser POST /documents/api/plugins/sentence_frames/run
    (hx-post, form data: document_id, student_id, class_id)
    │
    ▼
FastAPI Route (documents.py:run_plugin_endpoint)
    │
    ├── registry.get("sentence_frames") → SentenceFramesPlugin instance
    ├── db.get(Document) → extracted_text
    ├── db.get(Student) → StudentProfile dataclass
    ├── db.get(Class) → ClassProfile dataclass
    │
    ├── plugin.generate(document_text, student_profile, class_profile, options)
    │       │
    │       ├── Format prompt from prompts.py templates
    │       └── OllamaClient.generate(prompt, system) → raw JSON string
    │               │
    │               └── POST http://ollama:11434/api/generate
    │                       model: qwen3:8b
    │                       → JSON response parsed into dict
    │
    ├── Save Accommodation row to DB
    └── Render plugin panel template with result
            │
            ▼
        HTML fragment (HTMX swaps into sidebar)
```

### Document Upload & OCR (Background Task)

```
Browser POST /documents/5/upload (multipart file)
    │
    ▼
FastAPI Route (documents.py:upload_document)
    │
    ├── Save file to data/uploads/{class_id}/{uuid}.ext
    ├── INSERT Document row (ocr_status="pending")
    ├── process_document_ocr.delay(doc.id)  → Celery task dispatched
    └── Redirect to /documents/5

                    ┌──────────────────────┐
                    │    Celery Worker      │
                    ├──────────────────────┤
                    │ process_document_ocr  │
                    │   │                  │
Meanwhile:          │   ├── status: "processing", "Initializing..."
Browser polls       │   │                  │
GET /documents/     │   ├── if DOCX/PPTX:  │
  5/status/12       │   │   extract_docx_text() / extract_pptx_text()
every 2s via HTMX   │   │                  │
    │               │   ├── if PDF:        │
    │               │   │   extract_pdf_pages_as_images()
    │               │   │   for each page:  │
    │               │   │     status: "OCR processing page 1 of 3..."
    │               │   │     OllamaClient.generate(
    │               │   │       model=deepseek-ocr,
    │               │   │       images=[base64_png])
    │               │   │                  │
    │               │   ├── doc.extracted_text = combined
    │               │   └── status: "complete", progress: 100
    │               └──────────────────────┘
    │
    ▼
Status endpoint returns <tr> HTML with
progress bar, status detail, and action button
```

## Plugin Architecture

### Plugin Contract

Every plugin extends `BasePlugin` (ABC) and implements two methods:

```python
class BasePlugin(ABC):
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """Return static metadata about this plugin."""

    @abstractmethod
    async def generate(
        self,
        document_text: str,
        student_profile: StudentProfile | None,
        class_profile: ClassProfile | None,
        options: dict,
    ) -> AccommodationResult:
        """Run the plugin and return structured output."""
```

### PluginManifest

```python
@dataclass
class PluginManifest:
    id: str                    # Unique slug (e.g., "sentence_frames")
    name: str                  # Human-readable name
    description: str           # Shown in feature manager
    category: PluginCategory   # DOCUMENT_ACCOMMODATION | STUDENT_TOOL | TEACHER_TOOL
    icon: str                  # Lucide icon name
    default_enabled: bool      # On by default for new classes?
    always_on: bool            # Can it be disabled? (OCR = always on)
    requires_student_profile: bool
    requires_document: bool
    panel_template: str | None # Jinja2 template path for sidebar panel
    config_schema: dict | None # JSON Schema for per-class config overrides
    order_hint: int            # Sidebar ordering (lower = higher)
```

### Auto-Discovery

```
PluginRegistry.discover()
    │
    ├── importlib.import_module("accommodation_buddy.plugins")
    ├── Iterate all .py files in plugins/ directory
    ├── For each module, find classes that subclass BasePlugin
    ├── Instantiate and call .manifest()
    └── Store in {manifest.id: plugin_instance} dict
```

The registry is a singleton — `PluginRegistry.get_instance()` returns the same instance everywhere. Discovery runs once at app startup.

### Adding a New Plugin

1. Create `src/accommodation_buddy/plugins/my_plugin.py`
2. Subclass `BasePlugin`, implement `manifest()` and `generate()`
3. Add your prompts to `core/prompts.py`
4. Optionally create `templates/plugin_panels/my_plugin.html` for sidebar rendering
5. Restart the app — auto-discovery handles the rest

No registration code, no imports to add. Drop the file in and it works.

## Data Model

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│   teachers   │     │   classes    │     │    students       │
├──────────────┤     ├──────────────┤     ├──────────────────┤
│ id (PK)      │◄──┐ │ id (PK)      │◄──┐ │ id (PK)          │
│ name         │   │ │ teacher_id(FK)│   │ │ class_id (FK)    │
│ email        │   │ │ name         │   │ │ pseudonym        │
│ password_hash│   │ │ grade_level  │   │ │ heritage_language│
│ created_at   │   │ │ created_at   │   │ │ english_prof_lvl │
└──────────────┘   │ └──────────────┘   │ │ l1_prof_level    │
                   │        │           │ │ proficiency_notes │
                   │        │           │ │ created_at       │
                   │        ▼           │ └──────────────────┘
                   │ ┌──────────────┐   │          │
                   │ │  documents   │   │          │
                   │ ├──────────────┤   │          │
                   │ │ id (PK)      │   │          │
                   ├─│ teacher_id   │   │          │
                   │ │ class_id (FK)│───┘          │
                   │ │ filename     │              │
                   │ │ file_path    │              │
                   │ │ file_type    │              │
                   │ │ extracted_text│             │
                   │ │ ocr_status   │              │
                   │ │ status_detail│              │
                   │ │ ocr_progress │              │
                   │ │ created_at   │              │
                   │ └──────┬───────┘              │
                   │        │                      │
                   │        ▼                      │
                   │ ┌──────────────────┐          │
                   │ │  accommodations  │          │
                   │ ├──────────────────┤          │
                   │ │ id (PK)          │          │
                   │ │ document_id (FK) │          │
                   │ │ plugin_id        │          │
                   │ │ target_student_id│──────────┘
                   │ │ input_context    │  (nullable FK)
                   │ │ generated_output │
                   │ │ status           │
                   │ │ revised_text     │
                   │ │ created_at       │
                   │ └──────────────────┘
                   │
                   │ ┌──────────────────┐   ┌──────────────────┐
                   │ │ feature_toggles  │   │  plugin_states   │
                   │ ├──────────────────┤   ├──────────────────┤
                   │ │ id (PK)          │   │ id (PK)          │
                   │ │ class_id (FK)    │   │ document_id (FK) │
                   │ │ plugin_id        │   │ plugin_id        │
                   │ │ enabled          │   │ panel_order      │
                   │ │ config_overrides │   │ collapsed        │
                   │ │ updated_at       │   │ last_run_at      │
                   │ └──────────────────┘   └──────────────────┘
                   │
                   │ ┌──────────────────┐   ┌──────────────────┐
                   │ │ language_         │   │ glossary_entries │
                   │ │ assessments      │   ├──────────────────┤
                   │ ├──────────────────┤   │ id (PK)          │
                   │ │ id (PK)          │   │ student_id (FK)  │
                   │ │ student_id (FK)  │   │ term             │
                   │ │ conversation_log │   │ definition       │
                   │ │ english_score    │   │ l1_translation   │
                   │ │ l1_score         │   │ context_sentence │
                   │ │ assessed_at      │   │ source_doc_id(FK)│
                   │ └──────────────────┘   │ created_at       │
                   │                        └──────────────────┘
```

9 tables total. All models use SQLAlchemy 2.0 `Mapped` annotations with async sessions via `asyncpg`.

## Key Architectural Decisions

### Server-Rendered UI with HTMX
No React/Vue/Angular. The server renders full HTML pages with Jinja2 templates. HTMX handles interactivity — form submissions return HTML fragments that get swapped into the DOM. This keeps the frontend simple, eliminates a build step, and means the entire app is one deployable unit.

### Local LLMs via Ollama (No Cloud APIs)
All AI inference runs locally through Ollama. This means:
- No API keys or billing
- Student data never leaves the school's network
- Teachers can run this on a laptop in an air-gapped classroom
- Model selection is configurable per-task (OCR, scaffolding, translation)

### Plugin Auto-Discovery
Plugins are discovered at runtime by scanning the `plugins/` directory. No manual registration, no config files. To add a plugin: drop a `.py` file into `plugins/`, subclass `BasePlugin`, restart. The registry, feature manager, and panel host all pick it up automatically.

### Centralized Prompts
All LLM system prompts and user prompt templates live in `core/prompts.py`. This makes it easy for non-technical users (curriculum specialists, ESL coaches) to tune AI behavior without touching plugin logic.

### Cookie-Based Auth (No Session Middleware)
Authentication uses `itsdangerous.URLSafeSerializer` to sign cookies directly. No Starlette SessionMiddleware. This avoids the Starlette assertion error that fires when anything touches `request.session` without the middleware installed, and keeps the auth layer minimal.

### Async Everything (Except Celery)
FastAPI routes use `async/await` throughout. Database access is via `asyncpg` + SQLAlchemy async sessions. The Ollama client uses `httpx.AsyncClient`. The only sync code runs in Celery workers, which spin up their own async event loops via `asyncio.new_event_loop()` to call the same async code paths.

## Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Web Framework | FastAPI 0.129 | ASGI, async-native |
| Templates | Jinja2 | Server-rendered HTML |
| Frontend | HTMX + Alpine.js | No build step, no SPA |
| CSS | Custom (single file) | `static/css/style.css` |
| ORM | SQLAlchemy 2.0 | Async sessions via asyncpg |
| Database | PostgreSQL 16 | Via Docker |
| Migrations | Alembic | Sync via psycopg2 |
| Task Queue | Celery 5.6 | Redis broker |
| LLM Client | httpx | Async HTTP to Ollama API |
| LLM Runtime | Ollama | Local inference, no cloud |
| Auth | itsdangerous | Signed cookies |
| Password Hash | bcrypt 5.0 | Direct library, not passlib |
| Package Manager | uv | Fast Python package management |
| Containerization | Docker Compose | 5 services |
| NLP Utilities | wordfreq | Vocabulary frequency analysis |

## File Map

```
accommodation_buddy/
│
├── config.py                  # Pydantic Settings — single source of truth for all config
├── main.py                    # create_app() factory — mounts routes, static, templates
├── cli.py                     # Click CLI — `accommodation-buddy serve`
│
├── core/
│   ├── base_plugin.py         # BasePlugin ABC, PluginManifest, StudentProfile, ClassProfile,
│   │                          #   AccommodationResult, PluginCategory enum
│   ├── registry.py            # PluginRegistry singleton — discover() + get(id) + get_all()
│   ├── feature_manager.py     # FeatureManager — get_enabled_plugins(class_id, db)
│   ├── panel_host.py          # PanelHost — render_sidebar() composites enabled panels
│   └── prompts.py             # ALL system prompts — single editable file
│
├── api/
│   ├── deps.py                # FastAPI Depends: get_db, get_registry, get_current_teacher, etc.
│   └── routes/
│       ├── auth.py            # POST /register, /login, /logout
│       ├── classes.py         # CRUD for classes
│       ├── students.py        # CRUD for students
│       ├── documents.py       # Upload, list, view, status polling, plugin execution
│       ├── features.py        # GET/POST feature toggles per class
│       └── assessment.py      # Multi-turn assessment chat
│
├── plugins/                   # Auto-discovered — each file = one plugin
│   ├── ocr.py                 # Document text extraction (always-on)
│   ├── translation.py         # English → Spanish translation
│   ├── sentence_frames.py     # WIDA-aligned sentence frames/starters
│   ├── frontloaded_vocab.py   # Rare word identification + vocab cards
│   ├── instruction_explainer.py # L1 instruction explanations
│   ├── cognates.py            # Cognate pair identification
│   ├── teacher_strategy.py    # Whole-class strategy generation
│   ├── language_assessment.py # Multi-turn WIDA assessment chat
│   ├── new_language_dialogue.py # Practice conversation partner
│   ├── glossary.py            # Personal glossary management (DB-only, no LLM)
│   └── pause_teacher.py       # Stub — not yet implemented
│
├── services/
│   ├── ollama_client.py       # Async HTTP client for Ollama (generate + chat + stream)
│   └── document_parser.py     # DOCX/PPTX/PDF extraction utilities
│
├── tasks/
│   ├── celery_app.py          # Celery app configuration
│   └── plugin_tasks.py        # process_document_ocr, run_plugin background tasks
│
├── db/
│   ├── models.py              # 9 SQLAlchemy ORM models
│   ├── session.py             # Async session factory + get_db dependency
│   └── migrations/            # Alembic migration scripts
│
├── templates/                 # Jinja2 HTML templates (15 files)
└── static/
    ├── css/style.css          # All app styles
    ├── css/document_view.css  # Document viewer specific styles
    └── js/
        ├── panel_host.js      # Sidebar panel interactions
        └── feature_toggles.js # HTMX toggle handlers
```
