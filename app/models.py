from pydantic import BaseModel, Field


class ConvertRequest(BaseModel):
    m_code: str = Field(min_length=10, description="Raw Power Query M code")


class ParsedStep(BaseModel):
    step_name: str
    operation: str
    source_pattern: str
    tableau_equivalent: str
    explanation: str


class ConvertResponse(BaseModel):
    summary: str
    tableau_steps: list[str]
    flow_diagram: str
    migration_notes: list[str]
    parsed_steps: list[ParsedStep]


class LLMRefinementPayload(BaseModel):
    summary: str
    tableau_steps: list[str]
    flow_diagram: str
    migration_notes: list[str]
