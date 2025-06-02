import streamlit as st

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

data_store_path = os.path.join("stores", "data_stores")

def project_manager_view(current_project_name, on_project_switch=None):
  
  def start_sub_view():
    data_stores_paths = Path(data_store_path).glob("data_store_*.json")
    core_names = [path.stem for path in data_stores_paths]
    project_names = [str(name).split('data_store_')[1] for name in core_names]
    st.subheader("Add new Innovation Project", help="Create a new project to start working on it. You can also import existing projects.")
    new_project_name = st.text_input(label="Name of new Innovation Project").strip()
    if st.button("Create and open new Innovation Project", disabled=new_project_name == ""):
        if new_project_name not in project_names:
            # Save the current data store just to be sure
            update_data_store()
            sst.project_name = new_project_name
            # Create new empty data store
            sst.data_store = {}
            update_data_store()
            load_data_store()
            st.success("Project created")
            sst.sidebar_state = "expanded"
            sst.update_graph = True
            sst.current_view = "chart"  # Transition to the overview screen
            time.sleep(1.0)
            st.rerun()
        else:
            st.warning("A project with this name is already there")
    st.divider()
    st.subheader("Switch/Delete Project", help="Switch to another project or delete the current one.")
    selected_project_name = st.selectbox("Switch to another project:", options=project_names,
                                         index=project_names.index(sst.project_name))
    if selected_project_name != sst.project_name:
        sst.project_name = selected_project_name
        load_data_store()
        sst.sidebar_state = "expanded"
        st.rerun()
    if selected_project_name != "default":
        add_empty_lines(2)
        with st.expander("Delete Project"):
            if st.button("Delete"):
                os.remove(get_full_data_store_path())
                sst.project_name = "default"
                load_data_store()
                st.success("Deleted")
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
                file.write(uploaded_file.getbuffer())
            shutil.unpack_archive(save_path, "./stores", "zip")
            time.sleep(0.2)
            os.remove(save_path)
            os.remove("stores.zip")
            st.success("Projects imported")
            time.sleep(2.0)
            st.rerun()
