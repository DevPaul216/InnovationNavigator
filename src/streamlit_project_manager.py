import streamlit as st
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

data_store_path = os.path.join("stores", "data_stores")

def project_manager_view(current_project_name, on_project_switch=None):
    data_stores_paths = Path(data_store_path).glob("data_store_*.json")
    core_names = [path.stem for path in data_stores_paths]
    project_names = [str(name).split('data_store_')[1] for name in core_names]
    add_empty_lines(3)
    st.subheader("Add new Innovation Project", help="Create a new project to start working on it. You can also import existing projects.")
    new_project_name = st.text_input(label="Name of new Innovation Project").strip()
    if st.button("Create and open new Innovation Project", disabled=new_project_name == ""):
        if new_project_name not in project_names:
            # Save the current data store just to be sure
            if on_project_switch:
                on_project_switch()
            st.session_state['project_name'] = new_project_name
            # Create new empty data store
            st.session_state['data_store'] = {}
            # Save new data store
            full_path = os.path.join(data_store_path, f"data_store_{new_project_name}.json")
            with open(full_path, "w", encoding="utf-8") as file:
                file.write("{}")
            st.success("Project created")
            st.session_state['sidebar_state'] = "expanded"
            st.session_state['update_graph'] = True
            st.session_state['current_view'] = "chart"  # Transition to the overview screen
            time.sleep(1.0)
            st.rerun()
        else:
            st.warning("A project with this name is already there")
    st.divider()
    st.subheader("Switch/Delete Project", help="Switch to another project or delete the current one.")
    selected_project_name = st.selectbox("Switch to another project:", options=project_names,
                                         index=project_names.index(current_project_name) if current_project_name in project_names else 0)
    if selected_project_name != current_project_name:
        st.session_state['project_name'] = selected_project_name
        st.session_state['sidebar_state'] = "expanded"
        if on_project_switch:
            on_project_switch()
        st.rerun()
    if selected_project_name != "default":
        st.write("")
        with st.expander("Delete Project"):
            if st.button("Delete"):
                full_path = os.path.join(data_store_path, f"data_store_{selected_project_name}.json")
                if os.path.exists(full_path):
                    os.remove(full_path)
                    st.success("Project deleted")
                    time.sleep(1.0)
                    st.rerun()
    st.divider()
    st.subheader("Export all projects", help="Export all projects to a zip file.")
    if st.button("Export"):
        zip_directory_path = shutil.make_archive("stores", "zip", "./stores")
        now = datetime.now()
        date_time_str = now.strftime("%Y-%m-%d-%H-%M")
        with open(zip_directory_path, "rb") as file:
            st.download_button(
                label="Download",
                data=file,
                file_name=f"projects_{date_time_str}.zip",
                mime="application/zip",
                type="primary"
            )
    st.divider()
    st.subheader("Import projects", help="Import projects from a zip file. Needs to be in the correct format.")
    uploaded_file = st.file_uploader(label="Upload zip project folder",
                                     type=".zip",
                                     accept_multiple_files=False)
    if uploaded_file is not None:
        if st.button("Import"):
            save_path = "uploaded_project.zip"
            with open(save_path, "wb") as file:
                file.write(uploaded_file.read())
            shutil.unpack_archive(save_path, "./stores", "zip")
            time.sleep(0.2)
            os.remove(save_path)
            if os.path.exists("stores.zip"):
                os.remove("stores.zip")
            st.success("Projects imported")
            time.sleep(2.0)
