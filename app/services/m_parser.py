import re
from dataclasses import dataclass
from app.models import ParsedStep


@dataclass(frozen=True)
class OperationRule:
    pattern: str
    operation: str
    tableau_equivalent: str


OPERATION_RULES = [
    OperationRule(r"Table\.RenameColumns", "Rename columns", "Clean Step > Rename Field"),
    OperationRule(r"Table\.TransformColumnTypes", "Change data types", "Clean Step > Change Data Type"),
    OperationRule(r"Table\.RemoveColumns", "Remove columns", "Clean Step > Remove Fields"),
    OperationRule(r"Table\.NestedJoin|Table\.Join", "Merge queries", "Join Step"),
    OperationRule(r"Table\.Combine", "Append queries", "Union Step"),
    OperationRule(r"Table\.AddColumn", "Calculated/conditional column", "Calculated Field in Clean Step"),
    OperationRule(r"Table\.Group", "Group by", "Aggregate Step"),
    OperationRule(r"Table\.Pivot", "Pivot", "Pivot Step"),
    OperationRule(r"Table\.Unpivot|Table\.UnpivotOtherColumns", "Unpivot", "Pivot Step (Unpivot)"),
    OperationRule(r"Table\.SelectRows", "Filter rows", "Clean Step > Filter"),
    OperationRule(r"Table\.Sort", "Sort rows", "Clean Step > Sort"),
]

STEP_LINE_PATTERN = re.compile(r'^\s*(?:#"(?P<quoted_name>[^"]+)"|(?P<name>[A-Za-z_][A-Za-z0-9_]*))\s*=\s*(?P<expr>.+?),?\s*$')


def _extract_let_steps(m_code: str) -> list[tuple[int, str, str]]:
    """Return ordered tuples of (line_index, step_name, expression)."""
    lines = [ln.rstrip() for ln in m_code.splitlines()]
    in_let = False
    out: list[tuple[int, str, str]] = []

    for idx, line in enumerate(lines):
        low = line.strip().lower()
        if low == "let":
            in_let = True
            continue
        if in_let and low.startswith("in "):
            break
        if not in_let:
            continue

        m = STEP_LINE_PATTERN.match(line)
        if not m:
            continue
        name = m.group("quoted_name") or m.group("name")
        expr = m.group("expr")
        out.append((idx, name, expr))

    return out


def parse_m_code(m_code: str) -> list[ParsedStep]:
    steps: list[ParsedStep] = []
    for _, step_name, expr in _extract_let_steps(m_code):
        for rule in OPERATION_RULES:
            if re.search(rule.pattern, expr):
                matched = re.search(rule.pattern, expr)
                source_pattern = matched.group(0) if matched else rule.pattern
                steps.append(
                    ParsedStep(
                        step_name=step_name,
                        operation=rule.operation,
                        source_pattern=source_pattern,
                        tableau_equivalent=rule.tableau_equivalent,
                        explanation=(
                            f"Step '{step_name}' performs '{rule.operation}'. "
                            f"In Tableau Prep, use: {rule.tableau_equivalent}."
                        ),
                    )
                )
                break

    return steps
