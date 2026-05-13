from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)
_STEP_START_RE = re.compile(r'^(#?"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*=')


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


def _split_step_blocks(code: str) -> List[str]:
    """
    Split Power Query M into step blocks while preserving multiline expressions.
    A new block starts when a line begins with: StepName =
    """
    lines = _clean_lines(code)
    blocks: List[str] = []
    buffer: List[str] = []

    for line in lines:
        if _STEP_START_RE.match(line) and buffer:
            blocks.append(" ".join(buffer).strip().rstrip(","))
            buffer = []
        buffer.append(line)

    if buffer:
        blocks.append(" ".join(buffer).strip().rstrip(","))

    return blocks


def _extract_step_name(block: str) -> str:
    m = re.match(r'(?P<name>#?"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<expr>.+)', block, re.DOTALL)
    if not m:
        return "Step"
    name = m.group("name").strip()
    if name.startswith('#"') and name.endswith('"'):
        name = name[2:-1]
    return name


def _extract_expression(block: str) -> str:
    m = re.match(r'(?P<name>#?"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<expr>.+)', block, re.DOTALL)
    if not m:
        return block.strip()
    return re.sub(r"\s+", " ", m.group("expr")).strip()


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _friendly_type_name(raw_type: str) -> str:
    t = re.sub(r"\s+", " ", raw_type.strip().lower())

    mapping = {
        "int64.type": "Whole Number",
        "number.type": "Decimal Number",
        "type text": "Text",
        "text": "Text",
        "type date": "Date",
        "date.type": "Date",
        "type datetime": "Date & Time",
        "datetime.type": "Date & Time",
        "type logical": "True/False",
        "logical.type": "True/False",
        "type time": "Time",
        "time.type": "Time",
        "type duration": "Duration",
        "duration.type": "Duration",
    }

    if t in mapping:
        return mapping[t]

    cleaned = raw_type.replace(".Type", "").replace(".type", "").strip()
    cleaned = re.sub(r"^type\s+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned or raw_type


def _extract_quoted_strings(text: str) -> List[str]:
    return re.findall(r'"([^"]+)"', text)


def _parse_remove_columns(expr: str) -> List[str]:
    cols = _extract_quoted_strings(expr)
    return _dedupe_preserve_order(cols)


def _parse_type_conversions(expr: str) -> List[Tuple[str, str]]:
    """
    Example:
      Table.TransformColumnTypes(Source,{{"A", type date}, {"B", Int64.Type}})
    """
    pairs = re.findall(r'\{\s*"([^"]+)"\s*,\s*([^{}]+?)\s*\}', expr)
    return [(col.strip(), raw_type.strip()) for col, raw_type in pairs]


def _parse_rename_pairs(expr: str) -> List[Tuple[str, str]]:
    """
    Example:
      Table.RenameColumns(Source,{{"Old","New"}})
    """
    pairs = re.findall(r'\{\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\}', expr)
    return [(old.strip(), new.strip()) for old, new in pairs]


def _parse_add_column_name(expr: str) -> str | None:
    m = re.search(r'Table\.AddColumn\s*\(.*?,\s*"([^"]+)"\s*,', expr, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()

    quoted = _extract_quoted_strings(expr)
    return quoted[1].strip() if len(quoted) >= 2 else None


def _parse_group_keys(expr: str) -> List[str]:
    m = re.search(r'Table\.Group\s*\(.*?,\s*\{(.*?)\}\s*,', expr, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    keys = _extract_quoted_strings(m.group(1))
    return _dedupe_preserve_order(keys)


def _parse_pivot_info(expr: str) -> Dict[str, Any]:
    quoted = _extract_quoted_strings(expr)
    info: Dict[str, Any] = {"column": None, "values": []}

    if "Table.Pivot" in expr:
        if len(quoted) >= 2:
            info["column"] = quoted[1]
        if len(quoted) >= 3:
            info["values"] = quoted[2:]
    elif "Table.UnpivotOtherColumns" in expr:
        if len(quoted) >= 1:
            info["values"] = quoted
    elif "Table.Unpivot" in expr:
        if len(quoted) >= 2:
            info["column"] = quoted[1]
        if len(quoted) >= 3:
            info["values"] = quoted[2:]

    return info


def _summarize_operations(operations: List[Dict[str, str]]) -> str:
    if not operations:
        return (
            "No major Power Query transformations were detected. "
            "The script may be very short, heavily nested, or use patterns that are not yet recognized."
        )

    counts: Dict[str, int] = {}
    for op in operations:
        counts[op["type"]] = counts.get(op["type"], 0) + 1

    parts = [f"{count} {name.lower()}" for name, count in counts.items()]
    return f"Detected {len(operations)} transformation step(s): {', '.join(parts)}."


def _build_tableau_steps(operations: List[Dict[str, str]]) -> List[str]:
    if not operations:
        return [
            "1. Inspect the M script manually and identify each transformation step.",
            "2. Rebuild the flow in Tableau Prep using source, clean, join, pivot, and output steps as needed.",
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
        elif op["type"] == "Pivot":
            tableau_hint = "In Tableau Prep, use a Pivot step."
        elif op["type"] == "Unpivot":
            tableau_hint = "In Tableau Prep, use a Pivot step in reverse / reshape columns as rows."
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

    return notes or ["This script is a good candidate for a straightforward Tableau Prep recreation."]


def _detect_operations(code: str) -> List[Dict[str, str]]:
    blocks = _split_step_blocks(code)
    operations: List[Dict[str, str]] = []

    for block in blocks:
        expr = _extract_expression(block)
        step_name = _extract_step_name(block)
        expr_low = expr.lower()

        if "excel.workbook" in expr_low:
            operations.append(
                {
                    "step": step_name,
                    "type": "Source",
                    "description": "Connect to an Excel workbook source.",
                }
            )
            continue

        if "csv.document" in expr_low:
            operations.append(
                {
                    "step": step_name,
                    "type": "Source",
                    "description": "Connect to a CSV / flat file source.",
                }
            )
            continue

        if "sql.database" in expr_low:
            operations.append(
                {
                    "step": step_name,
                    "type": "Source",
                    "description": "Connect to a SQL database and read the source query/table.",
                }
            )
            continue

        if "table.removecolumns" in expr_low:
            removed_cols = _parse_remove_columns(expr)
            if removed_cols:
                desc = f"Remove column(s): {', '.join(removed_cols)}."
            else:
                desc = "Remove one or more columns."
            operations.append(
                {
                    "step": step_name,
                    "type": "Remove Columns",
                    "description": desc,
                }
            )
            continue

        if "table.selectrows" in expr_low:
            if "each true" in expr_low.replace(" ", ""):
                continue

            cond_match = re.search(r"each\s+(.+?)(?:\)\s*,?\s*$|\)\s*in\s*$)", expr, re.IGNORECASE)
            condition = cond_match.group(1).strip() if cond_match else "custom condition"
            operations.append(
                {
                    "step": step_name,
                    "type": "Filter",
                    "description": f"Filter rows using condition: {condition}.",
                }
            )
            continue

        if "table.transformcolumntypes" in expr_low:
            pairs = _parse_type_conversions(expr)
            if pairs:
                parts = []
                for col_name, raw_type in pairs:
                    friendly = _friendly_type_name(raw_type)
                    parts.append(f"{col_name} → {friendly}")
                desc = "Change data type: " + "; ".join(parts) + "."
            else:
                desc = "Change column data types."
            operations.append(
                {
                    "step": step_name,
                    "type": "Change Types",
                    "description": desc,
                }
            )
            continue

        if "table.renamecolumns" in expr_low:
            pairs = _parse_rename_pairs(expr)
            if pairs:
                desc = "Rename column(s): " + "; ".join(f"{old} → {new}" for old, new in pairs) + "."
            else:
                desc = "Rename columns."
            operations.append(
                {
                    "step": step_name,
                    "type": "Rename",
                    "description": desc,
                }
            )
            continue

        if "table.addcolumn" in expr_low:
            new_col = _parse_add_column_name(expr)
            if new_col:
                desc = f"Add calculated column: {new_col}."
            else:
                desc = "Add a calculated column."
            operations.append(
                {
                    "step": step_name,
                    "type": "Add Column",
                    "description": desc,
                }
            )
            continue

        if "table.group" in expr_low:
            keys = _parse_group_keys(expr)
            if keys:
                desc = "Group by: " + ", ".join(keys) + "."
            else:
                desc = "Group rows and aggregate data."
            operations.append(
                {
                    "step": step_name,
                    "type": "Group",
                    "description": desc,
                }
            )
            continue

        if "table.nestedjoin" in expr_low:
            tables = _extract_quoted_strings(expr)
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

        if "table.expandtablecolumn" in expr_low:
            cols = _extract_quoted_strings(expr)
            if len(cols) > 2:
                expanded = cols[2:]
                expanded_text = ", ".join(expanded)
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

        if "table.sort" in expr_low:
            operations.append(
                {
                    "step": step_name,
                    "type": "Sort",
                    "description": "Sort rows.",
                }
            )
            continue

        if "table.distinct" in expr_low:
            operations.append(
                {
                    "step": step_name,
                    "type": "Deduplicate",
                    "description": "Remove duplicate rows.",
                }
            )
            continue

        if "table.replacevalue" in expr_low:
            quoted = _extract_quoted_strings(expr)
            target_columns: List[str] = []
            for q in quoted:
                low = q.lower().strip()
                if low not in {"x", "y", "null", "replacer.replacetext", "replacer.replacevalue"}:
                    target_columns.append(q)

            target_columns = _dedupe_preserve_order(target_columns)
            if target_columns:
                cols = ", ".join(f"'{c}'" for c in target_columns)
                desc = f"Replace values in {cols}."
            else:
                desc = "Replace values in selected columns."

            operations.append(
                {
                    "step": step_name,
                    "type": "Replace Values",
                    "description": desc,
                }
            )
            continue

        if "table.unpivotothercolumns" in expr_low or "table.unpivot" in expr_low:
            info = _parse_pivot_info(expr)
            if info["values"]:
                desc = "Unpivot columns: " + ", ".join(info["values"]) + "."
            else:
                desc = "Unpivot columns into attribute/value rows."
            operations.append(
                {
                    "step": step_name,
                    "type": "Unpivot",
                    "description": desc,
                }
            )
            continue

        if "table.pivot" in expr_low:
            info = _parse_pivot_info(expr)
            if info["column"]:
                desc = f"Pivot using column: {info['column']}."
            else:
                desc = "Pivot data to reshape rows into columns."
            operations.append(
                {
                    "step": step_name,
                    "type": "Pivot",
                    "description": desc,
                }
            )
            continue

        if any(token in expr_low for token in ("text.", "date.", "number.", "list.", "record.", "table.")):
            operations.append(
                {
                    "step": step_name,
                    "type": "Custom",
                    "description": f"Custom Power Query transformation: {expr[:180]}",
                }
            )

    return operations


def convert_m_code(m_code: str) -> Dict[str, Any]:
    """
    Convert Power Query M code into a Tableau Prep migration guide.
    """
    code = m_code or ""
    operations = _detect_operations(code)

    return {
        "summary": _summarize_operations(operations),
        "tableau_steps": _build_tableau_steps(operations),
        "flow_diagram": _build_flow_diagram(operations),
        "migration_notes": _build_notes(operations, code),
        "parsed_steps": operations,
    }