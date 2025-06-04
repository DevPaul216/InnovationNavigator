import streamlit as st
from streamlit import session_state as sst
import os

def add_empty_lines(number_lines):
    for i in range(number_lines):
        st.write("")

def init_page():
    st.set_page_config(page_title="Innovation Navigator", layout="wide",
                       page_icon=os.path.join("misc", "LogoFH.png"),
                       initial_sidebar_state=sst.sidebar_state)

    st.markdown(
        """
            <style>
                .block-container {
                        padding-top: 0rem;
                        padding-bottom: 2rem;
                        padding-left: 2rem;
                        padding-right: 2rem;
                    }
                      [data-testid="stSidebar"] {
                        min-width: 250px;
                        max-width: 250px;
                    }
            </style>
            """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        .stDivider {
            margin-top: 5px;
            margin-bottom: 5px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

def get_config_value(name, for_template=True, config_value="display_name", default_value=""):
    if for_template:
        if name not in sst.template_config:
            return default_value
        config = sst.template_config[name]
    else:
        if name not in sst.elements_config:
            return default_value
        config = sst.elements_config[name]
    display_name = default_value
    if config_value in config:
        display_name = str(config[config_value])
    return display_name

def element_selection_format_func(item):
    return get_config_value(item, for_template=False)

def format_func(option):
    options_display_dict = {
        "documents": "External Document",
        "websearch": "Google Search",
        "website": "Website"
    }
    icon_dict = {
        "documents": ":material/description:",
        "websearch": ":material/globe:",
        "website": ":material/home:"
    }
    return f"{icon_dict[option]} {options_display_dict[option]}" 