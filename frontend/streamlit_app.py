# Optimized Final `frontend/streamlit_app.py`

Replace your entire existing `frontend/streamlit_app.py` with the code below.

```python
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

import streamlit as st

# Make sure repo root is importable when Streamlit runs from frontend/
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# -----------------------------
# Visual flow builder
# -----------------------------


def build_visual_flow_vertical(flow_text: str) -> str:
    """
    Render flow as stacked boxes with downward arrows.
    """

    nodes = [n.strip() for n in flow_text.split("->") if n.strip()]

    if not nodes:
        return "No flow detected."

    width = max(19, max(len(n) for n in nodes) + 4)

    border = "┌" + "─" * (width + 2) + "┐"
    divider = "└" + "─" * (width + 2) + "┘"
    indent = " " * ((width // 2) + 2)

    visual: List[str] = []

    for i, node in enumerate(nodes):

        visual.append(
            f"{border}\n"
            f"│ {node.center(width)} │\n"
            f"{divider}"
        )

        if i != len(nodes) - 1:
            visual.append(f"{indent}↓")

    return "\n".join(visual)



def build_visual_flow_horizontal(flow_text: str) -> str:
    """
    Render flow as a single left-to-right line.
    """

    nodes = [n.strip() for n in flow_text.split("->") if n.strip()]

    if not nodes:
        return "No flow detected."

    parts = []

    for i, node in enumerate(nodes):

        parts.append(f"[ {node} ]")

        if i != len(nodes) - 1:
            parts.append("→")

    return "  ".join(parts)


# -----------------------------
# Step formatting helper
# -----------------------------


def format_tableau_steps(steps: List[str]) -> str:
    """
    Improve readability and consistency for parser output.

    Handles:
    - long datatype conversion steps
    - leaked numbering
    - replacement wording cleanup
    - multiline formatting for better readability
    """

    formatted_steps = []

    for step in steps:

        if not isinstance(step, str):
            formatted_steps.append(str(step))
            continue

        clean_step = step.strip()

        # ---------------------------------
        # Improve ReplaceValue wording
        # ---------------------------------

        if "Replace IIL with value" in clean_step:
            clean_step = clean_step.replace(
                "Replace IIL with value",
                "Remove text 'IIL ' from"
            )

        if "Replace '' with value" in clean_step:
            clean_step = clean_step.replace(
                "Replace '' with value",
                "Replace blank value with"
            )

        # ---------------------------------
        # Format long datatype conversions
        # ---------------------------------

        if (
            "Change data type:" in clean_step
            and clean_step.count(";") >= 2
        ):

            guidance = ""
            step_number = ""

            # Extract step number like "6."
            if ". " in clean_step[:5]:
                step_number = clean_step.split(". ", 1)[0] + ". "

            if ". In Tableau Prep" in clean_step:

                split_parts = clean_step.split(
                    ". In Tableau Prep",
                    1
                )

                datatype_part = split_parts[0]

                guidance = (
                    "\n\nIn Tableau Prep"
                    + split_parts[1]
                )

            else:
                datatype_part = clean_step

            datatype_text = datatype_part.replace(
                step_number,
                ""
            ).replace(
                "Change data type:",
                ""
            ).strip()

            columns = [
                c.strip()
                for c in datatype_text.split(";")
                if c.strip()
            ]

            pretty_step = (
                f"{step_number}Change data types:\n\n"
            )

            for col in columns:

                clean_col = col

                # Remove leaked numbering like "6. "
                if ". " in clean_col[:5]:
                    clean_col = clean_col.split(". ", 1)[1]

                pretty_step += f"    • {clean_col}\n"

            pretty_step += guidance

            formatted_steps.append(pretty_step.strip())
            continue

        formatted_steps.append(clean_step)

    return "\n\n".join(formatted_steps)


# -----------------------------
# Page config
# -----------------------------

st.set_page_config(
    page_title="M → Tableau Prep Assistant",
    layout="wide"
)

st.title("Power Query M → Tableau Prep Migration Assistant")

st.caption(
    "Runs fully inside Streamlit. No separate backend is required."
)


# -----------------------------
# Converter loader
# -----------------------------


def _candidate_converter_functions(
    module: Any
) -> List[Callable[[str], Any]]:
    """
    Return likely converter functions from app.services.converter.
    """

    preferred_names = [
        "convert_m_code",
        "convert_m_to_tableau_prep",
        "convert_power_query_m",
        "convert",
        "generate_conversion",
        "process_m_code",
        "analyze_m_code",
    ]

    funcs: List[Callable[[str], Any]] = []

    for name in preferred_names:

        fn = getattr(module, name, None)

        if callable(fn):
            funcs.append(fn)

    if funcs:
        return funcs

    # Fallback search
    for name in dir(module):

        if name.startswith("_"):
            continue

        if any(
            token in name.lower()
            for token in (
                "convert",
                "transform",
                "analy",
                "process"
            )
        ):

            fn = getattr(module, name, None)

            if callable(fn):
                funcs.append(fn)

    return funcs


@st.cache_resource
def get_converter() -> Callable[[str], Any]:

    module = importlib.import_module(
        "app.services.converter"
    )

    funcs = _candidate_converter_functions(module)

    if not funcs:

        raise AttributeError(
            "No converter function found in "
            "app.services.converter."
        )

    return funcs[0]



def normalize_result(result: Any) -> Dict[str, Any]:
    """
    Normalize converter output into UI format.
    """

    if isinstance(result, dict):

        return {
            "summary": str(result.get("summary", "")),
            "tableau_steps": (
                result.get("tableau_steps", []) or []
            ),
            "flow_diagram": str(
                result.get("flow_diagram", "")
            ),
            "migration_notes": (
                result.get("migration_notes", []) or []
            ),
        }

    if isinstance(result, str):

        return {
            "summary": result,
            "tableau_steps": [],
            "flow_diagram": "",
            "migration_notes": [],
        }

    if isinstance(result, tuple):

        items = list(result)

        while len(items) < 4:
            items.append([])

        steps = (
            items[1]
            if isinstance(items[1], list)
            else (
                [str(items[1])]
                if items[1]
                else []
            )
        )

        notes = (
            items[3]
            if isinstance(items[3], list)
            else (
                [str(items[3])]
                if items[3]
                else []
            )
        )

        return {
            "summary": str(items[0]),
            "tableau_steps": steps,
            "flow_diagram": str(items[2]),
            "migration_notes": notes,
        }

    return {
        "summary": str(result),
        "tableau_steps": [],
        "flow_diagram": "",
        "migration_notes": [],
    }


# -----------------------------
# Session state
# -----------------------------

if "conversion_data" not in st.session_state:
    st.session_state.conversion_data = None

if "m_code" not in st.session_state:
    st.session_state.m_code = ""


# -----------------------------
# UI
# -----------------------------

st.caption(
    "Supports full Power Query M scripts "
    "or partial transformation snippets."
)

st.text_area(
    "Paste Power Query M code",
    key="m_code",
    height=320,
    placeholder=(
        "let\n"
        "    Source = ...\n"
        "in\n"
        "    Result\n\n"
        "(Partial M snippets also supported)"
    ),
)

col1, col2 = st.columns([1, 1])

with col1:

    convert_clicked = st.button(
        "Convert",
        use_container_width=True
    )

with col2:

    clear_clicked = st.button(
        "Clear & Convert New",
        use_container_width=True
    )


# -----------------------------
# Clear state
# -----------------------------

if clear_clicked:

    st.session_state.conversion_data = None

    if "m_code" in st.session_state:
        del st.session_state["m_code"]

    st.rerun()


# -----------------------------
# Conversion
# -----------------------------

if convert_clicked:

    if not st.session_state.m_code.strip():

        st.error("Please paste M code first.")

        st.session_state.conversion_data = None

    else:

        with st.spinner(
            "Analyzing and mapping transformations..."
        ):

            try:

                converter = get_converter()

                raw_result = converter(
                    st.session_state.m_code
                )

                st.session_state.conversion_data = (
                    normalize_result(raw_result)
                )

            except ModuleNotFoundError as exc:

                st.error(
                    "Could not import "
                    "app.services.converter."
                )

                st.exception(exc)

                st.session_state.conversion_data = None

            except AttributeError as exc:

                st.error(
                    "No suitable converter function found."
                )

                st.exception(exc)

                st.session_state.conversion_data = None

            except Exception as exc:

                st.error(f"Conversion failed: {exc}")

                st.exception(exc)

                st.session_state.conversion_data = None


# -----------------------------
# Results
# -----------------------------

if st.session_state.conversion_data is not None:

    data = st.session_state.conversion_data

    # 1) Summary
    st.subheader("1) Transformation Summary")

    if data["summary"]:
        st.write(data["summary"])

    else:
        st.info("No summary returned.")

    st.markdown("")

    # 2) Tableau Steps
    st.subheader("2) Tableau Prep Step-by-Step")

    step_count = len(data["tableau_steps"])

    st.caption(
        f"{step_count} transformation steps detected"
    )

    if data["tableau_steps"]:

        formatted_steps = format_tableau_steps(
            data["tableau_steps"]
        )

        with st.expander(
            "View Detailed Tableau Prep Steps",
            expanded=False
        ):

            st.code(formatted_steps, language="text")

            st.download_button(
                "Download Steps (.txt)",
                formatted_steps,
                file_name="tableau_steps.txt",
                mime="text/plain",
            )

            st.caption(
                "Tip: Use the copy icon in the top-right "
                "corner of the code block to copy steps."
            )

    else:
        st.info("No Tableau steps returned.")

    st.markdown("")

    # 3) Visual Flow
    st.subheader("3) Tableau Prep Style Flow")

    if data["flow_diagram"]:

        layout = st.radio(
            "Layout",
            ["Vertical", "Horizontal"],
            horizontal=True,
            label_visibility="collapsed",
        )

        with st.expander(
            "View Transformation Flow",
            expanded=True
        ):

            if layout == "Vertical":

                st.code(
                    build_visual_flow_vertical(
                        data["flow_diagram"]
                    ),
                    language="text"
                )

            else:

                st.code(
                    build_visual_flow_horizontal(
                        data["flow_diagram"]
                    ),
                    language="text"
                )

    else:
        st.info("No flow diagram returned.")

    st.markdown("")

    # 4) Migration Notes
    st.subheader("4) Migration Notes & Limitations")

    if data["migration_notes"]:

        with st.expander(
            "View Migration Notes",
            expanded=False
        ):

            for note in data["migration_notes"]:
                st.markdown(f"- {note}")

    else:
        st.info("No migration notes returned.")


# -----------------------------
# Footer
# -----------------------------

st.markdown("---")
st.caption("❤️ Developed by Shiv")
```
