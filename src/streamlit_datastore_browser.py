import streamlit as st
import os
import json
from pathlib import Path

data_store_path = os.path.join("stores", "data_stores")

def list_data_store_files():
    data_stores = list(Path(data_store_path).glob("data_store_*.json"))
    return sorted(data_stores)

def load_data_store(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    st.set_page_config(page_title="Data Store Browser", layout="wide")
    st.title("Data Store Browser")
    st.markdown("Browse and inspect saved project data stores.")

    data_store_files = list_data_store_files()
    if not data_store_files:
        st.warning("No data store files found in stores/data_stores/.")
        return

    file_names = [f.name for f in data_store_files]
    selected_file = st.selectbox("Select a data store file:", file_names)
    file_path = os.path.join(data_store_path, selected_file)

    data = load_data_store(file_path)

    st.subheader(f"Contents of {selected_file}")
    st.json(data)

    # Optional: Add a search/filter feature
    st.markdown("---")
    st.subheader("Search in Data Store")
    search_term = st.text_input("Enter a key or value to search for (case-insensitive):")
    if search_term:
        search_term_lower = search_term.lower()
        results = []
        def search_dict(d, path=None):
            if path is None:
                path = []
            if isinstance(d, dict):
                for k, v in d.items():
                    if search_term_lower in str(k).lower() or search_term_lower in str(v).lower():
                        results.append((path + [k], v))
                    search_dict(v, path + [k])
            elif isinstance(d, list):
                for idx, item in enumerate(d):
                    search_dict(item, path + [str(idx)])
        search_dict(data)
        if results:
            st.write(f"Found {len(results)} matches:")
            for path, value in results:
                st.write(f"**{'/'.join(path)}**: {value}")
        else:
            st.info("No matches found.")

if __name__ == "__main__":
    main()
