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
    selected_file = st.selectbox("Select a data store file:", file_names)
    file_path = os.path.join(DATA_STORE_PATH, selected_file)

    data = load_data_store(file_path)

    st.markdown(f"## Project: `{selected_file.replace('data_store_', '').replace('.json', '')}`")
    if not data:
        st.info("This data store is empty.")
        return

    # Show templates as expandable folders with color indicators in the expander title
    for template_name, template_content in data.items():
        filled = all_elements_filled(template_content)
        dot = "🟢" if filled else "🟠"  # green dot if filled, orange dot if not
        expander_label = f"{dot} {template_name}"
        with st.expander(label=expander_label, expanded=False):
            show_template_content(template_name, template_content)

    # --- Show full data store content with names and descriptions ---
    st.markdown("---")
    st.subheader(":page_facing_up: Full Data Store Content (with Names & Descriptions)")
    # Load elements config for names/descriptions
    elements_config_path = os.path.join("module_files", "elements_config.json")
    with open(elements_config_path, "r", encoding="utf-8") as f:
        elements_config = json.load(f)
    # Pretty print with names/descriptions
    for template_name, template_content in data.items():
        st.markdown(f"### Template: `{template_name}`")
        for element_name, element_content in template_content.items():
            display_name = elements_config.get(element_name, {}).get("display_name", element_name)
            description = elements_config.get(element_name, {}).get("description", "")
            st.markdown(f"**Element:** `{element_name}` | **Name:** {display_name}")
            if description:
                st.markdown(f"_Description:_ {description}")
            if isinstance(element_content, list):
                if not element_content:
                    st.info("No artifacts assigned.")
                else:
                    for i, artifact in enumerate(element_content):
                        st.markdown(f"- {artifact}")
            else:
                st.write(element_content)

    # --- Show full data store content (content only, easy to copy) ---
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
    # Show in a Streamlit text area for easy copy/paste
    st.container().text_area(
        label="All Content (copy/paste for transfer)",
        value=content_text,
        height=300,
        label_visibility="visible"
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
