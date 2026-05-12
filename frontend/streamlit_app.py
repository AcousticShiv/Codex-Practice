import streamlit as st
import requests

st.set_page_config(page_title="M → Tableau Prep Assistant", layout="wide")
st.title("Power Query M → Tableau Prep Migration Assistant")

api_url = st.sidebar.text_input("Backend URL", value="http://localhost:8000/api/v1/convert")

m_code = st.text_area("Paste Power Query M code", height=320, placeholder="let\n  Source = ...\nin\n  Result")

if st.button("Convert"):
    if not m_code.strip():
        st.error("Please paste M code first.")
    else:
        with st.spinner("Analyzing and mapping transformations..."):
            try:
                resp = requests.post(api_url, json={"m_code": m_code}, timeout=60)
                resp.raise_for_status()
                data = resp.json()

                st.subheader("1) Transformation Summary")
                st.write(data["summary"])

                st.subheader("2) Tableau Prep Step-by-Step")
                st.code("\n".join(data["tableau_steps"]), language="text")
                st.download_button("Copy Steps (.txt)", "\n".join(data["tableau_steps"]), file_name="tableau_steps.txt")

                st.subheader("3) Flow Representation")
                st.code(data["flow_diagram"], language="text")

                st.subheader("4) Migration Notes & Limitations")
                for note in data["migration_notes"]:
                    st.markdown(f"- {note}")

            except Exception as exc:
                st.error(f"Conversion failed: {exc}")
