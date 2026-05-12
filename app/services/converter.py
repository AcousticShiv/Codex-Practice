from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


# -----------------------------
# Helpers
# -----------------------------

_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)

# Common Power Query functions we can recognize
_OPERATION_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bSql\.Database\s*\(", re.IGNORECASE), "Connect to a SQL database source"),
    (re.compile(r"\bTable\.SelectRows\s*\(", re.IGNORECASE), "Filter rows"),
    (re.compile(r"\bTable\.TransformColumnTypes\s*\(", re.IGNORECASE), "Change column data types"),
    (re.compile(r"\bTable\.ReplaceValue\s*\(", re.IGNORECASE), "Replace values"),
    (re.compile(r"\bTable\.TransformColumns\s*\(", re.IGNORECASE), "Transform column values"),
    (re.compile(r"\bTable\.NestedJoin\s*\(", re.IGNORECASE), "Join tables"),
    (re.compile(r"\bTable\.ExpandTableColumn\s*\(", re.IGNORECASE), "Expand joined table columns"),
    (re.compile(r"\bTable\.RenameColumns\s*\(", re.IGNORECASE), "Rename columns"),
    (re.compile(r"\bTable\.RemoveColumns\s*\(", re.IGNORECASE), "Remove columns"),
    (re.compile(r"\bTable\.AddColumn\s*\(", re.IGNORECASE), "Add calculated column"),
    (re.compile(r"\bTable\.Group\s*\(", re.IGNORECASE), "Group / aggregate rows"),
    (re.compile(r"\bTable\.Sort\s*\(", re.IGNORECASE), "Sort rows"),
    (re.compile(r"\bTable\.Distinct\s*\(", re.IGNORECASE), "Remove duplicate rows"),
]


def _strip_comments(code: str) -> str:
    return re.sub(_COMMENT_RE, "", code)


def _clean_lines(code: str) -> List[str]:
    cleaned: List[str] = []
    for raw in _strip_comments(code).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower() in {"let", "in"}:
            continue
        cleaned.append(line)
    return cleaned


def _extract_step_name(line: str) -> str:
    """
    Extracts the step variable name from lines like:
        #"Changed Type" = Table.TransformColumnTypes(...)
    """
    m = re.match(r'(?P<name>#?"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<expr>.+)', line)
    if not m:
        return "Step"

    name = m.group("name").strip()
    if name.startswith('#"') and name.endswith('"'):
        name = name[2:-1]
    return name


def _extract_expression(line: str) -> str:
    m = re.match(r'(?P<name>#?"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<expr>.+)', line)
    if not m:
        return line.strip()
    return m.group("expr").rstrip(",").strip()


def _extract_quoted_items(text: str) -> List[str]:
    return re.findall(r'"([^"]+)"', text)


def _format_columns_from_text(text: str) -> str:
    cols = []
    for item in _extract_quoted_items(text):
        # Filter out obvious type tokens / non-column tokens
        if item.lower() in {
            "type text",
            "text",
            "int64.type",
            "number.type",
            "date.type",
            "datetime.type",
            "logical.type",
            "null",
        }:
            continue
        cols.append(item)

    # de-duplicate while preserving order
    seen = set()
    unique = []
    for c in cols:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    if not unique:
        return "selected columns"

    if len(unique) == 1:
        return f"'{unique[0]}'"
    return ", ".join(f"'{c}'" for c in unique)


def _detect_operations(code: str) -> List[Dict[str, str]]:
    lines = _clean_lines(code)
    operations: List[Dict[str, str]] = []

    for line in lines:
        expr = _extract_expression(line)
        step_name = _extract_step_name(line)

        # Detect common patterns in the expression
        if "Sql.Database" in expr:
            operations.append(
                {
                    "step": step_name,
                    "type": "Source",
                    "description": "Connect to a SQL database and read the source query/table.",
                }
            )
            continue

        if "Table.SelectRows" in expr:
            if "each true" in expr.replace(" ", "").lower():
                # No-op filter; ignore as a business step
                continue

            cond_match = re.search(r"each\s+(.+?)(?:\)\s*,?\s*$|\)\s*in\s*$)", expr, re.IGNORECASE)
            condition = cond_match.group(1).strip() if cond_match else "custom condition"
            operations.append(
                {
                    "step": step_name,
                    "type": "Filter",
                    "description": f"Filter rows using condition: {condition}",
                }
            )
            continue

        if "Table.TransformColumnTypes" in expr:
            cols = _format_columns_from_text(expr)
            operations.append(
                {
                    "step": step_name,
                    "type": "Change Types",
                    "description": f"Change data types for {cols}.",
                }
            )
            continue

        if "Table.ReplaceValue" in expr:
            quoted = _extract_quoted_items(expr)
            target_columns = []
            # The last brace list often contains columns; the generic extraction above is good enough
            for q in quoted:
                if q.lower() not in {"x", "y", "null", "replacer.replacetext", "replacer.replacevalue"}:
                    target_columns.append(q)

            # Deduplicate
            deduped = []
            seen = set()
            for c in target_columns:
                if c not in seen:
                    seen.add(c)
                    deduped.append(c)

            cols = ", ".join(f"'{c}'" for c in deduped) if deduped else "selected columns"
            operations.append(
                {
                    "step": step_name,
                    "type": "Replace Values",
                    "description": f"Replace values in {cols}.",
                }
            )
            continue

        if "Table.TransformColumns" in expr and "Text.Proper" in expr:
            cols = _format_columns_from_text(expr)
            operations.append(
                {
                    "step": step_name,
                    "type": "Capitalize Text",
                    "description": f"Apply proper-case formatting to {cols}.",
                }
            )
            continue

        if "Table.NestedJoin" in expr:
            tables = _extract_quoted_items(expr)
            if len(tables) >= 2:
                left_table = tables[0]
                right_table = tables[1]
                description = f"Join '{left_table}' with lookup table '{right_table}'."
            else:
                description = "Join tables using a merge operation."
            operations.append(
                {
                    "step": step_name,
                    "type": "Join",
                    "description": description,
                }
            )
            continue

        if "Table.ExpandTableColumn" in expr:
            cols = _extract_quoted_items(expr)
            if cols:
                # First two are usually source table + nested table name; remaining are expanded columns
                expanded = cols[2:] if len(cols) > 2 else cols
                expanded_text = ", ".join(f"'{c}'" for c in expanded) if expanded else "expanded fields"
            else:
                expanded_text = "expanded fields"
            operations.append(
                {
                    "step": step_name,
                    "type": "Expand",
                    "description": f"Expand joined table columns: {expanded_text}.",
                }
            )
            continue

        if "Table.RenameColumns" in expr:
            operations.append(
                {
                    "step": step_name,
                    "type": "Rename",
                    "description": "Rename columns.",
                }
            )
            continue

        if "Table.RemoveColumns" in expr:
            operations.append(
                {
                    "step": step_name,
                    "type": "Remove Columns",
                    "description": "Remove one or more columns.",
                }
            )
            continue

        if "Table.AddColumn" in expr:
            operations.append(
                {
                    "step": step_name,
                    "type": "Add Column",
                    "description": "Add a calculated column.",
                }
            )
            continue

        if "Table.Group" in expr:
            operations.append(
                {
                    "step": step_name,
                    "type": "Group",
                    "description": "Group rows and aggregate data.",
                }
            )
            continue

        if "Table.Sort" in expr:
            operations.append(
                {
                    "step": step_name,
                    "type": "Sort",
                    "description": "Sort rows.",
                }
            )
            continue

        if "Table.Distinct" in expr:
            operations.append(
                {
                    "step": step_name,
                    "type": "Deduplicate",
                    "description": "Remove duplicate rows.",
                }
            )
            continue

        # Ignore boring plumbing steps like previous step references
        if re.fullmatch(r'#"[^"]+"', step_name) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", step_name):
            # Keep unrecognized steps only if they look useful
            if any(token in expr for token in ("Text.", "Date.", "Number.", "List.", "Record.", "Table.")):
                operations.append(
                    {
                        "step": step_name,
                        "type": "Custom",
                        "description": f"Custom Power Query transformation: {expr[:180]}",
                    }
                )

    return operations


def _build_summary(operations: List[Dict[str, str]]) -> str:
    if not operations:
        return (
            "No major Power Query transformations were detected. "
            "The script may be very short, heavily nested, or use patterns that are not yet recognized."
        )

    op_types = [op["type"] for op in operations]
    counts: Dict[str, int] = {}
    for t in op_types:
        counts[t] = counts.get(t, 0) + 1

    parts = [f"{count} {name.lower()}" for name, count in counts.items()]
    major = ", ".join(parts)

    return (
        f"Detected {len(operations)} transformation step(s): {major}. "
        "The script appears to load data, filter rows, change types, and apply lookup / text-cleaning steps."
    )


def _build_tableau_steps(operations: List[Dict[str, str]]) -> List[str]:
    if not operations:
        return [
            "1. Inspect the M script manually and identify each transformation step.",
            "2. Rebuild the flow in Tableau Prep using source, clean, join, and output steps as needed.",
        ]

    steps: List[str] = []
    for i, op in enumerate(operations, start=1):
        desc = op["description"]
        tableau_hint = ""

        if op["type"] == "Source":
            tableau_hint = "In Tableau Prep, use an Input step."
        elif op["type"] == "Filter":
            tableau_hint = "In Tableau Prep, use a Clean step and apply filters."
        elif op["type"] == "Change Types":
            tableau_hint = "In Tableau Prep, use a Clean step and set field data types."
        elif op["type"] == "Replace Values":
            tableau_hint = "In Tableau Prep, use a Clean step and replace values."
        elif op["type"] == "Capitalize Text":
            tableau_hint = "In Tableau Prep, use a Clean step with calculated field or formatting."
        elif op["type"] == "Join":
            tableau_hint = "In Tableau Prep, use a Join step."
        elif op["type"] == "Expand":
            tableau_hint = "In Tableau Prep, expand fields from the joined table."
        elif op["type"] == "Rename":
            tableau_hint = "In Tableau Prep, rename the fields in a Clean step."
        elif op["type"] == "Remove Columns":
            tableau_hint = "In Tableau Prep, keep only required fields or remove columns in a Clean step."
        elif op["type"] == "Add Column":
            tableau_hint = "In Tableau Prep, create a calculated field."
        elif op["type"] == "Group":
            tableau_hint = "In Tableau Prep, use a Group and Aggregate step."
        elif op["type"] == "Sort":
            tableau_hint = "In Tableau Prep, sort rows in a Clean step."
        elif op["type"] == "Deduplicate":
            tableau_hint = "In Tableau Prep, use a Clean step to remove duplicates."
        else:
            tableau_hint = "Map this step manually in Tableau Prep."

        steps.append(f"{i}. {desc} {tableau_hint}".strip())

    return steps


def _build_flow_diagram(operations: List[Dict[str, str]]) -> str:
    if not operations:
        return "Input -> Review manually -> Tableau Prep flow"

    nodes = ["Input"]
    for op in operations:
        label = op["type"]
        if label == "Custom":
            label = "Custom Step"
        nodes.append(label)
    nodes.append("Output")

    # Keep consecutive duplicates out of the diagram
    compact: List[str] = []
    for node in nodes:
        if not compact or compact[-1] != node:
            compact.append(node)

    return " -> ".join(compact)


def _build_notes(operations: List[Dict[str, str]], code: str) -> List[str]:
    notes: List[str] = []

    if not operations:
        notes.append("No standard transformations were detected automatically.")
        notes.append("Review the M script manually for custom logic, nested expressions, or dynamic functions.")
        return notes

    custom_steps = [op for op in operations if op["type"] == "Custom"]
    if custom_steps:
        notes.append("Some steps look custom or complex and may need manual conversion in Tableau Prep.")

    if "Table.Buffer" in code:
        notes.append("Table.Buffer is not directly equivalent in Tableau Prep and may require a performance review.")

    if "List.Generate" in code or "List.Accumulate" in code:
        notes.append("List-based iterative logic usually needs manual redesign in Tableau Prep.")

    if "Record." in code:
        notes.append("Record-based transformations often need manual interpretation when migrating to Tableau Prep.")

    if "Web." in code or "OData." in code:
        notes.append("Data-source-specific connectors may need a separate Tableau Prep input configuration.")

    if not notes:
        notes.append("This script is a good candidate for a straightforward Tableau Prep recreation.")

    return notes


# -----------------------------
# Public API
# -----------------------------

def convert_m_code(m_code: str) -> Dict[str, Any]:
    """
    Convert Power Query M code into a Tableau Prep migration guide.

    Returns a dictionary with:
      - summary
      - tableau_steps
      - flow_diagram
      - migration_notes
    """
    code = m_code or ""
    operations = _detect_operations(code)

    result = {
        "summary": _build_summary(operations),
        "tableau_steps": _build_tableau_steps(operations),
        "flow_diagram": _build_flow_diagram(operations),
        "migration_notes": _build_notes(operations, code),
    }
    return result


# Backward-compatible aliases for the Streamlit app's function lookup
convert = convert_m_code
generate_conversion = convert_m_code
process_m_code = convert_m_code
analyze_m_code = convert_m_code
convert_power_query_m = convert_m_code
convert_m_to_tableau_prep = convert_m_code