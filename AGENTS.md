# AGENTS.md

RAG search system over G1 (globo) news articles for a TCC thesis. Python 3.11 (pinned `==3.11.13`), managed with uv. Content and prompts are in Portuguese.

## Commands

```bash
uv sync                          # install deps
docker compose up -d             # required services: pgvector Postgres (tcc-postgres) + Redis + DBpedia Spotlight pt (tcc-dbpedia-spotlight)
uv run pytest                    # all tests (integration — see Tests)
uv run pytest tests/test_search.py::test_load_schema   # single test
uv run python -m src --search "query"                  # CLI search
uv run python -m src --populate-chunks                 # other flags: --populate-embeddings, --populate-entities
uv run python -m src --canonicalize-entities           # entity linking backfill (junk + DBpedia URIs); --limit N for trials
uv run python src/api.py         # Flask API on :5000 (Redis-cached /search)
```

## Critical gotchas

- **Imports are flat, not packaged**: everything in `src/` imports as `from app import App`, `from config import ...` — never `from src.app import ...`. This works because `src/` is on `sys.path` via an editable install (`src/tcc.egg-info/` + a `.pth` in the venv). There is no `[build-system]` in pyproject, so a fresh venv may not get it; if you see `ModuleNotFoundError: app`, run `uv pip install -e .`.
- **`src/config.py` raises at import time** if `POSTGRES_DSN` is unset. `.env` is gitignored and must define: `POSTGRES_DSN`, `OLLAMA_HOST`, `GEMINI_API_KEY`. Note `OLLAMA_HOST`'s default (`http://paradiddle-earth:11434`) is machine-specific — always set it explicitly.
- **spaCy models are not in the lockfile**: `pt_core_news_sm` and `pt_core_news_lg` (3.8.0) were installed manually. `uv sync` will NOT restore them and `NERService` fails without them:
  ```bash
  uv pip install https://github.com/explosion/spacy-models/releases/download/pt_core_news_sm-3.8.0/pt_core_news_sm-3.8.0-py3-none-any.whl
  uv pip install https://github.com/explosion/spacy-models/releases/download/pt_core_news_lg-3.8.0/pt_core_news_lg-3.8.0-py3-none-any.whl
  ```
- **Don't bump pinned versions casually**: `torch==2.1.1` (from the `pytorch-cpu` explicit index) and `numpy==2.0.0` are deliberate pins.
- **DBpedia Spotlight container needs its model preloaded**: the image's built-in model downloader is broken (its Databus curl fails). If `tcc-dbpedia-spotlight` crash-loops with "Invalid Spotlight model folder", load the pt model into the `tcc_spotlight_models` volume manually:
  ```bash
  curl -sL -o /tmp/spotlight-pt.tar.gz "http://downloads.dbpedia.org/repo/dbpedia/spotlight/spotlight-model/2022.03.01/spotlight-model_lang=pt.tar.gz"
  docker run --rm -v tcc_spotlight_models:/opt/spotlight -v /tmp:/src alpine \
    sh -c "rm -rf /opt/spotlight/models/pt && mkdir -p /opt/spotlight/models && tar -xzf /src/spotlight-pt.tar.gz -C /opt/spotlight/models"
  docker compose restart dbpedia-spotlight   # JVM takes ~1 min to load the model
  ```
- **Entity linking is optional at runtime** (`SPOTLIGHT_ENDPOINT`, default `http://localhost:2222/rest`): `NERService` degrades gracefully — spaCy NER still extracts, entities just stay unlinked (`g1_entities.canonical` NULL → surface text is the identity). The graph in `ranking.ppr` groups entities by `coalesce(canonical, text)` and labels them from the DBpedia URI tail.

## Tests

- All tests are **integration tests** — they hit the live Postgres DB, Ollama, the Gemini API (litellm), the DBpedia Spotlight service, and even live g1.globo.com URLs. No mocks. They fail without the docker services and an Ollama server (embedding model `qwen3-embedding:0.6b`, 768 dims).
- Tests instantiate `App()` at module level (loads the spaCy model, creates DB engine), so even collection is slow and needs prerequisites.

## Architecture

- `src/` is the real app, layered: `models/` (SQLAlchemy) → `repositories/` (DB access) → `services/` (chunking, vectorizer, NER, ranking/PPR, search, summarizer) → wired together in `src/app.py` (`App`). Entry points: `src/__main__.py` (CLI) and `src/api.py` (Flask).
- The web UI is vanilla JS (ES modules, no build step): `src/templates/index.html` + `src/static/css/main.css` + `src/static/js/{app,api,timeline,graph}.js`. D3 is loaded via CDN. Flask serves `src/static/` at `/static/` automatically (no route config).
- Root-level scripts (`get_data.py`, `traverse_sitemap.py`, `populate_db.py`, `get_titles.py`, etc.) and `.ipynb` notebooks are one-off data-collection/exploration code, not part of the app — don't treat them as entry points.
- No CI, lint, typecheck, or formatter is configured. Don't look for one or add one unprompted.
