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
from utils import synchronize_shared_elements

from experimental.streamlit_artifact_generation import scrape_texts
# from streamlit_idea_generation import idea_generation_view  # commented out
from streamlit_prompteditor import prompt_editor_view
from utils import load_prompt, make_request_structured, load_schema, make_request_image
from website_parser import get_url_text_and_images

data_store_path = os.path.join("stores", "data_stores")
# Define color scheme
COLOR_BLOCKED = "rgb(250, 240, 220)"
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
                    if element not in element_store or not isinstance(element_store[element], list):
                        element_store[element] = []
                else:
                    group_elements = element_config["elements"]
                    for group_element in group_elements:
                        if group_element not in element_store or not isinstance(element_store[group_element], list):
                            element_store[group_element] = []
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
                        padding-top: 0rem; /* Reduced padding to give more space to the graph */
                        padding-bottom: 2rem;
                        padding-left: 2rem; /* Adjusted for better layout */
                        padding-right: 2rem;
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
    # Synchronize shared elements before saving
    synchronize_shared_elements(sst.data_store, sst.elements_config, sst.template_config)
    # --- Fix: Remove any BytesIO objects before saving ---
    for template, element_store in sst.data_store.items():
        for element, values in element_store.items():
            if isinstance(values, list):
                filtered = []
                for v in values:
                    if hasattr(v, 'getvalue') and callable(v.getvalue):
                        # This is a BytesIO or similar, skip it and warn
                        print(f"Warning: Skipping BytesIO object in {template} -> {element}")
                        continue
                    filtered.append(v)
                element_store[element] = filtered
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
            # Special formatting for key templates
            special_templates = [
                "align", "discover", "define", "develop", "deliver", "continue",
                "empathize", "define+", "ideate", "prototype", "test"
            ]
            if template_name.lower() in special_templates:
                style = {"backgroundColor": "white", "width": "320px", "padding": "1px", "border": "2px solid #bbb"}
                node = StreamlitFlowNode(
                    id=str(template_name),
                    pos=(0, 0),
                    data={'content': f"{template_display_name}"},
                    node_type="default",
                    source_position="right",
                    target_position="left",
                    style=style,
                    draggable=False,
                    focusable=False,
                    selectable=False
                )
            elif template_name == "Start":
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
                                         style={**style, "width": "90px", "padding": "1px"})
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
    # Combine generated artifacts and already assigned artifacts, show all with toggles
    generated = sst.generated_artifacts.get(element_name, {})
    assigned = sst.data_store[sst.selected_template_name][element_name]
    if isinstance(assigned, dict):
        assigned = list(assigned.values())
        sst.data_store[sst.selected_template_name][element_name] = assigned
    # Build a unique list: keep order, but don't duplicate
    all_artifacts = []
    artifact_keys = []
    # Add generated artifacts first (with their ids)
    for artifact_id, artifact in generated.items():
        all_artifacts.append(artifact)
        # Use both id and hash of artifact for uniqueness
        # For images, use hash of bytes if possible
        if hasattr(artifact, 'getvalue') and callable(artifact.getvalue):
            try:
                artifact_hash = hash(artifact.getvalue())
            except Exception:
                artifact_hash = hash(str(artifact))
        else:
            artifact_hash = hash(str(artifact))
        artifact_keys.append(f"generated_{artifact_id}_{artifact_hash}")
    # Add assigned artifacts that are not in generated
    for artifact in assigned:
        if artifact not in all_artifacts:
            all_artifacts.append(artifact)
            artifact_keys.append(f"assigned_{hash(str(artifact))}")
    if not all_artifacts:
        st.write("Nothing to show")
        return
    element_store = sst.data_store[sst.selected_template_name]
    # --- Make the display more compact ---
    compact_container_style = ""
    for i, (artifact, artifact_key) in enumerate(zip(all_artifacts, artifact_keys)):
        # Use a more compact container without any background, border, or margin
        with st.container():
            columns = st.columns([0.2, 2.5, 0.2, 1], gap="small")
            with columns[1]:
                # Show image if artifact is a path to an image file, else show as text
                if isinstance(artifact, str) and artifact.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    st.image(artifact, use_container_width=True)
                elif hasattr(artifact, 'getvalue') and callable(artifact.getvalue):
                    # Show BytesIO image
                    st.image(artifact, use_container_width=True)
                else:
                    st.markdown(str(artifact))
            with columns[3]:
                # Use a unique key for each toggle based on artifact_key and element_name
                is_assigned = artifact in assigned
                toggled = st.toggle("Add", value=is_assigned, key=f"toggle_{element_name}_{artifact_key}")
                if toggled and not is_assigned:
                    # For BytesIO images, save to disk and store path
                    if hasattr(artifact, 'getvalue') and callable(artifact.getvalue):
                        import hashlib
                        import os
                        from PIL import Image
                        artifact.seek(0)
                        img = Image.open(artifact)
                        hash_digest = hashlib.sha256(artifact.getvalue()).hexdigest()[:10]
                        directory_path = './stores/image_store'
                        if not os.path.exists(directory_path):
                            os.makedirs(directory_path)
                        filename = f"{element_name}_{sst.project_name}_{hash_digest}.jpg"
                        full_path = os.path.join(directory_path, filename)
                        img.save(full_path)
                        artifact_to_add = full_path
                    else:
                        artifact_to_add = artifact
                    check = check_can_add(element_store, element_name, [artifact_to_add])
                    if check is None:
                        assigned.append(artifact_to_add)
                        update_data_store()
                        st.rerun()
                    else:
                        st.warning(check)
                elif not toggled and is_assigned:
                    if artifact in assigned:
                        assigned.remove(artifact)
                        update_data_store()
                        st.rerun()


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
        # Use segmented control with single selection mode
        selected_option = st.segmented_control(
            label="Add additional Resources",
            options=used_resources,
            selection_mode='single',  # Allow only one selection
            format_func=format_func
        )

        if selected_option == "website":
            with st.container(border=True):
                st.subheader(":material/home: Website")
                home_url = st.text_input(label="Website URL").strip()

        elif selected_option == "websearch":
            with st.container(border=True):
                st.subheader(":material/globe: Google Search")
                query = st.text_input(label="Search Query").strip()
                number_entries_used = st.number_input(
                    label="Number of websites searched (1-10)",
                    min_value=1,
                    max_value=10,
                    value=5
                )

        elif selected_option == "documents":
            with st.container(border=True):
                st.subheader(":material/description: Documents")
                uploaded_files = st.file_uploader(
                    label="Upload Relevant Documents",
                    type="pdf",
                    accept_multiple_files=True
                )

    return home_url, query, number_entries_used, uploaded_files


def add_to_generated_artifacts(element_name, values):
    artifacts_dict = {}
    if not isinstance(values, list):
        values = [values]
    for i, value in enumerate(values):
        artifacts_dict[i] = value
    sst.generated_artifacts[element_name] = artifacts_dict
    sst.confirmed_artifacts[element_name] = {}


def handle_response(element_name, prompt, schema, selected_resources, temperature, top_p):
    response = make_request_structured(prompt, selected_resources, json_schema=schema, temperature=temperature, top_p=top_p)
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
    # Old code for generating 3 images:
    # generated_images = []
    # for _ in range(0, 3):
    #     generated_image = make_request_image(prompt, additional_information_dict=selected_resources)
    #     generated_images.append(generated_image)
    # add_to_generated_artifacts(element_name, generated_images)

    # New code: only generate one image
    generated_image = make_request_image(prompt, additional_information_dict=selected_resources)
    add_to_generated_artifacts(element_name, [generated_image])


def generate_artifacts(element_name, is_image=False, generate_now_clicked=False):
    element_config = sst.elements_config[element_name]
    required_items = element_config['used_templates']
    selected_resources = {}

    # --- Resource selection and Generation parameters side by side ---
    top_cols = st.columns([1, 1], gap="large")
    with top_cols[0]:
        home_url, query, number_entries_used, uploaded_files = resource_selection_view(element_name)
    with top_cols[1]:
        st.session_state.setdefault("temperature", 1.0)
        st.session_state.setdefault("top_p", 1.0)
        cols = st.columns(3)
        if cols[0].button("Creative", key="creative_button"):
            st.session_state.update(temperature=1.6, top_p=1.0)
        if cols[1].button("Logic", key="logic_button"):
            st.session_state.update(temperature=0.2, top_p=1.0)
        if cols[2].button("Simplify", key="simple_button"):
            st.session_state.update(temperature=1.0, top_p=0.1)
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.8,
            step=0.1,
            key="temperature"
        )
        top_p = st.slider(
            "Top-P",
            min_value=0.0,
            max_value=1.0,
            step=0.1,
            key="top_p"
        )
        temperature = st.session_state.temperature
        top_p = st.session_state.top_p

    # --- Combine Template selection and individual elements selection ---
    with st.expander("Template & Element selection (information sources)"):
        all_templates = list(sst.template_config.keys())
        selected_keys = st.multiselect(
            label="Suggested templates used as information sources for this generation (open dropdown menu to add others)",
            placeholder="Choose templates to use",
            options=all_templates,
            default=required_items
        )
        selected_elements = {}
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
        for selected_key, selected_elements_list in selected_elements.items():
            element_store = sst.data_store[selected_key]
            for name in selected_elements_list:
                resource_text = ""
                element_value = element_store[name]
                for value in element_value:
                    resource_text += f"- {value}\n"
                if resource_text.strip() != "":
                    name_display = sst.elements_config[name].get("display_name", name)
                    description = sst.elements_config[name].get("description", "No description available.")
                    resource_text = f"_{description}_\n{resource_text}"
                    selected_resources[name_display] = resource_text

    # --- Combine Prompt and Schema into one expander ---
    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    schema = None
    if not is_image:
        schema_name = element_config['schema_name']
        schema = load_schema(schema_name)
    with st.expander("Prompt & Response Schema"):
        st.markdown("**Prompt:** " + prompt_name + ".txt")
        if prompt:
            st.markdown(prompt)
        else:
            st.error("There is no prompt assigned")
        if not is_image and schema is not None:
            st.divider()
            st.markdown("**Schema:** " + schema_name + ".json")
            st.json(schema)
        st.divider()
        st.markdown("**Contextual Information:**")
        user_prompt = "\n".join([f"{key}: {value}" for key, value in selected_resources.items()])
        st.markdown(user_prompt)

    if generate_now_clicked:
        with st.spinner("Generating..."):
            add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files)
            if not is_image:
                handle_response(element_name, prompt, schema, selected_resources, temperature, top_p)
            else:
                handle_response_image(element_name, prompt, selected_resources)


def import_artifacts(element_name, generate_now_clicked=False):
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
            handle_response(element_name, prompt, schema, selected_resources, temperature=1.0, top_p=1.0)


def add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files):
    if home_url is not None:
        home_url_text, _ = get_url_text_and_images(home_url)
        selected_resources["Website_Text"] = home_url_text[:10000]
    if query is not None:
        texts_scrape = scrape_texts(query, number_entries_used)
        selected_resources.update(texts_scrape)
    # ↓ Fix: Ensure uploaded_files is a list
    if uploaded_files is not None:
        if not isinstance(uploaded_files, list):
            uploaded_files = [uploaded_files]
        if len(uploaded_files) > 0:
            text = ""
            for uploaded_file in uploaded_files:
                text += f"# {uploaded_file.name}\n"
                reader = PyPDF2.PdfReader(uploaded_file)
                for page in reader.pages:
                    text += page.extract_text() or ""
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
            # st.divider()
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
        update_data_store()
        st.rerun()


def display_artifact_view_image(element_selected, element_store):
    st.subheader("Available Artifacts")
    if element_selected not in element_store or len(element_store[element_selected]) == 0:
        st.write("Nothing here to show")
    else:
        columns = st.columns([1, 3, 1, 1], vertical_alignment="center")
        with columns[1]:
            image = element_store[element_selected]
            st.image(image)
        with columns[2]:
            if st.button(":x:", key=f"button_{element_selected}_image"):
                element_store[element_selected] = []
                update_data_store()
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
                artifact_text += "- " + str(artifact) + "  \n"
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
                            sub_columns = container.columns([1, 15, 1], vertical_alignment='center')
                            with sub_columns[1]:
                                # Combine name and description in a single line
                                element_config = sst.elements_config[element_name]
                                display_name = element_name
                                if "display_name" in element_config:
                                    display_name = element_config["display_name"]
                                description = element_config.get("description", "")
                                st.markdown(f"<span style='font-weight:bold;font-size:1.1em'>{display_name}</span> <span style='color:#888;font-size:0.98em'>{description}</span>", unsafe_allow_html=True)
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
                                    text_to_show = ":heavy_exclamation_mark: No image available :heavy_exclamation_mark:"
                                    st.markdown(text_to_show)
                            position += 1


def display_template_view(selected_template_name):
    element_store = sst.data_store[selected_template_name]
    selected_template_config = sst.template_config[selected_template_name]
    max_characters = 0
    element_names = list(element_store.keys())
    artifact_texts, artifact_images = get_elements_to_show(element_names, element_store, max_characters)
    vertical_gap = 2
    display_elements_subview(artifact_texts, artifact_images, element_names, selected_template_config,
                             vertical_gap)


def legend_subview():
    # Add a legend for the graph colors
    legend_cols = st.columns([1, 1, 1, 1,1,1,1,1], gap="small")  # Adjusted gap to reduce horizontal space
    with legend_cols[0]:
        st.markdown(
            f"<div style='background-color: {COLOR_BLOCKED}; width: 20px; height: 20px; display: inline-block;'></div> Requirements not met",
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


def get_progress_stats():
    total_required_elements = 0
    total_filled_required_elements = 0
    for template_name, element_store in sst.data_store.items():
        template_config = sst.template_config.get(template_name, {})
        elements = template_config.get("elements", [])
        for element in elements:
            element_config = sst.elements_config.get(element, {})
            if not element_config.get("required", True):
                continue
            if element not in element_store:
                continue
            total_required_elements += 1
            values = element_store[element]
            if (isinstance(values, list) and len(values) > 0) or (isinstance(values, str) and values.strip()):
                total_filled_required_elements += 1
    progress = (total_filled_required_elements / total_required_elements) if total_required_elements > 0 else 0
    return progress, total_filled_required_elements, total_required_elements


def chart_view():
    add_empty_lines(3)
    # Progress bar next to project title
    progress, frac_elements_filled, frac_templates_2_3 = get_progress_stats()
    cols = st.columns([3, 7])
    with cols[0]:
        st.subheader(f"Project: {sst.project_name}")
    with cols[1]:
        st.progress(progress, text=f"Progress: {int(progress*100)}%")
    add_empty_lines(1)
    legend_subview()

    with st.container(border=True):
        updated_state = streamlit_flow(
            key="ret_val_flow",
            state=sst.flow_state,
            height=800,
            layout=LayeredLayout(direction="right"),
            fit_view=True,
            get_node_on_click=True,
            get_edge_on_click=False,
            show_controls=True,
            allow_zoom=True,
            pan_on_drag=False,
        )
    # Prevent selection of special templates
    special_templates = [
        "align", "discover", "define", "develop", "deliver", "continue",
        "empathize", "define+", "ideate", "prototype", "test"
    ]
    if updated_state.selected_id is not None and updated_state.selected_id.lower() not in special_templates:
        sst.selected_template_name = updated_state.selected_id
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        st.rerun()


def element_selection_format_func(item):
    return get_config_value(item, for_template=False)


def general_creation_view(assigned_elements):
    #st.subheader("Generate Information Artifacts")
    # --- Main controls row ---
    top_cols = st.columns([1, 1], gap="medium")
    # Set default mode to 'Generate' when switching templates
    if 'last_template' not in sst or sst.last_template != sst.selected_template_name:
        sst['creation_mode'] = 'Generate'
        sst['last_template'] = sst.selected_template_name
    creation_mode = sst.get('creation_mode', 'Generate')
    with top_cols[0]:
        element_selected = st.selectbox(
            label="Select Element to generate:",
            help="Select the element to generate artifacts for.",
            options=assigned_elements,
            format_func=element_selection_format_func
        )
        # Move action buttons and auto-assign toggle here, below the selectbox
        action_cols = st.columns([1, 1, 2], gap="small")
        generate_now_clicked = False
        with action_cols[0]:
            if creation_mode == "Generate":
                generate_now_clicked = st.button("Generate now!", type="primary", use_container_width=True)
            elif creation_mode == "Import":
                generate_now_clicked = st.button("Import now!", type="primary", use_container_width=True)
        with action_cols[1]:
            auto_assign_max = False
            if creation_mode != "Manual":
                auto_assign_max = st.toggle(
                    "Auto-assign max allowed artifacts after generation",
                    key="auto_assign_max_toggle",
                    value=False,
                    help="Automatically assigns the maximum allowed number of generated artifacts after generation."
                )
    with top_cols[1]:
        # Parameters always on the right
        st.session_state.setdefault("temperature", 1.0)
        st.session_state.setdefault("top_p", 1.0)
        param_cols = st.columns(3)
        if param_cols[0].button("Creative", key="creative_button"):
            st.session_state.update(temperature=1.6, top_p=1.0)
        if param_cols[1].button("Logic", key="logic_button"):
            st.session_state.update(temperature=0.2, top_p=1.0)
        if param_cols[2].button("Simplify", key="simple_button"):
            st.session_state.update(temperature=1.0, top_p=0.1)
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.8,
            step=0.1,
            key="temperature"
        )
        top_p = st.slider(
            "Top-P",
            min_value=0.0,
            max_value=1.0,
            step=0.1,
            key="top_p"
        )
        temperature = st.session_state.temperature
        top_p = st.session_state.top_p

    # --- Combine Template selection and individual elements selection ---
    with st.expander("Template & Element selection (information sources)"):
        all_templates = list(sst.template_config.keys())
        selected_keys = st.multiselect(
            label="Suggested templates used as information sources for this generation (open dropdown menu to add others)",
            placeholder="Choose templates to use",
            options=all_templates,
            default=required_items
        )
        selected_elements = {}
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
        for selected_key, selected_elements_list in selected_elements.items():
            element_store = sst.data_store[selected_key]
            for name in selected_elements_list:
                resource_text = ""
                element_value = element_store[name]
                for value in element_value:
                    resource_text += f"- {value}\n"
                if resource_text.strip() != "":
                    name_display = sst.elements_config[name].get("display_name", name)
                    description = sst.elements_config[name].get("description", "No description available.")
                    resource_text = f"_{description}_\n{resource_text}"
                    selected_resources[name_display] = resource_text

    # --- Combine Prompt and Schema into one expander ---
    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    schema = None
    if not is_image:
        schema_name = element_config['schema_name']
        schema = load_schema(schema_name)
    with st.expander("Prompt & Response Schema"):
        st.markdown("**Prompt:** " + prompt_name + ".txt")
        if prompt:
            st.markdown(prompt)
        else:
            st.error("There is no prompt assigned")
        if not is_image and schema is not None:
            st.divider()
            st.markdown("**Schema:** " + schema_name + ".json")
            st.json(schema)
        st.divider()
        st.markdown("**Contextual Information:**")
        user_prompt = "\n".join([f"{key}: {value}" for key, value in selected_resources.items()])
        st.markdown(user_prompt)

    if generate_now_clicked:
        with st.spinner("Generating..."):
            add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files)
            if not is_image:
                handle_response(element_name, prompt, schema, selected_resources, temperature, top_p)
            else:
                handle_response_image(element_name, prompt, selected_resources)


def import_artifacts(element_name, generate_now_clicked=False):
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
            handle_response(element_name, prompt, schema, selected_resources, temperature=1.0, top_p=1.0)


def add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files):
    if home_url is not None:
        home_url_text, _ = get_url_text_and_images(home_url)
        selected_resources["Website_Text"] = home_url_text[:10000]
    if query is not None:
        texts_scrape = scrape_texts(query, number_entries_used)
        selected_resources.update(texts_scrape)
    # ↓ Fix: Ensure uploaded_files is a list
    if uploaded_files is not None:
        if not isinstance(uploaded_files, list):
            uploaded_files = [uploaded_files]
        if len(uploaded_files) > 0:
            text = ""
            for uploaded_file in uploaded_files:
                text += f"# {uploaded_file.name}\n"
                reader = PyPDF2.PdfReader(uploaded_file)
                for page in reader.pages:
                    text += page.extract_text() or ""
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
            # st.divider()
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
        update_data_store()
        st.rerun()


def display_artifact_view_image(element_selected, element_store):
    st.subheader("Available Artifacts")
    if element_selected not in element_store or len(element_store[element_selected]) == 0:
        st.write("Nothing here to show")
    else:
        columns = st.columns([1, 3, 1, 1], vertical_alignment="center")
        with columns[1]:
            image = element_store[element_selected]
            st.image(image)
        with columns[2]:
            if st.button(":x:", key=f"button_{element_selected}_image"):
                element_store[element_selected] = []
                update_data_store()
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
                artifact_text += "- " + str(artifact) + "  \n"
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
                            sub_columns = container.columns([1, 15, 1], vertical_alignment='center')
                            with sub_columns[1]:
                                # Combine name and description in a single line
                                element_config = sst.elements_config[element_name]
                                display_name = element_name
                                if "display_name" in element_config:
                                    display_name = element_config["display_name"]
                                description = element_config.get("description", "")
                                st.markdown(f"<span style='font-weight:bold;font-size:1.1em'>{display_name}</span> <span style='color:#888;font-size:0.98em'>{description}</span>", unsafe_allow_html=True)
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
                                    text_to_show = ":heavy_exclamation_mark: No image available :heavy_exclamation_mark:"
                                    st.markdown(text_to_show)
                            position += 1


def display_template_view(selected_template_name):
    element_store = sst.data_store[selected_template_name]
    selected_template_config = sst.template_config[selected_template_name]
    max_characters = 0
    element_names = list(element_store.keys())
    artifact_texts, artifact_images = get_elements_to_show(element_names, element_store, max_characters)
    vertical_gap = 2
    display_elements_subview(artifact_texts, artifact_images, element_names, selected_template_config,
                             vertical_gap)


def legend_subview():
    # Add a legend for the graph colors
    legend_cols = st.columns([1, 1, 1, 1,1,1,1,1], gap="small")  # Adjusted gap to reduce horizontal space
    with legend_cols[0]:
        st.markdown(
            f"<div style='background-color: {COLOR_BLOCKED}; width: 20px; height: 20px; display: inline-block;'></div> Requirements not met",
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


def get_progress_stats():
    total_required_elements = 0
    total_filled_required_elements = 0
    for template_name, element_store in sst.data_store.items():
        template_config = sst.template_config.get(template_name, {})
        elements = template_config.get("elements", [])
        for element in elements:
            element_config = sst.elements_config.get(element, {})
            if not element_config.get("required", True):
                continue
            if element not in element_store:
                continue
            total_required_elements += 1
            values = element_store[element]
            if (isinstance(values, list) and len(values) > 0) or (isinstance(values, str) and values.strip()):
                total_filled_required_elements += 1
    progress = (total_filled_required_elements / total_required_elements) if total_required_elements > 0 else 0
    return progress, total_filled_required_elements, total_required_elements


def chart_view():
    add_empty_lines(3)
    # Progress bar next to project title
    progress, frac_elements_filled, frac_templates_2_3 = get_progress_stats()
    cols = st.columns([3, 7])
    with cols[0]:
        st.subheader(f"Project: {sst.project_name}")
    with cols[1]:
        st.progress(progress, text=f"Progress: {int(progress*100)}%")
    add_empty_lines(1)
    legend_subview()

    with st.container(border=True):
        updated_state = streamlit_flow(
            key="ret_val_flow",
            state=sst.flow_state,
            height=800,
            layout=LayeredLayout(direction="right"),
            fit_view=True,
            get_node_on_click=True,
            get_edge_on_click=False,
            show_controls=True,
            allow_zoom=True,
            pan_on_drag=False,
        )
    # Prevent selection of special templates
    special_templates = [
        "align", "discover", "define", "develop", "deliver", "continue",
        "empathize", "define+", "ideate", "prototype", "test"
    ]
    if updated_state.selected_id is not None and updated_state.selected_id.lower() not in special_templates:
        sst.selected_template_name = updated_state.selected_id
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        st.rerun()


def element_selection_format_func(item):
    return get_config_value(item, for_template=False)


def general_creation_view(assigned_elements):
    #st.subheader("Generate Information Artifacts")
    # --- Main controls row ---
    top_cols = st.columns([1, 1], gap="medium")
    # Set default mode to 'Generate' when switching templates
    if 'last_template' not in sst or sst.last_template != sst.selected_template_name:
        sst['creation_mode'] = 'Generate'
        sst['last_template'] = sst.selected_template_name
    creation_mode = sst.get('creation_mode', 'Generate')
    with top_cols[0]:
        element_selected = st.selectbox(
            label="Select Element to generate:",
            help="Select the element to generate artifacts for.",
            options=assigned_elements,
            format_func=element_selection_format_func
        )
        # Move action buttons and auto-assign toggle here, below the selectbox
        action_cols = st.columns([1, 1, 2], gap="small")
        generate_now_clicked = False
        with action_cols[0]:
            if creation_mode == "Generate":
                generate_now_clicked = st.button("Generate now!", type="primary", use_container_width=True)
            elif creation_mode == "Import":
                generate_now_clicked = st.button("Import now!", type="primary", use_container_width=True)
        with action_cols[1]:
            auto_assign_max = False
            if creation_mode != "Manual":
                auto_assign_max = st.toggle(
                    "Auto-assign max allowed artifacts after generation",
                    key="auto_assign_max_toggle",
                    value=False,
                    help="Automatically assigns the maximum allowed number of generated artifacts after generation."
                )
    with top_cols[1]:
        # Parameters always on the right
        st.session_state.setdefault("temperature", 1.0)
        st.session_state.setdefault("top_p", 1.0)
        param_cols = st.columns(3)
        if param_cols[0].button("Creative", key="creative_button"):
            st.session_state.update(temperature=1.6, top_p=1.0)
        if param_cols[1].button("Logic", key="logic_button"):
            st.session_state.update(temperature=0.2, top_p=1.0)
        if param_cols[2].button("Simplify", key="simple_button"):
            st.session_state.update(temperature=1.0, top_p=0.1)
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.8,
            step=0.1,
            key="temperature"
        )
        top_p = st.slider(
            "Top-P",
            min_value=0.0,
            max_value=1.0,
            step=0.1,
            key="top_p"
        )
        temperature = st.session_state.temperature
        top_p = st.session_state.top_p

    # --- Combine Template selection and individual elements selection ---
    with st.expander("Template & Element selection (information sources)"):
        all_templates = list(sst.template_config.keys())
        selected_keys = st.multiselect(
            label="Suggested templates used as information sources for this generation (open dropdown menu to add others)",
            placeholder="Choose templates to use",
            options=all_templates,
            default=required_items
        )
        selected_elements = {}
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
        for selected_key, selected_elements_list in selected_elements.items():
            element_store = sst.data_store[selected_key]
            for name in selected_elements_list:
                resource_text = ""
                element_value = element_store[name]
                for value in element_value:
                    resource_text += f"- {value}\n"
                if resource_text.strip() != "":
                    name_display = sst.elements_config[name].get("display_name", name)
                    description = sst.elements_config[name].get("description", "No description available.")
                    resource_text = f"_{description}_\n{resource_text}"
                    selected_resources[name_display] = resource_text

    # --- Combine Prompt and Schema into one expander ---
    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    schema = None
    if not is_image:
        schema_name = element_config['schema_name']
        schema = load_schema(schema_name)
    with st.expander("Prompt & Response Schema"):
        st.markdown("**Prompt:** " + prompt_name + ".txt")
        if prompt:
            st.markdown(prompt)
        else:
            st.error("There is no prompt assigned")
        if not is_image and schema is not None:
            st.divider()
            st.markdown("**Schema:** " + schema_name + ".json")
            st.json(schema)
        st.divider()
        st.markdown("**Contextual Information:**")
        user_prompt = "\n".join([f"{key}: {value}" for key, value in selected_resources.items()])
        st.markdown(user_prompt)

    if generate_now_clicked:
        with st.spinner("Generating..."):
            add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files)
            if not is_image:
                handle_response(element_name, prompt, schema, selected_resources, temperature, top_p)
            else:
                handle_response_image(element_name, prompt, selected_resources)


def import_artifacts(element_name, generate_now_clicked=False):
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
            handle_response(element_name, prompt, schema, selected_resources, temperature=1.0, top_p=1.0)


def add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files):
    if home_url is not None:
        home_url_text, _ = get_url_text_and_images(home_url)
        selected_resources["Website_Text"] = home_url_text[:10000]
    if query is not None:
        texts_scrape = scrape_texts(query, number_entries_used)
        selected_resources.update(texts_scrape)
    # ↓ Fix: Ensure uploaded_files is a list
    if uploaded_files is not None:
        if not isinstance(uploaded_files, list):
            uploaded_files = [uploaded_files]
        if len(uploaded_files) > 0:
            text = ""
            for uploaded_file in uploaded_files:
                text += f"# {uploaded_file.name}\n"
                reader = PyPDF2.PdfReader(uploaded_file)
                for page in reader.pages:
                    text += page.extract_text() or ""
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
            # st.divider()
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
        update_data_store()
        st.rerun()


def display_artifact_view_image(element_selected, element_store):
    st.subheader("Available Artifacts")
    if element_selected not in element_store or len(element_store[element_selected]) == 0:
        st.write("Nothing here to show")
    else:
        columns = st.columns([1, 3, 1, 1], vertical_alignment="center")
        with columns[1]:
            image = element_store[element_selected]
            st.image(image)
        with columns[2]:
            if st.button(":x:", key=f"button_{element_selected}_image"):
                element_store[element_selected] = []
                update_data_store()
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
                artifact_text += "- " + str(artifact) + "  \n"
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
                            sub_columns = container.columns([1, 15, 1], vertical_alignment='center')
                            with sub_columns[1]:
                                # Combine name and description in a single line
                                element_config = sst.elements_config[element_name]
                                display_name = element_name
                                if "display_name" in element_config:
                                    display_name = element_config["display_name"]
                                description = element_config.get("description", "")
                                st.markdown(f"<span style='font-weight:bold;font-size:1.1em'>{display_name}</span> <span style='color:#888;font-size:0.98em'>{description}</span>", unsafe_allow_html=True)
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
                                    text_to_show = ":heavy_exclamation_mark: No image available :heavy_exclamation_mark:"
                                    st.markdown(text_to_show)
                            position += 1


def display_template_view(selected_template_name):
    element_store = sst.data_store[selected_template_name]
    selected_template_config = sst.template_config[selected_template_name]
    max_characters = 0
    element_names = list(element_store.keys())
    artifact_texts, artifact_images = get_elements_to_show(element_names, element_store, max_characters)
    vertical_gap = 2
    display_elements_subview(artifact_texts, artifact_images, element_names, selected_template_config,
                             vertical_gap)


def legend_subview():
    # Add a legend for the graph colors
    legend_cols = st.columns([1, 1, 1, 1,1,1,1,1], gap="small")  # Adjusted gap to reduce horizontal space
    with legend_cols[0]:
        st.markdown(
            f"<div style='background-color: {COLOR_BLOCKED}; width: 20px; height: 20px; display: inline-block;'></div> Requirements not met",
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


def get_progress_stats():
    total_required_elements = 0
    total_filled_required_elements = 0
    for template_name, element_store in sst.data_store.items():
        template_config = sst.template_config.get(template_name, {})
        elements = template_config.get("elements", [])
        for element in elements:
            element_config = sst.elements_config.get(element, {})
            if not element_config.get("required", True):
                continue
            if element not in element_store:
                continue
            total_required_elements += 1
            values = element_store[element]
            if (isinstance(values, list) and len(values) > 0) or (isinstance(values, str) and values.strip()):
                total_filled_required_elements += 1
    progress = (total_filled_required_elements / total_required_elements) if total_required_elements > 0 else 0
    return progress, total_filled_required_elements, total_required_elements


def chart_view():
    add_empty_lines(3)
    # Progress bar next to project title
    progress, frac_elements_filled, frac_templates_2_3 = get_progress_stats()
    cols = st.columns([3, 7])
    with cols[0]:
        st.subheader(f"Project: {sst.project_name}")
    with cols[1]:
        st.progress(progress, text=f"Progress: {int(progress*100)}%")
    add_empty_lines(1)
    legend_subview()

    with st.container(border=True):
        updated_state = streamlit_flow(
            key="ret_val_flow",
            state=sst.flow_state,
            height=800,
            layout=LayeredLayout(direction="right"),
            fit_view=True,
            get_node_on_click=True,
            get_edge_on_click=False,
            show_controls=True,
            allow_zoom=True,
            pan_on_drag=False,
        )
    # Prevent selection of special templates
    special_templates = [
        "align", "discover", "define", "develop", "deliver", "continue",
        "empathize", "define+", "ideate", "prototype", "test"
    ]
    if updated_state.selected_id is not None and updated_state.selected_id.lower() not in special_templates:
        sst.selected_template_name = updated_state.selected_id
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        st.rerun()


def element_selection_format_func(item):
    return get_config_value(item, for_template=False)


def general_creation_view(assigned_elements):
    #st.subheader("Generate Information Artifacts")
    # --- Main controls row ---
    top_cols = st.columns([1, 1], gap="medium")
    # Set default mode to 'Generate' when switching templates
    if 'last_template' not in sst or sst.last_template != sst.selected_template_name:
        sst['creation_mode'] = 'Generate'
        sst['last_template'] = sst.selected_template_name
    creation_mode = sst.get('creation_mode', 'Generate')
    with top_cols[0]:
        element_selected = st.selectbox(
            label="Select Element to generate:",
            help="Select the element to generate artifacts for.",
            options=assigned_elements,
            format_func=element_selection_format_func
        )
        # Move action buttons and auto-assign toggle here, below the selectbox
        action_cols = st.columns([1, 1, 2], gap="small")
        generate_now_clicked = False
        with action_cols[0]:
            if creation_mode == "Generate":
                generate_now_clicked = st.button("Generate now!", type="primary", use_container_width=True)
            elif creation_mode == "Import":
                generate_now_clicked = st.button("Import now!", type="primary", use_container_width=True)
        with action_cols[1]:
            auto_assign_max = False
            if creation_mode != "Manual":
                auto_assign_max = st.toggle(
                    "Auto-assign max allowed artifacts after generation",
                    key="auto_assign_max_toggle",
                    value=False,
                    help="Automatically assigns the maximum allowed number of generated artifacts after generation."
                )
    with top_cols[1]:
        # Parameters always on the right
        st.session_state.setdefault("temperature", 1.0)
        st.session_state.setdefault("top_p", 1.0)
        param_cols = st.columns(3)
        if param_cols[0].button("Creative", key="creative_button"):
            st.session_state.update(temperature=1.6, top_p=1.0)
        if param_cols[1].button("Logic", key="logic_button"):
            st.session_state.update(temperature=0.2, top_p=1.0)
        if param_cols[2].button("Simplify", key="simple_button"):
            st.session_state.update(temperature=1.0, top_p=0.1)
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.8,
            step=0.1,
            key="temperature"
        )
        top_p = st.slider(
            "Top-P",
            min_value=0.0,
            max_value=1.0,
            step=0.1,
            key="top_p"
        )
        temperature = st.session_state.temperature
        top_p = st.session_state.top_p

    # --- Combine Template selection and individual elements selection ---
    with st.expander("Template & Element selection (information sources)"):
        all_templates = list(sst.template_config.keys())
        selected_keys = st.multiselect(
            label="Suggested templates used as information sources for this generation (open dropdown menu to add others)",
            placeholder="Choose templates to use",
            options=all_templates,
            default=required_items
        )
        selected_elements = {}
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
        for selected_key, selected_elements_list in selected_elements.items():
            element_store = sst.data_store[selected_key]
            for name in selected_elements_list:
                resource_text = ""
                element_value = element_store[name]
                for value in element_value:
                    resource_text += f"- {value}\n"
                if resource_text.strip() != "":
                    name_display = sst.elements_config[name].get("display_name", name)
                    description = sst.elements_config[name].get("description", "No description available.")
                    resource_text = f"_{description}_\n{resource_text}"
                    selected_resources[name_display] = resource_text

    # --- Combine Prompt and Schema into one expander ---
    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    schema = None
    if not is_image:
        schema_name = element_config['schema_name']
        schema = load_schema(schema_name)
    with st.expander("Prompt & Response Schema"):
        st.markdown("**Prompt:** " + prompt_name + ".txt")
        if prompt:
            st.markdown(prompt)
        else:
            st.error("There is no prompt assigned")
        if not is_image and schema is not None:
            st.divider()
            st.markdown("**Schema:** " + schema_name + ".json")
            st.json(schema)
        st.divider()
        st.markdown("**Contextual Information:**")
        user_prompt = "\n".join([f"{key}: {value}" for key, value in selected_resources.items()])
        st.markdown(user_prompt)

    if generate_now_clicked:
        with st.spinner("Generating..."):
            add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files)
            if not is_image:
                handle_response(element_name, prompt, schema, selected_resources, temperature, top_p)
            else:
                handle_response_image(element_name, prompt, selected_resources)


def import_artifacts(element_name, generate_now_clicked=False):
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
            handle_response(element_name, prompt, schema, selected_resources, temperature=1.0, top_p=1.0)


def add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files):
    if home_url is not None:
        home_url_text, _ = get_url_text_and_images(home_url)
        selected_resources["Website_Text"] = home_url_text[:10000]
    if query is not None:
        texts_scrape = scrape_texts(query, number_entries_used)
        selected_resources.update(texts_scrape)
    # ↓ Fix: Ensure uploaded_files is a list
    if uploaded_files is not None:
        if not isinstance(uploaded_files, list):
            uploaded_files = [uploaded_files]
        if len(uploaded_files) > 0:
            text = ""
            for uploaded_file in uploaded_files:
                text += f"# {uploaded_file.name}\n"
                reader = PyPDF2.PdfReader(uploaded_file)
                for page in reader.pages:
                    text += page.extract_text() or ""
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
            # st.divider()
            with st.container():
                columns = st.columns([1, 3, 1, 2], vertical_alignment="center")
                with columns[1]:
                    st.markdown(artifact)
                with columns[3]:
                   