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

def all_elements_filled(template_content):
    # Returns True if all elements in the template have at least one artifact (non-empty list or non-empty value)
    for element_content in template_content.values():
        if isinstance(element_content, list):
            if not element_content:
                return False
        elif not element_content:
            return False
    return True

def main():
    st.title(":open_file_folder: Data Store Browser")
    st.markdown("Browse and inspect saved project data stores in a hierarchical (template/element) view.")

    data_store_files = list_data_store_files()
    if not data_store_files:
        st.warning("No data store files found in stores/data_stores/.")
        return

    file_names = [f.name for f in data_store_files]
    # Set default selection to currently open project (from session_state['project_name'])
    project_name = st.session_state.get('project_name', 'default')
    default_file = f"data_store_{project_name}.json"
    default_index = file_names.index(default_file) if default_file in file_names else 0
    selected_file = st.selectbox("Select a data store file:", file_names, index=default_index)
    file_path = os.path.join(DATA_STORE_PATH, selected_file)

    data = load_data_store(file_path)

    st.markdown(f"## Project: `{selected_file.replace('data_store_', '').replace('.json', '')}`")
    if not data:
        st.info("This data store is empty.")
        return

    # --- Template quick-jump selectbox ---
    template_names = list(data.keys())
    selected_template = st.selectbox(
        "Jump to template:", template_names, key="template_jump_select"
    )

    # Show templates as expandable folders with color indicators in the expander title
    for template_name, template_content in data.items():
        filled = all_elements_filled(template_content)
        dot = "🟢" if filled else "🟠"  # green dot if filled, orange dot if not
        expander_label = f"{dot} {template_name}"
        expander_cols = st.columns([8, 1])
        with expander_cols[0]:
            with st.expander(label=expander_label, expanded=(template_name == selected_template)):
                show_template_content(template_name, template_content)
        with expander_cols[1]:
            if st.button("Go", key=f"jump_{template_name}"):
                st.session_state['selected_template_name'] = template_name
                st.session_state['current_view'] = 'detail'
                st.rerun()

    # --- Show full data store content (content only, easy to copy) in a single container ---
    with st.container():
        st.markdown("---")
        st.subheader(":page_facing_up: Full Data Store Content (Content Only)")
        # Load elements config for names/descriptions (not used for output, but could be for future features)
        elements_config_path = os.path.join("module_files", "elements_config.json")
        with open(elements_config_path, "r", encoding="utf-8") as f:
            elements_config = json.load(f)
        # Collect all content as plain text (no keys, just values)
        content_lines = []
        for template_content in data.values():
            for element_content in template_content.values():
                if isinstance(element_content, list):
                    for artifact in element_content:
                        content_lines.append(str(artifact))
                elif element_content:
                    content_lines.append(str(element_content))
        content_text = "\n".join(content_lines)
        if not content_text.strip():
            content_text = "[No content available in this data store.]"
            st.info("No content found to display. The data store may be empty or all elements are blank.")
        # Show in a Streamlit text_area for easy copy/paste
        st.text_area(
            label="Full Content (copy/paste)",
            value=content_text,
            height=300,
            key="full_content_reader"
        )
        # Optionally, add a download button for convenience
        st.download_button(
            label="Download Content as .txt",
            data=content_text,
            file_name=f"{selected_file.replace('.json', '')}_content.txt",
            mime="text/plain"
        )

if __name__ == "__main__":
    main()
