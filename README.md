# Power Query M → Tableau Prep Migration Assistant

A production-oriented app that converts Power Query **M code** into beginner-friendly Tableau Prep migration guidance.

## What this app returns
1. Plain-English transformation explanation
2. Tableau Prep step-by-step instructions
3. Text flow representation
4. Migration notes / limitations

## Architecture (Increment 2)
- **Backend**: FastAPI
- **Frontend**: Streamlit
- **Core Conversion Engine**:
  - Deterministic parser that extracts `let` step assignments in order
  - Operation mapping from M operations to Tableau Prep equivalents
  - Optional LLM refinement layer with strict schema validation

## Quick start

### 1) Create environment
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure env
```bash
cp .env.example .env
```
Set `OPENAI_API_KEY` to enable LLM refinement.

### 3) Run backend
```bash
uvicorn app.main:app --reload --port 8000
```

### 4) Run frontend
```bash
streamlit run frontend/streamlit_app.py
```

## API endpoint
- `POST /api/v1/convert`

## Security & reliability notes
- API keys are loaded via environment variables.
- LLM output is validated against a strict schema before being returned.
- If LLM output is invalid JSON or schema-invalid, deterministic output is returned.

## Current limitations
- Multiline M expressions are only partially supported in this increment.
- Complex custom functions and deeply nested expressions may require manual migration.
