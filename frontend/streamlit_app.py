import importlib
from typing import Any, Callable, Dict, List

import streamlit as st

st.set_page_config(page_title="M → Tableau Prep Assistant", layout="wide")
st.title("Power Query M → Tableau Prep Migration Assistant")


@st.cache_resource
def get_converter() -> Callable[[str], Any]:
    """
    Try common converter function names inside app.services.converter.
    Adjust the candidate list only if your converter uses a different name.
    """
    module = importlib.import_module("app.services.converter")

    candidate_names = [
        "convert_m_code",
        "convert",
        "generate_conversion",
        "process_m_code",
        "analyze_m_code",
        "convert_power_query_m",
        "convert_m_to_tableau_prep",
    ]

    for name in candidate_names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn

    raise AttributeError(
        "No supported converter function found in app.services.converter. "
        f"Tried: {', '.join(candidate_names)}"
    )


def normalize_result(result: Any) -> Dict[str, Any]:
    """
    Normalize different possible return shapes into the UI format.
    Expected final shape:
    {
        'summary': str,
        'tableau_steps': list[str],
        'flow_diagram': str,
        'migration_notes': list[str]
    }
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
        return {
            "summary": str(items[0]),
            "tableau_steps": items[1] if isinstance(items[1], list) else [str(items[1])] if items[1] else [],
            "flow_diagram": str(items[2]),
            "migration_notes": items[3] if isinstance(items[3], list) else [str(items[3])] if items[3] else [],
        }

    return {
        "summary": str(result),
        "tableau_steps": [],
        "flow_diagram": "",
        "migration_notes": [],
    }


m_code = st.text_area(
    "Paste Power Query M code",
    height=320,
    placeholder="let\n  Source = ...\nin\n  Result",
)

convert_clicked = st.button("Convert")

if convert_clicked:
    if not m_code.strip():
        st.error("Please paste M code first.")
    else:
        with st.spinner("Analyzing and mapping transformations..."):
            try:
                converter = get_converter()
                raw_result = converter(m_code)
                data = normalize_result(raw_result)

                st.subheader("1) Transformation Summary")
                if data["summary"]:
                    st.write(data["summary"])
                else:
                    st.info("No summary returned.")

                st.subheader("2) Tableau Prep Step-by-Step")
                if data["tableau_steps"]:
                    steps_text = "\n".join(
                        step if isinstance(step, str) else str(step)
                        for step in data["tableau_steps"]
                    )
                    st.code(steps_text, language="text")
                    st.download_button(
                        "Copy Steps (.txt)",
                        steps_text,
                        file_name="tableau_steps.txt",
                        mime="text/plain",
                    )
                else:
                    st.info("No Tableau steps returned.")

                st.subheader("3) Flow Representation")
                if data["flow_diagram"]:
                    st.code(data["flow_diagram"], language="text")
                else:
                    st.info("No flow diagram returned.")

                st.subheader("4) Migration Notes & Limitations")
                if data["migration_notes"]:
                    for note in data["migration_notes"]:
                        st.markdown(f"- {note}")
                else:
                    st.info("No migration notes returned.")

            except ModuleNotFoundError as exc:
                st.error(
                    "Could not import the converter module. "
                    "Make sure app/services/converter.py exists and the app folder is a Python package."
                )
                st.exception(exc)

            except AttributeError as exc:
                st.error(
                    "Converter function not found in app/services/converter.py. "
                    "Rename the function or add one of the supported names in the code."
                )
                st.exception(exc)

            except Exception as exc:
                st.error(f"Conversion failed: {exc}")
                st.exception(exc)