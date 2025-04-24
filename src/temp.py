import base64
import io
import json
import os
from pathlib import Path

import PyPDF2
import streamlit as st
from PIL import Image
from streamlit import session_state as sst
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
from streamlit_flow.layouts import LayeredLayout
from streamlit_flow.state import StreamlitFlowState

from experimental.streamlit_artifact_generation import scrape_texts
from utils import load_prompt, load_schema, make_request_structured, make_request_image
from website_parser import get_url_text_and_images

data_store_path = "./data_stores/data_store"


def align_data_store():
    for template_name, template_config in sst.template_config.items():
        element_store = {}
        if template_name in sst.data_store:
            element_store = sst.data_store[template_name]
        elements = template_config["elements"]
        for element in elements:
            if element in sst.elements_config:
                element_config = sst.elements_config[element]
                if "type" not in element_config or element_config["type"] != "group":
                    if element not in element_store:
                        element_store[element] = {}
                else:
                    group_elements = element_config["elements"]
                    for group_element in group_elements:
                        if group_element not in element_store:
                            element_store[group_element] = {}
            else:
                print(
                    f"Element config of {element} referenced from template {template_name} not found in the element config!")
        sst.data_store[template_name] = element_store
        update_data_store()


def init_session_state():
    if "init" not in sst:
        sst.init = True
        sst.generated_artifacts = {}
        sst.confirmed_artifacts = {}
        sst.project_name = "default"
        load_data_store()
        update_data_store()
        sst.template_config = load_json_dictionary("./module_files/templates_config.json")
        sst.elements_config = load_json_dictionary("./module_files/elements_config.json")
        align_data_store()
        sst.selected_template_name = None
        sst.sidebar_state = "collapsed"
        sst.update_graph = True


def init_page():
    st.set_page_config(page_title="Innovation Assistant", layout="wide",
                       initial_sidebar_state=sst.sidebar_state)
    st.markdown(
        """
            <style>
                .block-container {
                        padding-top: 5rem;
                        padding-bottom: 5rem;
                        padding-left: 12rem;
                        padding-right: 12rem;
                    }
            </style>
            """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        .stDivider {
            margin-top: 5px;  /* Adjust the top margin */
            margin-bottom: 5px;  /* Adjust the bottom margin */
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def add_empty_lines(number_lines):
    for i in range(number_lines):
        st.write("")


def load_json_dictionary(path):
    with open(path, "r") as f:
        loaded_dictionary = json.load(f)
    return loaded_dictionary


def get_full_data_store_path():
    return f"{data_store_path}_{sst.project_name}.json"


def update_data_store():
    full_path = get_full_data_store_path()
    with open(full_path, "w") as file:
        json.dump(sst.data_store, file, indent=4)


def load_data_store():
    full_path = get_full_data_store_path()
    if not os.path.exists(full_path):
        return {}
    sst.data_store = load_json_dictionary(full_path)


def check_if_contained(data_store, required_items):
    is_available = True
    for required_item in required_items:
        if required_item not in data_store:
            is_available = False
    return is_available


def get_available_elements(elements, assigned_elements, data_store):
    available_elements = {}
    for name, config in elements.items():
        if name in assigned_elements:
            required_items = config['used_templates']
            if required_items is None or len(required_items) == 0:
                available_elements[name] = config
            else:
                is_available = check_if_contained(data_store, required_items)
                if is_available:
                    available_elements[name] = config
    return available_elements


def init_flow_graph(connection_states, completed_templates, blocked_templates):
    if sst.update_graph:
        nodes = []
        for i, template_name in enumerate(sst.template_config.keys()):
            if template_name == "Start":
                node = StreamlitFlowNode(id=str(template_name), pos=(0, 0), data={'content': f"{template_name}"},
                                         node_type="input", source_position='right')
            elif template_name == "End":
                node = StreamlitFlowNode(id=str(template_name), pos=(0, 0), data={'content': f"{template_name}"},
                                         node_type="output", target_position='left')
            else:
                if template_name in blocked_templates:
                    style = {'background-color': 'white', "color": 'black'}
                elif template_name in completed_templates:
                    style = {'background-color': 'green', "color": 'white'}
                else:
                    style = {'background-color': 'orange', "color": 'white'}
                node = StreamlitFlowNode(id=str(template_name), pos=(0, 0), data={'content': f"{template_name}"},
                                         draggable=False, focusable=False, node_type="default", source_position="right",
                                         target_position="left",
                                         style=style)
            nodes.append(node)
        edges = []
        for source, value in sst.template_config.items():
            for target in value["connects"]:
                id = f'{source}-{target}'
                connection_state = connection_states[id]
                edge = StreamlitFlowEdge(id, str(source), str(target), marker_end={'type': 'arrowclosed'},
                                         animated=connection_state,
                                         style={"backgroundColor": "green"})
                edges.append(edge)
        sst.flow_state = StreamlitFlowState(nodes, edges)
        sst.update_graph = False


def prepare_graph_elements():
    connection_states = {}
    completed_templates = []
    for template_name, template_config in sst.template_config.items():
        is_fulfilled = True
        elements = template_config["elements"]
        for element_name, element_config in elements.items():
            if element_config["required"]:
                element_store = sst.data_store[template_name]
                for element_values in element_store.values():
                    if element_values is None or len(element_values) == 0:
                        is_fulfilled = False
        if is_fulfilled:
            completed_templates.append(template_name)
        for target in template_config["connects"]:
            id = f"{template_name}-{target}"
            connection_states[id] = is_fulfilled
    blocked_templates = []
    for template_name, template_config in sst.template_config.items():
        connections = template_config["connects"]
        if template_name not in completed_templates or template_name in blocked_templates:
            blocked_templates.extend(connections)
    blocked_templates = list(set(blocked_templates))
    return connection_states, completed_templates, blocked_templates


def add_artifact(toggle_key, element_name, artifact_id, artifact):
    widget_state = sst[toggle_key]
    artifacts_dict = sst.confirmed_artifacts[element_name]
    if widget_state:
        artifacts_dict[artifact_id] = artifact
    else:
        artifacts_dict.pop(artifact_id, None)
    sst.confirmed_artifacts[element_name] = artifacts_dict


def display_generated_artifacts_view(element_name):
    if len(sst.generated_artifacts) == 0 or element_name not in sst.generated_artifacts:
        st.write("Keine generierten Einträge vorhanden")
        return
    artifacts_dict = sst.generated_artifacts[element_name]
    for artifact_id, artifact in artifacts_dict.items():
        with st.container():
            columns = st.columns([1, 3, 1, 1], vertical_alignment="center")
            with columns[1]:
                if isinstance(artifact, str):
                    st.markdown(artifact)
                else:
                    st.image(artifact)
            with columns[3]:
                st.toggle("Übernehmen", key=f"button_{artifact}_check",
                          on_change=add_artifact,
                          kwargs={"toggle_key": f"button_{artifact}_check", "element_name": element_name,
                                  "artifact_id": artifact_id, "artifact": artifact})
            st.divider()


def format_func(option):
    options_display_dict = {
        "documents": "Description",
        "web": "globe",
        "website": "home"
    }
    return f":material/{options_display_dict[option]}:"


def resource_selection_view(element_name):
    element_config = sst.elements_config[element_name]
    if "resources" in element_config:
        used_resources = element_config["resources"]
    else:
        used_resources = ["documents", "web", "website"]
    selected_option = st.segmented_control(label="Auswahl zusätzliche Ressourcen", options=used_resources,
                                           selection_mode='single',
                                           format_func=format_func)
    home_url = None
    query = None
    uploaded_files = None
    number_entries_used = None
    if selected_option is not None:
        if "website" in selected_option:
            with st.container(border=True):
                st.subheader("Website")
                home_url = st.text_input(label="URL der Website").strip()

        number_entries_used = 0
        if "web" in selected_option:
            with st.container(border=True):
                st.subheader("Google Suche")
                query = st.text_input(label="Search Query").strip()
                number_entries_used = st.number_input(label="Number of Entries Used", min_value=1, max_value=10,
                                                      value=2)
        if "documents" in selected_option:
            with st.container(border=True):
                st.subheader("Dokumente")
                uploaded_files = st.file_uploader(label="Dokumente hochladen", type="pdf")
    return home_url, query, number_entries_used, uploaded_files


def add_to_generated_artifacts(element_name, values):
    artifacts_dict = {}
    if not isinstance(values, list):
        values = [values]
    for i, value in enumerate(values):
        artifacts_dict[i] = value
    sst.generated_artifacts[element_name] = artifacts_dict
    sst.confirmed_artifacts[element_name] = {}


def generate_artifacts(element_name, is_image=False):
    element_config = sst.elements_config[element_name]
    required_items = element_config['used_templates']
    selected_resources = {}
    if required_items is not None and len(required_items) > 0:
        selected_keys = st.multiselect(label="Verwendete Elemente", options=required_items, default=required_items)
        for selected_key in selected_keys:
            element_store = sst.data_store[selected_key]
            for name, values in element_store.items():
                resource_text = ""
                for value in values:
                    resource_text += f"- {value}\n"
                selected_resources[name] = resource_text

    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    with st.expander(label="Used prompt"):
        st.markdown(prompt)
    with st.expander(label="Zusätzliche Resourcen"):
        home_url, query, number_entries_used, uploaded_files = resource_selection_view(element_name)
    if st.button("Generate") or True:
        with st.spinner("Wird verarbeitet"):
            add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files)
            if not is_image:
                sst.generated_artifacts = {}
                sst.confirmed_artifacts = {}
                schema_name = element_config['schema_name']
                schema = load_schema(schema_name)
                response = make_request_structured(prompt, selected_resources, json_schema=schema)
                if response is not None and str(response).strip() != "":
                    try:
                        response_dict = json.loads(response)
                        if len(response_dict) > 0:
                            if "points" in response_dict:
                                add_to_generated_artifacts(element_name, response_dict["points"])
                            else:
                                for name, values in response_dict.items():
                                    add_to_generated_artifacts(name, values)
                    except Exception as e:
                        st.error("Result received but could not be processed")
                        print(e)
                else:
                    st.warning("No results found")
            else:
                generated_images = []
                for _ in range(0, 3):
                    generated_image = make_request_image(prompt)
                    generated_images.append(generated_image)
                st.write("Append images")
                add_to_generated_artifacts(element_name, generated_images)


def add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files):
    if home_url is not None:
        home_url_text, _ = get_url_text_and_images(home_url)
        selected_resources["Website_Text"] = home_url_text[:10000]
    if query is not None:
        texts_scrape = scrape_texts(query, number_entries_used)
        selected_resources.update(texts_scrape)
    if uploaded_files is not None:
        reader = PyPDF2.PdfReader(uploaded_files)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        selected_resources["document_text"] = text


def display_artifacts_view(element_selected, element_store):
    st.subheader("Verfügbare Artefakte")
    artifacts_to_show = element_store[element_selected]
    if len(artifacts_to_show) == 0:
        st.write("Noch nichts vorhanden")
    deleted_artifacts = []
    for i, artifact in enumerate(artifacts_to_show):
        with st.container():
            columns = st.columns([1, 3, 1, 1], vertical_alignment="center")
            with columns[1]:
                st.markdown(artifact)
            with columns[2]:
                if st.button(":x:", key=f"button_{element_selected}_{artifact}"):
                    deleted_artifacts.append(artifact)
        if i != len(artifacts_to_show) - 1:
            st.divider()
    remaining_artifacts = [artifact for artifact in artifacts_to_show if artifact not in deleted_artifacts]
    element_store[element_selected] = remaining_artifacts
    # if len(artifacts_to_show) != len(remaining_artifacts):
    #    st.rerun()

"""def display_template_view(selected_template_name):
    element_store = sst.data_store[selected_template_name]
    selected_template_config = sst.template_config[selected_template_name]
    if "display" not in selected_template_config:
        return
    position = 0
    vertical_gap = 7
    artifact_texts = {}
    max_characters = 0
    element_names = list(element_store.keys())
    for element_name in element_names:
        element_artifacts = element_store[element_name]
        artifact_text = ""
        for artifact in element_artifacts:
            artifact_text += "- " + artifact + "  \n"
        if len(artifact_text) > max_characters:
            max_characters = len(artifact_text)
        artifact_texts[element_name] = artifact_text
    for row_config in selected_template_config['display']:
        sub_rows = row_config['format']
        height = row_config['height']
        number_cols = len(sub_rows)
        cols = st.columns(number_cols, vertical_alignment='center')
        for col, sub_row in zip(cols, sub_rows):
            with col:
                height_single = int(height / sub_row) - (sub_row - 1) * vertical_gap
                for number_subrows in range(0, sub_row):
                    with st.container(border=True, height=height_single):
                        # with stylable_container(key="sc_" + str(position), css_styles=container_css):
                        container = st.container(border=False)
                        sub_columns = container.columns([1, 5, 1], vertical_alignment='center')
                        with sub_columns[1]:
                            if position < len(element_names):
                                element_name = element_names[position]
                                st.subheader(get_display_name(element_name, False))
                                artifact_text = artifact_texts[element_name]
                                if len(artifact_text) > 0:
                                    text_to_show = artifact_text
                                else:
                                    text_to_show = "*No information available*"
                                    element_config = sst.elements_config[element_name]
                                    if "required" in element_config and element_config["required"]:
                                        text_to_show += "  \n :heavy_exclamation_mark: *Wird benötigt*"

                                sub_columns[1].markdown(text_to_show)
                                position += 1"""

def get_elements_to_show(element_names, element_store, max_characters):
    artifact_texts = {}
    artifact_images = {}
    for element_name in element_names:
        element_config = sst.elements_config[element_name]
        if 'type' in element_config and element_config['type'] == 'image':
            image_file = None
            if len(element_store[element_name]) > 0:
                image_file = element_store[element_name]
            artifact_images[element_name] = image_file
        else:
            element_artifacts = element_store[element_name]
            artifact_text = ""
            for artifact in element_artifacts:
                artifact_text += "- " + artifact + "  \n"
            if len(artifact_text) > max_characters:
                max_characters = len(artifact_text)
            artifact_texts[element_name] = artifact_text
    return artifact_texts, artifact_images


def display_elements_subview(artifact_texts, artifact_images, element_names, selected_template_config,
                             vertical_gap):
    position = 0
    # Each iteration add a row to the display
    for row_config in selected_template_config['display']:
        sub_rows = row_config['format']
        height = row_config['height']
        number_cols = len(sub_rows)
        cols = st.columns(number_cols, vertical_alignment='center')
        for col, sub_row in zip(cols, sub_rows):
            with col:
                height_single = int(height / sub_row) - (sub_row - 1) * vertical_gap
                for number_subrows in range(0, sub_row):
                    if position < len(element_names):
                        element_name = element_names[position]
                        if element_name in artifact_images:
                            height_single = None
                        with st.container(border=True, height=height_single):
                            # with stylable_container(key="sc_" + str(position), css_styles=container_css):
                            container = st.container(border=False)
                            sub_columns = container.columns([1, 5, 1], vertical_alignment='center')
                            with sub_columns[1]:
                                st.subheader(element_name)
                                if element_name in artifact_texts:
                                    artifact_text = artifact_texts[element_name]
                                    if len(artifact_text) > 0:
                                        text_to_show = artifact_text
                                    else:
                                        text_to_show = ":heavy_exclamation_mark: Keine Informationen verfügbar"
                                    st.markdown(text_to_show)
                            if element_name in artifact_images:
                                if artifact_images[element_name] is not None:
                                    container.image(artifact_images[element_name])
                                else:
                                    text_to_show = ":heavy_exclamation_mark: Keine Bild zum Anzeigen vorhanden"
                                    st.markdown(text_to_show)
                            position += 1


def display_template_view(selected_template_name):
    element_store = sst.data_store[selected_template_name]
    selected_template_config = sst.template_config[selected_template_name]
    max_characters = 0
    element_names = list(element_store.keys())
    artifact_texts, artifact_images = get_elements_to_show(element_names, element_store, max_characters)
    vertical_gap = 7
    display_elements_subview(artifact_texts, artifact_images, element_names, selected_template_config,
                             vertical_gap)


def chart_view():
    st.title("Innovation Assistant")
    add_empty_lines(2)
    st.header("Übersicht Ablauf")
    st.subheader("Derzeitiges Projekt: " + sst.project_name)
    add_empty_lines(3)
    updated_state = streamlit_flow(key='ret_val_flow',
                                   state=sst.flow_state,
                                   height=700,
                                   layout=LayeredLayout(direction='right'),
                                   fit_view=True,
                                   get_node_on_click=True,
                                   get_edge_on_click=False,
                                   show_controls=False,
                                   allow_zoom=False,
                                   pan_on_drag=False)
    sst.selected_template_name = updated_state.selected_id
    if sst.selected_template_name is not None:
        sst.sidebar_state = "expanded"
        st.rerun()


def display_artifact_view_image(element_selected, element_store):
    st.subheader("Verfügbares Artefakt")
    if element_selected not in element_store or len(element_store[element_selected]) == 0:
        st.write("Nichts vorhanden zum Anzeigen")
    else:
        columns = st.columns([1, 3, 1, 1], vertical_alignment="center")
        with columns[1]:
            image = element_store[element_selected]
            st.image(image)
        with columns[2]:
            if st.button(":x:", key=f"button_{element_selected}_image"):
                element_store[element_selected] = []
                st.rerun()


def template_edit_subview():
    element_store = sst.data_store[sst.selected_template_name]
    # convert_image_format(element_store)
    selected_template_config = sst.template_config[sst.selected_template_name]
    assigned_elements = selected_template_config["elements"]
    if assigned_elements is not None and len(assigned_elements) > 0:
        st.subheader("Überblick")
        display_template_view(sst.selected_template_name)
        st.divider()

        st.subheader("Artefakt Erzeugung")
        columns = st.columns([1, 1, 3], vertical_alignment="center")
        with columns[0]:
            element_selected = st.selectbox(label="Element", options=assigned_elements)
            # element_selected = 'Portrait'
        with columns[1]:
            creation_mode = st.segmented_control(label="Modus", options=["Manuell", "AI"], default="Manuell")
        element_config = sst.elements_config[element_selected]
        is_single = True
        is_image = False
        if "type" in element_config:
            if element_config["type"] == "image":
                is_image = True
            else:
                is_single = False
        if creation_mode == "Manuell":
            if is_single:
                if not is_image:
                    artifact_input_subview(element_selected, element_store)
                else:
                    image_input_subview(element_selected, element_store)
            else:
                elements_group = element_config["elements"]
                elements_group_copy = elements_group.copy()
                columns = st.columns(2)
                position = 0
                max_elements_row = 2
                while len(elements_group_copy) > 0:
                    with columns[position]:
                        with st.container(border=True):
                            element_name = elements_group_copy.pop(0)
                            st.subheader(element_name)
                            artifact_input_subview(element_name, element_store)
                            st.divider()
                            display_artifacts_view(element_name, element_store)
                            position += 1
                    if position >= max_elements_row:
                        columns = st.columns(2)
                        position = 0
        elif creation_mode == "AI":
            generate_artifacts(element_selected, is_image)
            st.divider()
            if is_single:
                st.subheader("Generierte Artefakte")
                confirm_single_subview(element_selected, element_store)
            else:
                elements_group = element_config["elements"]
                elements_group_copy = elements_group.copy()
                columns = st.columns(2)
                position = 0
                max_elements_row = 2
                while len(elements_group_copy) > 0:
                    with columns[position]:
                        with st.container(border=True):
                            element_name = elements_group_copy.pop(0)
                            st.subheader(element_name)
                            confirm_single_subview(element_name, element_store)
                            display_artifacts_view(element_name, element_store)
                            position += 1
                    if position >= max_elements_row and len(elements_group_copy) > 0:
                        number_columns = min(max_elements_row, len(elements_group_copy))
                        columns = st.columns(number_columns)
                        position = 0
        if is_single:
            st.divider()
            if not is_image:
                display_artifacts_view(element_selected, element_store)
            else:
                display_artifact_view_image(element_selected, element_store)
        # convert_image_format(element_store)
    else:
        st.caption("No functions available")


def convert_image_format(element_store):
    for element_name, values in element_store.items():
        element_config = sst.elements_config[element_name]
        if "type" in element_config and element_config["type"] == "image":
            clean_values = []
            for value in values:
                if not isinstance(value, str):
                    # clean_value = base64.b64encode(value.read()).decode('utf-8')
                    clean_value = base64.b64encode(value.getvalue()).decode("utf-8")
                else:
                    decoded_value = base64.b64decode(value)
                    clean_value = io.BytesIO(decoded_value)
                clean_values.append(clean_value)
            element_store[element_name] = clean_values


def confirm_generated_artifacts_view(element_name):
    display_generated_artifacts_view(element_name)
    if len(sst.confirmed_artifacts) > 0:
        if st.button("Auswahl bestätigen", key=f"button_{element_name}"):
            return True
    return False


def confirm_single_subview(element_selected, element_store):
    confirm_selection = confirm_generated_artifacts_view(element_selected)
    if confirm_selection:
        values_to_add = sst.confirmed_artifacts[element_selected].values()
        check = check_can_add(element_store, element_selected, values_to_add)
        if check is None:
            for confirmed_artifact in values_to_add:
                if isinstance(confirmed_artifact, str):
                    element_store[element_selected].append(confirmed_artifact)
                else:
                    add_image_to_element_store(element_selected, element_store, confirmed_artifact)
            st.rerun()
        else:
            st.warning(check)


def check_can_add(element_store, element_selected, elements_to_add):
    if element_selected in sst.elements_config:
        element_config = sst.elements_config[element_selected]
        for element_to_add in elements_to_add:
            if isinstance(element_to_add, str):
                if element_to_add in element_store[element_selected]:
                    return "Eintrag existiert bereits"
        number_current_entries = len(element_store[element_selected])
        max_entries = 100
        if "type" in element_config and element_config["type"] == "image":
            max_entries = 1
        elif "max" in element_config:
            max_entries = element_config["max"]
        if number_current_entries + len(elements_to_add) > max_entries:
            return f"Maximal '{max_entries}' Einträge erlaubt. Zuvor bestehende löschen um weitere hinzuzufügen!"
    return None


def artifact_input_subview(element_selected, element_store):
    with st.container(border=True):
        input_text = st.text_area(label="Hier eingeben", key=f"textarea_{element_selected}")
        if st.button("Bestätigen", disabled=str(input_text).strip() == "", key=f"button_{element_selected}"):
            check = check_can_add(element_store, element_selected, [input_text])
            if check is None:
                element_store[element_selected].append(input_text)
                st.rerun()
            else:
                st.warning(check)


def add_image_to_element_store(element_selected, element_store, image):
    directory_path = './image_store'
    if not os.path.exists(directory_path):
        os.makedirs('./image_store')
    image = Image.open(image)
    filename = element_selected + "_" + sst.project_name + '.jpg'
    full_path = os.path.join(directory_path, filename)
    image.save(full_path)
    element_store[element_selected] = [full_path]


def image_input_subview(element_selected, element_store):
    uploaded_file = st.file_uploader("Wähle ein Bild aus ...", type=[".jpg", ".jpeg", ".png", ".gif"])
    if uploaded_file is not None:
        st.image(uploaded_file)
    if st.button("Bestätigen", disabled=uploaded_file is None):
        # decoded_image = Image.open()
        buffered = io.BytesIO(uploaded_file.read())
        # decoded_image.save(buffered, format="PNG")
        add_image_to_element_store(element_selected, element_store, buffered)
        st.rerun()


def detail_view():
    if sst.selected_template_name in blocked_templates and False:
        st.text("Zuerst vorherige Methoden abschließen")
    elif sst.selected_template_name is not None and sst.selected_template_name in sst.template_config:
        st.title(sst.selected_template_name)
        if str(sst.selected_template_name).lower() == "start":
            start_sub_view()
        elif str(sst.selected_template_name).lower() == "end":
            end_sub_view()
        else:
            template_edit_subview()
    else:
        st.warning(f"Something is wrong with the configuration of {sst.selected_template_name}")
    update_data_store()
    st.divider()
    if st.sidebar.button(label="Zurück", type="primary", use_container_width=True):
        sst.selected_template_name = None
        sst.sidebar_state = "collapsed"
        sst.update_graph = True
        st.rerun()


def end_sub_view():
    st.header("Übersicht")
    for template_name in sst.template_config.keys():
        if "display" in sst.template_config[template_name]:
            st.subheader(template_name)
            display_template_view(template_name)
            add_empty_lines(5)


def start_sub_view():
    data_stores_paths = Path(".\data_stores").glob("data_store_*.json")
    core_names = [path.stem for path in data_stores_paths]
    project_names = [str(name).split('data_store_')[1] for name in core_names]
    st.subheader("Neues Projekt erstellen")
    new_project_name = st.text_input(label="Neuer Projektname").strip()
    if st.button("Projekt erstellen und zu diesem wechseln", disabled=new_project_name == ""):
        if new_project_name not in project_names:
            # Save the current data store just to be sure
            update_data_store()
            sst.project_name = new_project_name
            # Create new empty data store
            sst.data_store = {}
            align_data_store()
            update_data_store()
            st.success("Projekt erstellt.")
            st.rerun()
        else:
            st.warning("Projektname existiert bereits")
    st.divider()
    st.subheader("Projekt wechseln")
    selected_project_name = st.selectbox("Verfügbare Projekte", options=project_names,
                                         index=project_names.index(sst.project_name))
    if selected_project_name != sst.project_name:
        sst.project_name = selected_project_name
        load_data_store()
        st.rerun()
    if selected_project_name != "default":
        with st.expander("Projekt löschen"):
            if st.button("Löschen"):
                os.remove(get_full_data_store_path())
                sst.project_name = "default"
                load_data_store()
                st.write("Deleted")
                st.rerun()


if __name__ == '__main__':
    init_session_state()
    init_page()
    connection_states, completed_templates, blocked_templates = prepare_graph_elements()
    init_flow_graph(connection_states, completed_templates, blocked_templates)
    sst.selected_template_name = "Persona"
    if sst.selected_template_name is None:
        chart_view()
    else:
        detail_view()
