import json
from openai import OpenAI
from pydantic import ValidationError
from app.core.config import settings
from app.models import ConvertResponse, LLMRefinementPayload

SYSTEM_PROMPT = """You are a Power BI to Tableau Prep migration assistant.
Rules:
- Preserve parser-detected transformation order from the draft.
- Keep language beginner-friendly and implementation-focused.
- Do not invent operations that are not in parser-detected steps.
- Return JSON only with keys: summary, tableau_steps, flow_diagram, migration_notes.
"""


def _safe_parse_payload(text: str) -> LLMRefinementPayload | None:
    try:
        obj = json.loads(text)
        return LLMRefinementPayload.model_validate(obj)
    except (json.JSONDecodeError, ValidationError):
        return None


def refine_with_llm(m_code: str, draft: ConvertResponse) -> ConvertResponse:
    client = OpenAI(api_key=settings.openai_api_key)
    user_prompt = f"""
Power Query M Code:
{m_code}

Draft output to refine (preserve order and intent):
{draft.model_dump_json(indent=2)}
"""

    completion = client.responses.create(
        model=settings.openai_model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    payload = _safe_parse_payload(completion.output_text)
    if payload is None:
        return draft

    return ConvertResponse(
        summary=payload.summary,
        tableau_steps=payload.tableau_steps,
        flow_diagram=payload.flow_diagram,
        migration_notes=payload.migration_notes,
        parsed_steps=draft.parsed_steps,
    )
