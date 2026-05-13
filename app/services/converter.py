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


def _get_call_args(expr: str, func_name: str) -> List[str]:
    """
    Return top-level arguments for a function call like Table.X(...).
    Works reasonably well for multiline M expressions.
    """
    m = re.search(rf"{re.escape(func_name)}\s*\((.*)\)\s*$", expr, re.IGNORECASE | re.DOTALL)
    if not m:
        return []

    inner = m.group(1)
    args: List[str] = []
    buf: List[str] = []

    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    in_string = False

    i = 0
    while i < len(inner):
        ch = inner[i]
        nxt = inner[i + 1] if i + 1 < len(inner) else ""

        if ch == '"':
            if in_string and nxt == '"':
                buf.append(ch)
                buf.append(nxt)
                i += 2
                continue
            in_string = not in_string
            buf.append(ch)
            i += 1
            continue

        if not in_string:
            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren = max(0, depth_paren - 1)
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                depth_brace = max(0, depth_brace - 1)
            elif ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket = max(0, depth_bracket - 1)
            elif ch == "," and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
                arg = "".join(buf).strip()
                if arg:
                    args.append(arg)
                buf = []
                i += 1
                continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        args.append(tail)

    return args


def _normalize_ref(text: str) -> str:
    text = text.strip()

    quoted = re.findall(r'"([^"]+)"', text)
    if quoted:
        return quoted[-1].strip()

    if text.startswith('#"') and text.endswith('"'):
        return text[2:-1].strip()

    return text.strip()


def _extract_quoted_strings(text: str) -> List[str]:
    return re.findall(r'"([^"]+)"', text)


def _dedupe_nonempty(items: List[str]) -> List[str]:
    return _dedupe_preserve_order([item for item in items if item and item.strip()])


def _parse_remove_columns(expr: str) -> List[str]:
    args = _get_call_args(expr, "Table.RemoveColumns")
    if len(args) >= 2:
        cols = _extract_quoted_strings(args[1])
        return _dedupe_nonempty(cols)

    cols = _extract_quoted_strings(expr)
    return _dedupe_nonempty(cols)


def _parse_type_conversions(expr: str) -> List[Tuple[str, str]]:
    pairs = re.findall(r'\{\s*"([^"]+)"\s*,\s*([^{}]+?)\s*\}', expr)
    return [(col.strip(), raw_type.strip()) for col, raw_type in pairs]


def _parse_rename_pairs(expr: str) -> List[Tuple[str, str]]:
    args = _get_call_args(expr, "Table.RenameColumns")
    if len(args) >= 2:
        pairs = re.findall(r'\{\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\}', args[1])
        return [(old.strip(), new.strip()) for old, new in pairs]

    pairs = re.findall(r'\{\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\}', expr)
    return [(old.strip(), new.strip()) for old, new in pairs]


def _parse_transformcolumns_proper_fields(expr: str) -> List[str]:
    args = _get_call_args(expr, "Table.TransformColumns")
    target_expr = args[1] if len(args) >= 2 else expr
    fields = re.findall(r'\{\s*"([^"]+)"\s*,\s*Text\.Proper\b', target_expr, re.IGNORECASE)
    return _dedupe_nonempty(fields)


def _parse_add_column_name(expr: str) -> str | None:
    args = _get_call_args(expr, "Table.AddColumn")
    if len(args) >= 2:
        name = _normalize_ref(args[1])
        return name or None

    m = re.search(r'Table\.AddColumn\s*\(.*?,\s*"([^"]+)"\s*,', expr, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


def _parse_group_keys(expr: str) -> List[str]:
    args = _get_call_args(expr, "Table.Group")
    if len(args) >= 2:
        keys = _extract_quoted_strings(args[1])
        return _dedupe_nonempty(keys)
    return []


def _parse_nested_join(expr: str) -> Dict[str, Any]:
    args = _get_call_args(expr, "Table.NestedJoin")
    info: Dict[str, Any] = {
        "left_table": "",
        "right_table": "",
        "left_keys": [],
        "right_keys": [],
        "nested_name": "",
    }

    if len(args) >= 5:
        info["left_table"] = _normalize_ref(args[0])
        info["left_keys"] = _extract_quoted_strings(args[1])
        info["right_table"] = _normalize_ref(args[2])
        info["right_keys"] = _extract_quoted_strings(args[3])
        info["nested_name"] = _normalize_ref(args[4])
        return info

    quoted = _extract_quoted_strings(expr)
    if quoted:
        info["nested_name"] = quoted[-1]
    return info


def _parse_expand_table_column(expr: str) -> Dict[str, Any]:
    args = _get_call_args(expr, "Table.ExpandTableColumn")
    info: Dict[str, Any] = {
        "source_table": "",
        "nested_column": "",
        "expanded_cols": [],
        "new_names": [],
    }

    if len(args) >= 4:
        info["source_table"] = _normalize_ref(args[0])
        info["nested_column"] = _normalize_ref(args[1])
        info["expanded_cols"] = _extract_quoted_strings(args[2])
        info["new_names"] = _extract_quoted_strings(args[3])
        return info

    quoted = _extract_quoted_strings(expr)
    if quoted:
        info["nested_column"] = quoted[0]
    return info


def _parse_replace_value_info(expr: str) -> Dict[str, Any]:
    """
    Example:
      Table.ReplaceValue(#"Changed Type1","X","1",Replacer.ReplaceText,{"Order_Block", ...})
    """
    args = _get_call_args(expr, "Table.ReplaceValue")
    info: Dict[str, Any] = {
        "old_value": "",
        "new_value": "",
        "columns": [],
        "replacement_kind": "",
    }

    if len(args) >= 5:
        info["old_value"] = _normalize_ref(args[1])
        info["new_value"] = _normalize_ref(args[2])
        info["replacement_kind"] = _normalize_ref(args[3])
        info["columns"] = _extract_quoted_strings(args[4])
        return info

    # Fallback: use first two quoted values as old/new, last brace list as columns
    quoted = _extract_quoted_strings(expr)
    if quoted:
        if len(quoted) >= 1:
            info["old_value"] = quoted[0]
        if len(quoted) >= 2:
            info["new_value"] = quoted[1]

    start = expr.rfind("{")
    end = expr.rfind("}")
    if start != -1 and end != -1 and end > start:
        info["columns"] = _extract_quoted_strings(expr[start : end + 1])

    return info


def _parse_unpivot_info(expr: str) -> Dict[str, Any]:
    args = _get_call_args(expr, "Table.UnpivotOtherColumns")
    if len(args) >= 2:
        kept = _extract_quoted_strings(args[1])
        return {"mode": "other_columns", "kept_columns": kept}

    args = _get_call_args(expr, "Table.Unpivot")
    if len(args) >= 2:
        cols = _extract_quoted_strings(args[1])
        return {"mode": "columns", "cols": cols}

    return {"mode": "unknown"}


def _parse_pivot_info(expr: str) -> Dict[str, Any]:
    args = _get_call_args(expr, "Table.Pivot")
    if len(args) >= 2:
        pivot_values = _extract_quoted_strings(args[1])
        pivot_col = _normalize_ref(args[2]) if len(args) >= 3 else ""
        return {"pivot_values": pivot_values, "pivot_col": pivot_col}

    return {"pivot_values": [], "pivot_col": ""}


def _build_summary(operations: List[Dict[str, str]]) -> str:
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
            tableau_hint = "In Tableau Prep, reshape columns into rows with a Pivot-style transformation."
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
            desc = f"Remove column(s): {', '.join(removed_cols)}." if removed_cols else "Remove one or more columns."
            operations.append(
                {
                    "step": step_name,
                    "type": "Remove Columns",
                    "description": desc,
                }
            )
            continue

        if "table.selectrows" in expr_low:
            if re.search(r"\beach\s+true\b", expr_low, re.IGNORECASE):
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
            desc = "Rename column(s): " + "; ".join(f"{old} → {new}" for old, new in pairs) + "." if pairs else "Rename columns."
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
            desc = f"Add calculated column: {new_col}." if new_col else "Add a calculated column."
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
            desc = "Group by: " + ", ".join(keys) + "." if keys else "Group rows and aggregate data."
            operations.append(
                {
                    "step": step_name,
                    "type": "Group",
                    "description": desc,
                }
            )
            continue

        if "table.nestedjoin" in expr_low:
            info = _parse_nested_join(expr)
            left_table = str(info.get("left_table", "")).strip()
            right_table = str(info.get("right_table", "")).strip()
            left_keys = info.get("left_keys", []) or []
            right_keys = info.get("right_keys", []) or []

            if left_table and right_table and left_keys and right_keys:
                desc = (
                    f"Join '{left_table}' on {', '.join(left_keys)} "
                    f"with '{right_table}' on {', '.join(right_keys)}."
                )
            elif right_table:
                desc = f"Join with lookup table '{right_table}'."
            else:
                desc = "Join tables using a merge operation."

            operations.append(
                {
                    "step": step_name,
                    "type": "Join",
                    "description": desc,
                }
            )
            continue

        if "table.expandtablecolumn" in expr_low:
            info = _parse_expand_table_column(expr)
            nested_column = str(info.get("nested_column", "")).strip()
            expanded_cols = info.get("expanded_cols", []) or []
            new_names = info.get("new_names", []) or []

            if nested_column and expanded_cols:
                if new_names and len(new_names) == len(expanded_cols):
                    pairs = ", ".join(f"{src} → {dst}" for src, dst in zip(expanded_cols, new_names))
                    desc = f"Expand '{nested_column}' to: {pairs}."
                else:
                    desc = f"Expand '{nested_column}' to fields: {', '.join(expanded_cols)}."
            else:
                desc = "Expand joined table columns."

            operations.append(
                {
                    "step": step_name,
                    "type": "Expand",
                    "description": desc,
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
            info = _parse_replace_value_info(expr)
            columns = info.get("columns", []) or []
            old_value = str(info.get("old_value", "")).strip()
            new_value = str(info.get("new_value", "")).strip()

            if columns:
                if old_value or new_value:
                    desc = f"Replace {old_value or 'value'} with {new_value or 'value'} in columns: {', '.join(columns)}."
                else:
                    desc = f"Replace values in columns: {', '.join(columns)}."
            else:
                if old_value or new_value:
                    desc = f"Replace {old_value or 'value'} with {new_value or 'value'}."
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

        if "table.transformcolumns" in expr_low and "text.proper" in expr_low:
            fields = _parse_transformcolumns_proper_fields(expr)
            desc = f"Apply proper-case formatting to {', '.join(fields)}." if fields else "Apply proper-case formatting to selected text columns."
            operations.append(
                {
                    "step": step_name,
                    "type": "Capitalize Text",
                    "description": desc,
                }
            )
            continue

        if "table.unpivotothercolumns" in expr_low:
            info = _parse_unpivot_info(expr)
            kept = info.get("kept_columns", []) or []
            desc = f"Unpivot all other columns, keeping {', '.join(kept)}." if kept else "Unpivot other columns into attribute/value rows."
            operations.append(
                {
                    "step": step_name,
                    "type": "Unpivot",
                    "description": desc,
                }
            )
            continue

        if "table.unpivot" in expr_low:
            info = _parse_unpivot_info(expr)
            cols = info.get("cols", []) or []
            desc = f"Unpivot columns: {', '.join(cols)}." if cols else "Unpivot columns into attribute/value rows."
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
            pivot_values = info.get("pivot_values", []) or []
            pivot_col = str(info.get("pivot_col", "")).strip()

            if pivot_col:
                desc = f"Pivot using column '{pivot_col}'."
            elif pivot_values:
                desc = f"Pivot values: {', '.join(pivot_values)}."
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
        "summary": _build_summary(operations),
        "tableau_steps": _build_tableau_steps(operations),
        "flow_diagram": _build_flow_diagram(operations),
        "migration_notes": _build_notes(operations, code),
        "parsed_steps": operations,
    }


convert = convert_m_code
generate_conversion = convert_m_code
process_m_code = convert_m_code
analyze_m_code = convert_m_code
convert_power_query_m = convert_m_code
convert_m_to_tableau_prep = convert_m_code