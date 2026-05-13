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
    data = st.session_state.conversion_data