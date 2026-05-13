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

    Example:
        ┌───────────────────────┐
        │         Input         │
        └───────────────────────┘
                    ↓
        ┌───────────────────────┐
        │         Filter        │
        └───────────────────────┘
    """
    nodes = [n.strip() for n in flow_text.split("->") if n.strip()]
    if not nodes:
        return "No flow detected."

    width = max(19, max(len(n) for n in nodes) + 4)
    border  = "┌" + "─" * (width + 2) + "┐"
    divider = "└" + "─" * (width + 2) + "┘"
    indent  = " " * ((width // 2) + 2)

    visual: List[str] = []
    for i, node in enumerate(nodes):
        visual.append(f"{border}\n│ {node.center(width)} │\n{divider}")
        if i != len(nodes) - 1:
            visual.append(f"{indent}↓")

    return "\n".join(visual)


def build_visual_flow_horizontal(flow_text: str) -> str:
    """
    Render flow as a single left-to-right line.

    Example:
        [ Input ]  →  [ Filter ]  →  [ Change Types ]  →  [ Output ]
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
# Page config
# -----------------------------

st.set_page_config(page_title="M → Tableau Prep Assistant", layout="wide")
st.title("Power Query M → Tableau Prep Migration Assistant")
st.caption("Runs fully inside Streamlit. No separate backend is required.")


# -----------------------------
# Converter loader
# -----------------------------

def _candidate_converter_functions(module: Any) -> List[Callable[[str], Any]]:
    """
    Return likely converter functions from app.services.converter.
    Resilient to function renames.
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

    # Fallback: any public callable with a converter-like name
    for name in dir(module):
        if name.startswith("_"):
            continue
        if any(token in name.lower() for token in ("convert", "transform", "analy", "process")):
            fn = getattr(module, name, None)
            if callable(fn):
                funcs.append(fn)

    return funcs


@st.cache_resource
def get_converter() -> Callable[[str], Any]:
    module = importlib.import_module("app.services.converter")
    funcs = _candidate_converter_functions(module)

    if not funcs:
        raise AttributeError(
            "No converter function found in app.services.converter. "
            "Add a function such as convert_m_code(m_code) or rename your existing one "
            "to a supported name."
        )

    return funcs[0]


def normalize_result(result: Any) -> Dict[str, Any]:
    """
    Normalize converter output into the UI format.

    Expected keys:
      - summary: str
      - tableau_steps: list[str]
      - flow_diagram: str
      - migration_notes: list[str]
    """
    if isinstance(result, dict):
        return {
            "summary": str(result.get("summary", "")),
            "tableau_steps": result.get("tableau_steps", []) or [],
            "flow_diagram": str(result.get("flow_diagram", "")),
            "migration_notes": result.get("migration_notes", []) or [],
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
        steps = items[1] if isinstance(items[1], list) else ([str(items[1])] if items[1] else [])
        notes = items[3] if isinstance(items[3], list) else ([str(items[3])] if items[3] else [])
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
# UI
# -----------------------------

# Persist conversion result across re-runs (widget interactions re-run the script)
if "conversion_data" not in st.session_state:
    st.session_state.conversion_data = None

m_code = st.text_area(
    "Paste Power Query M code",
    height=320,
    placeholder="let\n  Source = ...\nin\n  Result",
)

convert_clicked = st.button("Convert")

if convert_clicked:
    if not m_code.strip():
        st.error("Please paste M code first.")
        st.session_state.conversion_data = None
    else:
        with st.spinner("Analyzing and mapping transformations..."):
            try:
                converter = get_converter()
                raw_result = converter(m_code)
                st.session_state.conversion_data = normalize_result(raw_result)
            except ModuleNotFoundError as exc:
                st.error(
                    "Could not import app.services.converter. "
                    "Check that app/__init__.py and app/services/__init__.py exist, "
                    "and that converter.py is inside app/services/."
                )
                st.exception(exc)
                st.session_state.conversion_data = None
            except AttributeError as exc:
                st.error(
                    "No suitable converter function was found inside app.services.converter."
                )
                st.exception(exc)
                st.session_state.conversion_data = None
            except Exception as exc:
                st.error(f"Conversion failed: {exc}")
                st.exception(exc)
                st.session_state.conversion_data = None

# Render results — runs on every re-run (including radio toggle clicks)
if st.session_state.conversion_data is not None:
    data = st.session_state.conversion_data

    # 1) Summary
    st.subheader("1) Transformation Summary")
    if data["summary"]:
        st.write(data["summary"])
    else:
        st.info("No summary returned.")

    # 2) Tableau Steps
    st.subheader("2) Tableau Prep Step-by-Step")
    if data["tableau_steps"]:
        steps_text = "\n".join(
            step if isinstance(step, str) else str(step)
            for step in data["tableau_steps"]
        )
        st.code(steps_text, language="text")
        st.download_button(
            "Download Steps (.txt)",
            steps_text,
            file_name="tableau_steps.txt",
            mime="text/plain",
        )
    else:
        st.info("No Tableau steps returned.")

    # 3) Visual Flow
    st.subheader("3) Tableau Prep Style Flow")
    if data["flow_diagram"]:
        layout = st.radio(
            "Layout",
            ["Vertical", "Horizontal"],
            horizontal=True,
            label_visibility="collapsed",
        )
        if layout == "Vertical":
            st.code(build_visual_flow_vertical(data["flow_diagram"]), language="text")
        else:
            st.code(build_visual_flow_horizontal(data["flow_diagram"]), language="text")
    else:
        st.info("No flow diagram returned.")

    # 4) Migration Notes
    st.subheader("4) Migration Notes & Limitations")
    if data["migration_notes"]:
        for note in data["migration_notes"]:
            st.markdown(f"- {note}")
    else:
        st.info("No migration notes returned.")

# -----------------------------
# Footer
# -----------------------------

st.markdown(
    """
    <div style='position: fixed; bottom: 10px; left: 15px; font-size: 14px; color: gray; z-index: 100;'>
        ❤️ Developed by Shiv
    </div>
    """,
    unsafe_allow_html=True,
)
