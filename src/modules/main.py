import streamlit as st
from streamlit import session_state as sst
import os

from .state import init_session_state, update_data_store
from .ui_components import init_page
from .views import chart_view, init_graph, init_flow_graph

def open_sidebar():
    sst.sidebar_state = "expanded"

    # Add a logo to the top of the sidebar
    st.sidebar.image(os.path.join(".", "misc", "LogoFH.png"), use_container_width=True)

    # Button in sidebar to go back to overview
    if st.sidebar.button(label="Overview", type="primary", use_container_width=True):
        if sst.current_view != "chart":
            sst.selected_template_name = None
            sst.current_view = "chart"
            sst.sidebar_state = "expanded"
            sst.update_graph = True
            st.rerun()

    # New button to project selection
    if st.sidebar.button(label="Projects", type="secondary", use_container_width=True):
        sst.selected_template_name = "Start"  # Set to "Start" to open the project creation screen
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()

    # button in sidebar to open prompt editor
    if st.sidebar.button(label="Prompts", type="secondary", use_container_width=True):
        sst.selected_template_name = "Prompts"
        sst.current_view = "prompt"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()

    # button for other stuff
    if st.sidebar.button(label="About", type="secondary", use_container_width=True):
        sst.selected_template_name = "About"
        sst.current_view = "about"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()

    # button to open Data Store Browser
    if st.sidebar.button(label="Database", type="secondary", use_container_width=True):
        sst.selected_template_name = None
        sst.current_view = "datastore_browser"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()

def main():
    init_session_state()
    init_page()
    connection_states, completed_templates, blocked_templates = init_graph()
    init_flow_graph(connection_states, completed_templates, blocked_templates)
    open_sidebar()
    
    if sst.current_view == "chart":
        chart_view()
    elif sst.current_view == "detail":
        from .views import detail_view
        detail_view()
    elif sst.current_view == "prompt":
        from streamlit_prompteditor import prompt_editor_view
        prompt_editor_view("./canned_prompts")
    elif sst.current_view == "about":
        from .views import about_view
        about_view()
    elif sst.current_view == "datastore_browser":
        import streamlit_datastore_browser
        streamlit_datastore_browser.main()

if __name__ == '__main__':
    main() 