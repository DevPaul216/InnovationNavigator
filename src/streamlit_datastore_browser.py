import streamlit as st
import os
import json
from pathlib import Path

# Path to the data store directory
DATA_STORE_PATH = os.path.join("stores", "data_stores")

def list_data_store_files():
    data_stores = list(Path(DATA_STORE_PATH).glob("data_store_*.json"))
    return sorted(data_stores)

def load_data_store(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def show_element_content(element_name, element_content):
    st.markdown(f"#### Element: `{element_name}`")
    if isinstance(element_content, list):
        if not element_content:
            st.info("No artifacts assigned.")
        else:
            for i, artifact in enumerate(element_content):
                st.markdown(f"- {artifact}")
    else:
        st.write(element_content)

def show_template_content(template_name, template_content):
    st.markdown(f"### Template: `{template_name}`")
    if not template_content:
        st.info("No elements in this template.")
        return
    for element_name, element_content in template_content.items():
        show_element_content(element_name, element_content)

def main():
    st.title(":open_file_folder: Data Store Browser")
    st.markdown("Browse and inspect saved project data stores in a hierarchical (template/element) view.")

    data_store_files = list_data_store_files()
    if not data_store_files:
        st.warning("No data store files found in stores/data_stores/.")
        return

    file_names = [f.name for f in data_store_files]
    selected_file = st.selectbox("Select a data store file:", file_names)
    file_path = os.path.join(DATA_STORE_PATH, selected_file)

    data = load_data_store(file_path)

    st.markdown(f"## Project: `{selected_file.replace('data_store_', '').replace('.json', '')}`")
    if not data:
        st.info("This data store is empty.")
        return

    # Show templates as expandable folders
    for template_name, template_content in data.items():
        with st.expander(f"Template: {template_name}", expanded=False):
            show_template_content(template_name, template_content)

if __name__ == "__main__":
    main()
