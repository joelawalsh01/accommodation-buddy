# Accommodation Buddy

A web application that helps teachers accommodate lesson materials for multilingual learners (MLLs). Teachers upload classroom documents (PDFs, DOCX, PPTX, images), and AI-powered plugins generate scaffolded accommodations — sentence frames, vocabulary cards, translations, instructional strategies, and more — all calibrated to each student's ELPAC English proficiency level (1-4).

## Prerequisites

- **Docker Desktop** (v4.0+)
- **Ollama** installed locally with the following models pulled:
  ```bash
  ollama pull qwen3:8b        # Scaffolding (assessment, vocab, strategies, etc.)
  ollama pull deepseek-ocr     # Document OCR / text extraction
  ollama pull aya:8b           # Spanish translation
  ```

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/accommodation-buddy.git
cd accommodation-buddy

# 2. Create your environment file
cp .env.example .env

# 3. Start everything
docker compose up -d --build

# 4. Open in your browser
open http://localhost:8000
```

The first startup takes a minute while Docker builds the images and PostgreSQL initializes. Once you see the login page, register a teacher account and you're ready to go.

## Environment Configuration

All configuration is in `.env`. Key settings:

| Variable | Default | Description |
|---|---|---|
| `SCAFFOLDING_MODEL` | `qwen3:8b` | Ollama model for all scaffolding plugins |
| `OCR_MODEL` | `deepseek-ocr` | Ollama model for document text extraction |
| `TRANSLATION_MODEL` | `aya:8b` | Ollama model for Spanish translation |
| `SECRET_KEY` | `change-me-in-production` | Session signing key — change this |
| `DB_PASSWORD` | `buddypass` | PostgreSQL password |

## Services

| Service | Port | Description |
|---|---|---|
| **app** | `8000` | FastAPI web server |
| **worker** | — | Celery worker for background OCR/plugin tasks |
| **ollama** | `11434` | Local LLM inference (mounts `~/.ollama` from host) |
| **postgres** | `5432` | PostgreSQL 16 database |
| **redis** | `6379` | Celery task broker |

## Features

### Document Upload & OCR
Upload PDFs, DOCX, PPTX, or image files. The system automatically extracts text — DOCX/PPTX via native Python parsers, PDFs and images via the DeepSeek OCR model through Ollama. Real-time progress tracking shows each step (converting pages, loading model, processing page N of M).

### Sentence Frames Generator
Generates fill-in-the-blank sentence frames and sentence starters matched to a student's ELPAC proficiency level (1-4). Lower levels get heavily scaffolded frames; higher levels get open-ended starters. Includes L1 bridge hints that translate key academic terms into the student's heritage language.

### Frontloaded Vocabulary
Uses word-frequency analysis (via `wordfreq`) to identify rare and academic vocabulary in a document, then generates student-friendly vocabulary cards with simple definitions, heritage-language translations, and specific teaching strategies (gesture, visual cue, realia, example sentence).

### Spanish Translation
Translates classroom documents from English to Spanish, preserving all formatting, structure, bullet points, and scientific terminology. Uses a tuned multi-part prompt that enforces fidelity checks and grade-level-appropriate vocabulary. Powered by the Aya multilingual model.

### Instruction Explainer
Takes activity instructions from a document and explains them in the student's heritage language (or simplified English). Generates a step-by-step task flow with L1 glosses and comprehension check questions the teacher can use to verify understanding before the student begins.

### Cognates Identifier
Finds cognate pairs between English and the student's heritage language. For Spanish, uses a built-in dictionary of 120+ academic cognates with etymological roots and teaching notes. For other languages, uses AI to identify cognates from the document text.

### Teacher Strategy Talk
Generates whole-class instructional strategies: student grouping recommendations (based on proficiency data and shared L1), activity modifications tiered by ELPAC level, and a list of specific materials to prepare (anchor charts, graphic organizers, word walls, translated handouts). Follows SIOP, ELPAC, and Kagan cooperative learning frameworks.

### Language Assessment (ELPAC Chat)
Conducts an informal, multi-turn text-based assessment aligned to ELPAC levels 1-4. The AI evaluates reading and writing proficiency through a progressive conversation that mirrors ELPAC task types — describing, recounting, academic explaining, and justifying opinions. Produces an estimated proficiency level with evidence summary, strengths, and areas for growth.

### New Language Dialogue
Provides structured practice conversations for newly taught English language concepts. The AI acts as a supportive conversation partner, using recasting (modeling correct usage naturally) rather than explicit correction. Generates feedback summaries and glossary entries after the session.

### Model Settings (Per-Teacher)
Each teacher can choose which Ollama models to use for each role — scaffolding, OCR, and translation — via the Settings page (`/settings`). Models are only loaded into GPU/RAM when actually used (e.g., the translation model only loads when a teacher runs the Translation plugin). Settings include:

- **Model selection dropdowns** populated from available Ollama models, with a "System default" fallback option for each role
- **Memory management** — control how long models stay loaded after use: unload immediately, keep for 5 or 30 minutes, or keep indefinitely
- **Models in Memory** — live view of currently loaded models with one-click unload buttons (auto-refreshes every 10 seconds)

If no custom settings are saved, the system defaults from `.env` are used. Settings are stored per-teacher in the database, so each teacher can have different model preferences.

### Feature Toggle Manager
Per-class toggle system that lets teachers enable or disable individual plugins. Each class can have a different set of active accommodations.

## Editing AI Prompts

All system prompts live in a single file:

```
src/accommodation_buddy/core/prompts.py
```

The file is heavily commented with plain-English explanations of what each prompt does, what's safe to change, what not to touch, and ideas for improvement. Non-technical users can edit the AI's behavior by modifying this file — no other code changes needed.

## Project Structure

```
src/accommodation_buddy/
  api/
    routes/          # FastAPI route handlers (auth, classes, students, documents, settings, etc.)
    deps.py          # Dependency injection (DB sessions, auth, plugin registry)
  core/
    base_plugin.py   # Plugin ABC, manifest dataclass, shared types
    registry.py      # Auto-discovery plugin registry (singleton)
    feature_manager.py # Per-class plugin toggle logic
    panel_host.py    # Sidebar panel renderer
    prompts.py       # ALL system prompts in one place
  db/
    models.py        # SQLAlchemy ORM models (10 tables)
    session.py       # Async DB session factory
    migrations/      # Alembic migrations
  plugins/           # Self-registering accommodation plugins (11 total)
  services/
    ollama_client.py # Async Ollama HTTP client
    model_settings.py # Per-teacher model preference resolution
    document_parser.py # DOCX/PPTX/PDF text extraction
  tasks/
    celery_app.py    # Celery configuration
    plugin_tasks.py  # Background OCR and plugin execution tasks
  templates/         # Jinja2 HTML templates
  static/            # CSS and JS assets
  config.py          # Pydantic Settings (loads from .env)
  main.py            # FastAPI app factory
  cli.py             # CLI entry point
```

## Development

```bash
# Run locally without Docker (requires local Postgres, Redis, Ollama)
uv sync
uv run accommodation-buddy serve

# Run database migrations
DATABASE_URL="postgresql://buddy:buddypass@localhost:5432/accommodation_buddy" \
  uv run alembic upgrade head

# View logs
docker compose logs app --tail 50 -f
docker compose logs worker --tail 50 -f
```

## Acknowledgements
```
Thanks to Spencer Foundation, Ashley Marquez, and Oscar Arenas
```

## License

MIT
