import io
import json
import os
import shutil
import time
from datetime import datetime
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
from streamlit_idea_generation import idea_generation_view
from streamlit_prompteditor import prompt_editor_view
from utils import load_prompt, make_request_structured, load_schema, make_request_image
from website_parser import get_url_text_and_images

data_store_path = os.path.join("stores", "data_stores")
# Define color scheme
COLOR_BLOCKED = "rgb(173, 200, 235)"
COLOR_COMPLETED = "rgb(104, 223, 200)"
COLOR_IN_PROGRESS = "rgb(255, 165, 0)"


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
        sst.template_config = load_json_dictionary(os.path.join("module_files", "templates_config.json"))
        sst.elements_config = load_json_dictionary(os.path.join("module_files", "elements_config.json"))
        sst.selected_template_name = None
        sst.sidebar_state = "collapsed"
        sst.update_graph = True
        sst.current_view = "chart"
        load_data_store()
        update_data_store()


def init_page():
    st.set_page_config(page_title="Innovation Navigator", layout="wide",
                       page_icon=os.path.join("misc", "LogoFH.png"),
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
                      /* Adjust the sidebar width */
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
    with open(path, "r", encoding="utf-8") as f:
        loaded_dictionary = json.load(f)
    return loaded_dictionary


def get_full_data_store_path():
    store_name = f"data_store_{sst.project_name}.json"
    return os.path.join(data_store_path, store_name)


def update_data_store():
    full_path = get_full_data_store_path()
    with open(full_path, "w", encoding="utf-8") as file:
        json.dump(sst.data_store, file, indent=4)


def load_data_store():
    full_path = get_full_data_store_path()
    if not os.path.exists(full_path):
        return {}
    sst.data_store = load_json_dictionary(full_path)
    align_data_store()


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


def init_flow_graph(connection_states, completed_templates, blocked_templates):
    if sst.update_graph:
        nodes = []
        for i, template_name in enumerate(sst.template_config.keys()):
            template_display_name = get_config_value(template_name)
            if template_name == "Start":
                node = StreamlitFlowNode(id=str(template_name), pos=(0, 0),
                                         data={'content': f"{template_display_name}"},
                                         node_type="input", source_position='right')
            elif template_name == "End":
                node = StreamlitFlowNode(id=str(template_name), pos=(0, 0),
                                         data={'content': f"{template_display_name}"},
                                         node_type="output", target_position='left')
            else:
                if template_name in blocked_templates:
                    style = {'background-color': COLOR_BLOCKED, "color": 'black'}
                elif template_name in completed_templates:
                    style = {'background-color': COLOR_COMPLETED, "color": 'black'}
                else:
                    style = {'background-color': COLOR_IN_PROGRESS, "color": 'black'}
                node = StreamlitFlowNode(id=template_name, pos=(0, 0), data={'content': f"{template_display_name}"},
                                         draggable=True, focusable=False, node_type="default", source_position="right",
                                         target_position="left",
                                         style={**style, "width": "70px", "padding": "1px"})
            nodes.append(node)
        edges = []
        for source, value in sst.template_config.items():
            # Skip edges connected to the "Prompts" template
            for target in value["connects"]:
                edge_id = f'{source}-{target}'
                connection_state = connection_states[edge_id]
                edge = StreamlitFlowEdge(edge_id, str(source), str(target), marker_end={'type': 'arrowclosed'},
                                         animated=connection_state,
                                         style={"backgroundColor": "green"})
                edges.append(edge)
        sst.flow_state = StreamlitFlowState(nodes, edges)
        sst.update_graph = False


def init_graph():
    connection_states = {}
    completed_templates = []
    for template_name, template_config in sst.template_config.items():
        is_fulfilled = True
        is_required = "required" not in template_config or template_config["required"]
        if is_required:
            elements = template_config["elements"]
            for element_name in elements:
                element_config = sst.elements_config[element_name]
                if element_config["required"]:
                    element_store = sst.data_store[template_name]
                    for element_values in element_store.values():
                        if element_values is None or len(element_values) == 0:
                            is_fulfilled = False
        if is_fulfilled:
            completed_templates.append(template_name)
        for target in template_config["connects"]:
            edge_id = f"{template_name}-{target}"
            connection_states[edge_id] = is_fulfilled
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
        # not needed: st.write("Artifacts:.")
        st.write("Nothing to show")
        return
    artifacts_dict = sst.generated_artifacts[element_name]
    for i, (artifact_id, artifact) in enumerate(artifacts_dict.items()):
        if i != 0:
            st.divider()
        with st.container():
            columns = st.columns([1, 3, 1, 2], vertical_alignment="center")
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


def format_func(option):
    options_display_dict = {
        "documents": "Description",
        "websearch": "globe",  # changed web to websearch
        "website": "home"
    }
    return f":material/{options_display_dict[option]}:"


def resource_selection_view(element_name):
    element_config = sst.elements_config[element_name]
    if "resources" in element_config:
        used_resources = element_config["resources"]
    else:
        used_resources = ["documents", "websearch", "website"]

    home_url = None
    query = None
    number_entries_used = None
    uploaded_files = None
    if used_resources is not None and len(used_resources) > 0:
        selected_option = st.segmented_control(label="Add additional Resources", options=used_resources,
                                               selection_mode='multi',
                                               format_func=format_func)
        if selected_option is not None:
            if "website" in selected_option:
                with st.container(border=True):
                    st.subheader("Website")
                    home_url = st.text_input(label="Website URL").strip()

            number_entries_used = 0
            if "websearch" in selected_option:
                with st.container(border=True):
                    st.subheader("Google Search")
                    query = st.text_input(label="Search Query").strip()
                    number_entries_used = st.number_input(label="Number of websites searched (1-10)", min_value=1,
                                                          max_value=10,
                                                          value=5)
            if "documents" in selected_option:
                with st.container(border=True):
                    st.subheader("Documents")
                    uploaded_files = st.file_uploader(label="Upload Relevant Documents", type="pdf",
                                                      accept_multiple_files=True)
    return home_url, query, number_entries_used, uploaded_files


def add_to_generated_artifacts(element_name, values):
    artifacts_dict = {}
    if not isinstance(values, list):
        values = [values]
    for i, value in enumerate(values):
        artifacts_dict[i] = value
    sst.generated_artifacts[element_name] = artifacts_dict
    sst.confirmed_artifacts[element_name] = {}


def handle_response(element_name, prompt, schema, selected_resources):
    response = make_request_structured(prompt, selected_resources, json_schema=schema)
    if response is not None and str(response).strip() != "":
        try:
            sst.generated_artifacts = {}
            sst.confirmed_artifacts = {}
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


def handle_response_image(element_name, prompt, selected_resources):
    generated_images = []
    for _ in range(0, 3):
        generated_image = make_request_image(prompt, additional_information_dict=selected_resources)
        generated_images.append(generated_image)
    add_to_generated_artifacts(element_name, generated_images)


def generate_artifacts(element_name, is_image=False):
    element_config = sst.elements_config[element_name]
    required_items = element_config['used_templates']
    selected_resources = {}

    # Fetch all template names from sst.template_config
    all_templates = list(sst.template_config.keys())
    # Dropdown to select templates
    selected_keys = st.multiselect(
        label="Suggested templates used as information sources for this generation (open dropdown menu to add others)",
        placeholder="Choose templates to use",
        options=all_templates,  # Show all templates as options
        default=required_items  # Preselect only the ones defined in the config
    )
    selected_elements = {}
    with st.expander("Choose individual elements from selected templates"):
        columns = st.columns(2)
        position = 0
        for selected_key in selected_keys:
            element_store = sst.data_store[selected_key]
            with columns[position]:
                element_names = [element for element in element_store.keys() if element != element_name]
                selection = st.multiselect(label=f"Available elements from template **{selected_key}**",
                                           options=element_names,
                                           default=element_names, key=f"multiselect_{selected_key}")
                selected_elements[selected_key] = selection
                position += 1
            if position >= 2:
                position = 0

        for selected_key, selected_elements in selected_elements.items():
            element_store = sst.data_store[selected_key]
            for name in selected_elements:
                resource_text = ""
                element_value = element_store[name]
                for value in element_value:
                    resource_text += f"- {value}\n"
                if resource_text.strip() != "":
                    if "display_name" in sst.elements_config[name]:
                        name = sst.elements_config[name]["display_name"]
                    selected_resources[name] = resource_text

    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    if prompt is None:
        st.error("There is no prompt assigned")
        return
    with st.expander(label="Add external information source"):
        home_url, query, number_entries_used, uploaded_files = resource_selection_view(element_name)
    schema = None    
    with st.expander(label="View prompt"):  # added name of the prompt used to label
        st.markdown("**Prompt:** " + prompt_name + ".txt")
        st.markdown(prompt)
        st.divider()
        st.markdown("**Contextual Information:**")
        # Construct the user prompt to show the user
        user_prompt = "\n".join([f"{key}: {value}" for key, value in selected_resources.items()])
        st.markdown(user_prompt)

    if not is_image:
        schema_name = element_config['schema_name']
        schema = load_schema(schema_name)

        with st.expander(label="View response schema"):
            st.markdown("**Schema:** " + schema_name + ".json")
            st.json(schema)

    if st.button("Generate now!", type="primary"):
        with st.spinner("Processing..."):
            add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files)
            if not is_image:
                handle_response(element_name, prompt, schema, selected_resources)
            else:
                handle_response_image(element_name, prompt, selected_resources)


def import_artifacts(element_name):
    element_config = sst.elements_config[element_name]
    if "prompt_name_import" not in element_config or "schema_name_import" not in element_config:
        st.write("Not available for this element")
        return
    prompt_name = element_config['prompt_name_import']
    schema_name = element_config['schema_name_import']
    prompt = load_prompt(prompt_name)
    schema = load_schema(schema_name)

    # Add disclaimer
    st.warning(
        "Please note: The uploaded document must be a PDF containing selectable text. Image-based PDFs or scanned documents are currently not supported.")

    uploaded_files = st.file_uploader("Upload document for importing", type="pdf", accept_multiple_files=False)
    with st.expander(label="Used prompt"):  # added name of the prompt used to label
        st.markdown("**System prompt:** " + prompt_name + ".txt")
        st.markdown(prompt)

    with st.expander(label="View import schema"):
        st.json(schema)

    add_empty_lines(1)
    if st.button("Import now!", type="primary"):
        with st.spinner("Processing..."):
            selected_resources = {}
            add_resources(selected_resources, None, None, None, uploaded_files)
            handle_response(element_name, prompt, schema, selected_resources)


def add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files):
    if home_url is not None:
        home_url_text, _ = get_url_text_and_images(home_url)
        selected_resources["Website_Text"] = home_url_text[:10000]
    if query is not None:
        texts_scrape = scrape_texts(query, number_entries_used)
        selected_resources.update(texts_scrape)
    if uploaded_files is not None and len(uploaded_files) > 0:
        text = ""
        for uploaded_file in uploaded_files:
            text += f"# {uploaded_file.name}\n"
            reader = PyPDF2.PdfReader(uploaded_file)
            for page in reader.pages:
                text += page.extract_text()
            text += "\n"
        selected_resources["document_text"] = text


def display_artifacts_view(element_selected, element_store):
    st.markdown("**Assigned Artifacts**")
    artifacts_to_show = element_store[element_selected]
    if len(artifacts_to_show) == 0:
        st.write("Nothing here yet.")
    deleted_artifacts = []
    for i, artifact in enumerate(artifacts_to_show):
        if i != 0:
            st.divider()
        with st.container():
            columns = st.columns([1, 3, 1, 2], vertical_alignment="center")
            with columns[1]:
                st.markdown(artifact)
            with columns[3]:
                if st.button(":x:", key=f"button_{element_selected}_{artifact}"):
                    deleted_artifacts.append(artifact)

    remaining_artifacts = [artifact for artifact in artifacts_to_show if artifact not in deleted_artifacts]
    element_store[element_selected] = remaining_artifacts
    # If something was marked for deletion refresh
    if len(deleted_artifacts) != 0:
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
                        # if element_name in artifact_images:
                        #    height_single = None
                        with st.container(border=True, height=height_single):
                            # with stylable_container(key="sc_" + str(position), css_styles=container_css):
                            container = st.container(border=False)
                            sub_columns = container.columns([1, 5, 1], vertical_alignment='center')
                            with sub_columns[1]:
                                element_config = sst.elements_config[element_name]
                                display_name = element_name
                                if "display_name" in element_config:
                                    display_name = element_config["display_name"]
                                st.subheader(display_name)
                                if element_name in artifact_texts:
                                    artifact_text = artifact_texts[element_name]
                                    if len(artifact_text) > 0:
                                        text_to_show = artifact_text
                                    else:
                                        text_to_show = "Nothing here yet."
                                        if 'required' not in element_config or element_config['required']:
                                            text_to_show = text_to_show + "\n \n Required :heavy_exclamation_mark:"
                                    st.markdown(text_to_show)
                            if element_name in artifact_images:
                                if artifact_images[element_name] is not None:
                                    container.image(artifact_images[element_name])
                                else:
                                    text_to_show = ":heavy_exclamation_mark: Kein Bild zum Anzeigen vorhanden"
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


def legend_subview():
    # Add a legend for the graph colors
    legend_cols = st.columns(3)
    with legend_cols[0]:
        st.markdown(
            f"<div style='background-color: {COLOR_BLOCKED}; width: 20px; height: 20px; display: inline-block;'></div> Recommended prerequisites not met",
            unsafe_allow_html=True,
        )
    with legend_cols[1]:
        st.markdown(
            f"<div style='background-color: {COLOR_COMPLETED}; width: 20px; height: 20px; display: inline-block;'></div> Completed/Optional",
            unsafe_allow_html=True,
        )
    with legend_cols[2]:
        st.markdown(
            f"<div style='background-color: {COLOR_IN_PROGRESS}; width: 20px; height: 20px; display: inline-block;'></div> Next Step",
            unsafe_allow_html=True,
        )


def chart_view():
    st.title("Innovation Navigator")

    st.markdown(
        "<h2 style='font-size:18px;'>Welcome to the Innovation Navigator — an experimental tool that helps innovators tackle real-world challenges by designing impactful products and business models. <br> Based on the Double Diamond framework, this tool guides you through a structured innovation journey using step-by-step templates tailored to each stage. <br> To begin, click the Start box on the far left to create a new project, or choose an existing one. Work through each template in sequence — complete one step to unlock the next, and keep moving forward on your innovation path!",
        unsafe_allow_html=True,
    )  # replaced header with this smaller text box.
    add_empty_lines(2)
    st.subheader("Project: " + sst.project_name)
    add_empty_lines(1)

    legend_subview()

    updated_state = streamlit_flow(
        key="ret_val_flow",
        state=sst.flow_state,
        height=500,
        layout=LayeredLayout(direction="right"),
        fit_view=True,
        get_node_on_click=True,
        get_edge_on_click=False,
        show_controls=True,
        allow_zoom=True,
        pan_on_drag=True,
    )
    sst.selected_template_name = updated_state.selected_id
    if sst.selected_template_name is not None:
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        st.rerun()


def element_selection_format_func(item):
    return get_config_value(item, for_template=False)


def general_creation_view(assigned_elements):
    st.subheader("Generate Information Artifacts")
    columns = st.columns([1, 1, 3], vertical_alignment="center")
    with columns[0]:
        element_selected = st.selectbox(label="Select Element to generate: ", options=assigned_elements,
                                        format_func=element_selection_format_func)
        # element_selected = "Portrait"
    with columns[1]:
        creation_mode = st.segmented_control(label="Select Mode:", options=["Manual", "Generate", "Import"], default="Manual", help="Select the mode to create artifacts PLACEHOLDER")
    element_store = sst.data_store[sst.selected_template_name]
    element_config = sst.elements_config[element_selected]
    is_single = True
    is_image = False
    if "type" in element_config:
        if element_config["type"] == "image":
            is_image = True
        else:
            is_single = False
    if creation_mode == "Manual":
        if is_single:
            with st.container(border=True):
                if not is_image:
                    artifact_input_subview(element_selected, element_store)
                else:
                    image_input_subview(element_selected, element_store)
        else:
            elements_group = element_config["elements"]
            elements_group_copy = elements_group.copy()
            position = 0
            max_elements_row = 2
            columns = st.columns(max_elements_row)
            while len(elements_group_copy) > 0:
                with columns[position]:
                    with st.container(border=True):
                        element_name = elements_group_copy.pop(0)
                        st.subheader(get_config_value(element_name, False))
                        st.markdown(get_config_value(element_name, False, "description"))
                        artifact_input_subview(element_name, element_store)
                        st.divider()
                        display_artifacts_view(element_name, element_store)
                        position += 1
                if position >= max_elements_row:
                    columns = st.columns(max_elements_row)
                    position = 0
    elif creation_mode == "Generate" or creation_mode == "Import":
        if creation_mode == "Generate":
            generate_artifacts(element_selected, is_image)
        if creation_mode == "Import":
            import_artifacts(element_selected)
        st.divider()
        if is_single:
            st.subheader("Generated Artifacts")
            confirm_single_subview(element_selected, element_store)
        else:
            elements_group = element_config["elements"]
            elements_group_copy = elements_group.copy()
            position = 0
            max_elements_row = 2
            columns = st.columns(max_elements_row)
            while len(elements_group_copy) > 0:
                with columns[position]:
                    with st.container(border=True):
                        element_name = elements_group_copy.pop(0)
                        st.subheader(get_config_value(element_name, False))
                        st.markdown(get_config_value(element_name, False, "description"))
                        confirm_single_subview(element_name, element_store)
                        st.divider()
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


def template_edit_subview():
    selected_template = sst.template_config[sst.selected_template_name]
    assigned_elements = selected_template["elements"]
    if assigned_elements is not None and len(assigned_elements) > 0:
        # st.subheader("Overview")
        display_template_view(sst.selected_template_name)
        st.divider()
        function = view_assignment_dict["general"]
        if sst.selected_template_name in view_assignment_dict:
            function = view_assignment_dict[sst.selected_template_name]
        function(assigned_elements)
    else:
        st.warning("No functions available. Check configuration!")


def special_view_idea_generation(assigned_elements):
    element_selected = st.selectbox(key="Select_Idea", label="Select Element to generate: ",
                                    options=assigned_elements,
                                    format_func=element_selection_format_func,
                                    help="Select the element to generate ideas for PLACEHOLDER")
    element_store = sst.data_store[sst.selected_template_name]
    selected_idea = idea_generation_view()
    st.divider()
    display_artifacts_view(element_selected, element_store)
    if selected_idea is not None:
        element_store[element_selected] = [selected_idea]
        update_data_store()
        st.rerun()


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
                    add_image_to_image_store(element_selected, element_store, confirmed_artifact)
            st.rerun()
        else:
            st.warning(check)


def confirm_generated_artifacts_view(element_name):
    with st.container(border=False):
        display_generated_artifacts_view(element_name)
        if element_name in sst.confirmed_artifacts and len(sst.confirmed_artifacts[element_name]) > 0:
            add_empty_lines(3)
            columns = st.columns([1, 3, 1])
            with columns[1]:
                if st.button("Confirm selected Artifacts", key=f"button_{element_name}", use_container_width=True):
                    return True
        return False


def check_can_add(element_store, element_selected, elements_to_add):
    if element_selected in sst.elements_config:
        element_config = sst.elements_config[element_selected]
        for element_to_add in elements_to_add:
            if element_to_add in element_store[element_selected]:
                return "This entry is already there"
        number_current_entries = len(element_store[element_selected])
        if "max" in element_config:
            max_entries = element_config["max"]
            if number_current_entries + len(elements_to_add) > max_entries:
                return f"Maximal '{max_entries}' Einträge erlaubt. Weniger Artefakte auswählen zum Hinzufügen oder zuvor bestehende löschen!"
    return None


def artifact_input_subview(element_selected, element_store):
    input_text = st.text_area(label="Type in artifacts manually:", key=f"textarea_{element_selected}",
                              label_visibility="collapsed")
    if st.button("Bestätigen", disabled=str(input_text).strip() == "", key=f"button_{element_selected}"):
        check = check_can_add(element_store, element_selected, [input_text])
        if check is None:
            element_store[element_selected].append(input_text)
            st.rerun()
        else:
            st.warning(check)


def add_image_to_image_store(element_selected, element_store, image):
    directory_path = './stores/image_store'
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)
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
        check = check_can_add(element_store, element_selected, [buffered])
        if check is None:
            add_image_to_image_store(element_selected, element_store, buffered)
            st.rerun()
        else:
            st.warning(check)


def detail_view():
    # removed temporarily blocking to make testing easier

    # if sst.selected_template_name in blocked_templates:
    #    st.text("Requirements not met. Fill previous templates")
    # el ....

    if sst.selected_template_name is not None and sst.selected_template_name in sst.template_config:
        st.title(get_config_value(sst.selected_template_name, config_value="display_name"))
        st.markdown(get_config_value(sst.selected_template_name, config_value="description"))
        if str(sst.selected_template_name).lower() == "start":
            start_sub_view()
        elif str(sst.selected_template_name).lower() == "end":
            end_sub_view()
        else:
            template_edit_subview()
    update_data_store()


def about_view():
    st.title("About")
    st.markdown("PLACEHOLDER for general infor about the project and system and so on")


def open_sidebar():
    sst.sidebar_state = "expanded"

    # Add a logo to the top of the sidebar
    st.sidebar.image(os.path.join(".", "misc", "LogoFH.png"), use_container_width=True)

    # Button in sidebar to go back to overview
    if st.sidebar.button(label="Overview", type="primary", use_container_width=True):
        if sst.current_view != "chart":  # Only rerun if not already on the "Overview" page because the fowchart collapsed otherwise
            sst.selected_template_name = None
            sst.current_view = "chart"
            sst.sidebar_state = "expanded"
            sst.update_graph = True
            st.rerun()

    # New button to project selection
    if st.sidebar.button(label="Projects", type="secondary", use_container_width=True):
        sst.selected_template_name = "Start"  # Set to "start" to open the project creation screen
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


def end_sub_view():
    st.header("Overview")
    for template_name in sst.template_config.keys():
        if template_name.lower() != "start" and template_name.lower() != "end":
            display_name = get_config_value(template_name)
            st.subheader(display_name)
            display_template_view(template_name)
            add_empty_lines(5)


def start_sub_view():
    data_stores_paths = Path(data_store_path).glob("data_store_*.json")
    core_names = [path.stem for path in data_stores_paths]
    project_names = [str(name).split('data_store_')[1] for name in core_names]
    st.subheader("Add new Innovation Project")
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
            time.sleep(1.0)
            st.rerun()
        else:
            st.warning("A project with this name is already there")
    st.divider()
    st.subheader("Switch/Delete Project")
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
    st.subheader("Export all projects")
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
    st.subheader("Import projects")
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


view_assignment_dict = {"general": general_creation_view,
                        "IdeaGeneration": special_view_idea_generation}
if __name__ == '__main__':
    init_session_state()
    init_page()
    connection_states, completed_templates, blocked_templates = init_graph()
    init_flow_graph(connection_states, completed_templates, blocked_templates)
    open_sidebar()
    if sst.current_view == "chart":
        chart_view()
    elif sst.current_view == "detail":
        detail_view()
    elif sst.current_view == "prompt":
        prompt_editor_view("./canned_prompts")
    elif sst.current_view == "about":
        about_view()
