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
    # Ensure assigned is always a list
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
        artifact_keys.append(f"generated_{artifact_id}_{hash(str(artifact))}")
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
    compact_container_style = "padding: 0.2rem 0.5rem 0.2rem 0.2rem; margin-bottom: 0.2rem; border-radius: 6px; border: 1px solid #eee; background: #fafbfc;"
    for i, (artifact, artifact_key) in enumerate(zip(all_artifacts, artifact_keys)):
        # Remove st.divider() and use a thin line instead        # Removed divider for maximum compactness
        # if i != 0:
        #     st.markdown('<hr style="margin:2px 0 2px 0; border:0; border-top:1px solid #eee;"/>', unsafe_allow_html=True)
        # Use a more compact container
        with st.container():
            columns = st.columns([0.2, 2.5, 0.2, 1], gap="small")
            with columns[1]:
                st.markdown(f'<div style="{compact_container_style}">', unsafe_allow_html=True)
                if isinstance(artifact, str):
                    st.markdown(artifact)
                else:
                    st.image(artifact, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
            with columns[3]:
                # Show toggle ON if artifact is assigned, OFF otherwise
                is_assigned = artifact in assigned or (not isinstance(artifact, str) and any(isinstance(a, str) and a.endswith('.jpg') for a in assigned))
                toggled = st.toggle("Add", value=is_assigned, key=f"toggle_{artifact_key}")
                if toggled and not is_assigned:
                    # If artifact is an image, save to disk and store path
                    if not isinstance(artifact, str):
                        import hashlib
                        directory_path = './stores/image_store'
                        if not os.path.exists(directory_path):
                            os.makedirs(directory_path)
                        # Generate a unique filename based on hash
                        artifact.seek(0)
                        img = Image.open(artifact)
                        hash_digest = hashlib.sha256(artifact.getvalue()).hexdigest()[:10]
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
                    # Remove by path if image
                    if not isinstance(artifact, str):
                        # Remove any .jpg path from assigned
                        assigned[:] = [a for a in assigned if not (isinstance(a, str) and a.endswith('.jpg'))]
                    else:
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
    generated_images = []
    for _ in range(0, 3):
        generated_image = make_request_image(prompt, additional_information_dict=selected_resources)
        generated_images.append(generated_image)
    add_to_generated_artifacts(element_name, generated_images)


def generate_artifacts(element_name, is_image=False, generate_now_clicked=False):
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
    with st.expander("🧩 Choose individual elements from selected templates"):
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
                    # Get the display name and description
                    name_display = sst.elements_config[name].get("display_name", name)
                    description = sst.elements_config[name].get("description", "No description available.")
                    
                    # Format the resource text to include only the description and values
                    resource_text = f"_{description}_\n{resource_text}"
                    
                    selected_resources[name_display] = resource_text

    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    if prompt is None:
        st.error("There is no prompt assigned")
        return

    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    if prompt is None:
        st.error("There is no prompt assigned")
        return
    with st.expander(label="🌐 Add external information source"):
        home_url, query, number_entries_used, uploaded_files = resource_selection_view(element_name)
    schema = None   
     
    with st.expander(label="📝 View prompt"):  # added name of the prompt used to label
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

        with st.expander(label="🗂️ View response schema"):
            st.markdown("**Schema:** " + schema_name + ".json")
            st.json(schema)

   
    with st.expander("🎛️ Adjust Generation Parameters", expanded=False):

        # --- initialise defaults once ---
        st.session_state.setdefault("temperature", 1.0)
        st.session_state.setdefault("top_p", 1.0)

        # --- preset buttons ---
        cols = st.columns(3)
        if cols[0].button("Creative", key="creative_button"):
            st.session_state.update(temperature=1.6, top_p=1.0)
        if cols[1].button("Logic", key="logic_button"):
            st.session_state.update(temperature=0.2, top_p=1.0)
        if cols[2].button("Simplify", key="simple_button"):
            st.session_state.update(temperature=1.0, top_p=0.1)

        # --- sliders (keys match session state) ---
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



        # Synchronize sliders with session state
        temperature = st.session_state.temperature
        top_p = st.session_state.top_p

    if generate_now_clicked:
        with st.spinner("Generating..."):
            add_resources(selected_resources, home_url, number_entries_used, query, uploaded_files)
            if not is_image:
                handle_response(element_name, prompt, schema, selected_resources, temperature, top_p)
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
                            sub_columns = container.columns([1, 15, 1], vertical_alignment='center')
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
                                    text_to_show = ":heavy_exclamation_mark: No image available :heavy_exclamation_mark:"
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


def chart_view():
    add_empty_lines(1)
    st.subheader("Project: " + sst.project_name)
    add_empty_lines(1)

    legend_subview()


    with st.container(border=True):  # Add border to the container of the flow chart
        updated_state = streamlit_flow(
            key="ret_val_flow",
            state=sst.flow_state,
            height=800,  # Adjusted height for better visibility
            layout=LayeredLayout(direction="right"),
            fit_view=True,
            get_node_on_click=True,
            get_edge_on_click=False,
            show_controls=True,
            allow_zoom=False,
            pan_on_drag=False,
        )
    sst.selected_template_name = updated_state.selected_id
    if sst.selected_template_name is not None:
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        st.rerun()

    # Overlay a semi-transparent logo on the overview using HTML/CSS (centered, wider, and lower)
    logo_path = os.path.join("misc", "BackgroundDoubleDiamondPhases.png")
    if os.path.exists(logo_path):
        import base64
        with open(logo_path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode()
        st.markdown(
            f"""
            <div style="
                position: fixed;
                top: 220px;
                left: 58%;
                transform: translateX(-50%);
                z-index: 9999;
                pointer-events: none;
                width: 2100px;
                display: flex;
                justify-content: center;
            ">
                <img src="data:image/png;base64,{encoded}" style="width: 100%; max-width: 2100px; opacity: 0.18;"/>
            </div>
            """,
            unsafe_allow_html=True
        )


def element_selection_format_func(item):
    return get_config_value(item, for_template=False)


def general_creation_view(assigned_elements):
    st.subheader("Generate Information Artifacts")
    columns = st.columns([1, 1, 1, 2], vertical_alignment="center")
    with columns[0]:
        element_selected = st.selectbox(
            label="Select Element to generate: ",
            help="Select the element to generate artifacts for PLACEHOLDER",
            options=assigned_elements,
            format_func=element_selection_format_func
        )
    with columns[1]:
        creation_mode = st.segmented_control(
            label="Select Mode:",
            options=["Manual", "Generate", "Import"],
            default="Generate",
            help="Select the mode to create artifacts PLACEHOLDER"
        )
    generate_now_clicked = False
    with columns[2]:
        if creation_mode == "Generate":
            generate_now_clicked = st.button("Generate now!", type="primary", use_container_width=True)
        elif creation_mode == "Import":
            generate_now_clicked = st.button("Import now!", type="primary", use_container_width=True)
    auto_assign_max = st.toggle(
        "Auto-assign max allowed artifacts after generation",
        key="auto_assign_max_toggle",
        value=False,
        help="Automatically assigns the maximum allowed number of generated artifacts after generation."
    )
    element_store = sst.data_store[sst.selected_template_name]
    element_config = sst.elements_config[element_selected]
    is_single = True
    is_image = False
    if "type" in element_config:
        if element_config["type"] == "image":
            is_image = True
        else:
            is_single = False

    # --- Redesigned, dense, scrollable element list ---
    st.markdown("""
        <style>
        .dense-element-card {
            background: #f8f9fa;
            border-radius: 10px;
            margin-bottom: 0.5rem;
            padding: 1.1rem 1.5rem 1.1rem 1.5rem;
            box-shadow: 0 1px 4px rgba(0,0,0,0.04);
            border: 1px solid #e0e0e0;
            transition: box-shadow 0.2s;
        }
        .dense-element-card:hover {
            box-shadow: 0 2px 12px rgba(0,0,0,0.10);
        }
        .dense-element-title {
            font-size: 1.25em;
            font-weight: 600;
            margin-bottom: 0.2em;
        }
        .dense-element-desc {
            color: #666;
            font-size: 1em;
            margin-bottom: 0.2em;
        }
        .dense-element-count {
            color: #888;
            font-size: 0.95em;
            margin-bottom: 0.1em;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div style='max-height: 600px; overflow-y: auto;'>", unsafe_allow_html=True)
    for element in assigned_elements:
        config = sst.elements_config[element]
        display_name = config.get("display_name", element)
        description = config.get("description", "")
        artifact_count = len(element_store.get(element, []))
        st.markdown(f"""
            <div class='dense-element-card'>
                <div class='dense-element-title'>{display_name}</div>
                <div class='dense-element-desc'>{description}</div>
                <div class='dense-element-count'>Artifacts: <b>{artifact_count}</b></div>
                <div style='margin-top:0.5em;'>
                    <span style='font-size:0.95em;color:#888;'>Type: {config.get('type','text')}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # --- The rest of the logic for creation_mode, artifact input, etc. remains unchanged below ---
    # ...existing code...

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
                return f"Maximum of '{max_entries}' entries allowed. Remove some existing artifacts or choose less to continue."
    return None


def artifact_input_subview(element_selected, element_store):
    input_text = st.text_area(label="Type in artifacts manually:", key=f"textarea_{element_selected}",
                              label_visibility="collapsed")
    if st.button("Confirm", disabled=str(input_text).strip() == "", key=f"button_{element_selected}"):
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
    st.write("")
    st.write("")
    template_names = list(sst.template_config.keys())
    try:
        idx = template_names.index(sst.selected_template_name)
        prev_template = template_names[idx - 1] if idx > 0 else None
        next_template = template_names[idx + 1] if idx + 1 < len(template_names) else None
    except Exception:
        prev_template = None
        next_template = None

    # Hide navigation buttons on the projects screen (when selected_template_name == 'Start')
    show_nav = str(sst.selected_template_name).lower() != "start"
    nav_cols = st.columns([1, 1, 1], gap="large")
    with nav_cols[0]:
        if prev_template and show_nav:
            if st.button("\u25C0 Previous Template", key="prev_template", use_container_width=True, type="primary"):
                sst.selected_template_name = prev_template
                sst.current_view = "detail"
                sst.sidebar_state = "expanded"
                st.rerun()
    with nav_cols[1]:
        if show_nav:
            if st.button("\u2302 Back to Overview", key="back_to_overview", use_container_width=True, type="primary"):
                sst.selected_template_name = None
                sst.current_view = "chart"
                sst.sidebar_state = "expanded"
                st.rerun()
    with nav_cols[2]:
        if next_template and show_nav:
            if st.button("Next Template \u25B6", key="next_template", use_container_width=True, type="primary"):
                sst.selected_template_name = next_template
                sst.current_view = "detail"
                sst.sidebar_state = "expanded"
                st.rerun()

    # Centered template name and description with larger text
    st.markdown(f"""
        <div style='text-align: center;'>
            <h1 style='margin-bottom: 0.1em; font-size:2.7em;'>{get_config_value(sst.selected_template_name, config_value='display_name')}</h1>
            <div style='font-size: 1.0em; color: #666; margin-bottom:0.5em;'>{get_config_value(sst.selected_template_name, config_value='description')}</div>
        </div>
    """, unsafe_allow_html=True)
    if str(sst.selected_template_name).lower() == "start":
        start_sub_view()
    elif str(sst.selected_template_name).lower() == "end":
        end_sub_view()
    else:
        template_edit_subview()
    update_data_store()


def about_view():
    st.title("Welcome")
    st.markdown(
        "<h2 style='font-size:18px;'>Welcome to the Innovation Navigator — an experimental tool that helps innovators tackle real-world challenges by designing impactful products and business models. <br> Based on the Double Diamond framework, this tool guides you through a structured innovation journey using step-by-step templates tailored to each stage. <br> To begin, click the Start box on the far left to create a new project, or choose an existing one. Work through each template in sequence — complete one step to unlock the next, and keep moving forward on your innovation path!",
        unsafe_allow_html=True)
    # Add disclaimer
    st.markdown("---")
    st.markdown("# **Disclaimer - Read before use**")
    
    st.markdown("---")
    st.markdown("## **1. Experimental Nature**")
    st.markdown(
        "The Innovation Navigator is a **prototype tool currently under active development**. It is provided on an “as-is” and “as-available” basis and may include:"
    )
    st.markdown(
        """
        * **Bugs** or technical errors that could affect performance.
        * **Incomplete functionality** or features that are still being tested or refined.
        * **Inaccurate or misleading content**, due to the evolving nature of the AI models.
        """
    )
    st.markdown(
        "We encourage users to **explore and experiment** with the tool and to share **feedback that can guide future improvements**. However, this tool **should not be used to inform mission-critical decisions**, especially in business, legal, financial, medical, or strategic contexts."
    )
    st.markdown("---")
    st.markdown("## **2. Data Privacy**")
    st.markdown(
        "We are committed to safeguarding your data, but it is important to be aware of the following:"
    )
    st.markdown(
        """
        * The tool may temporarily **process user input to generate results**, but we do **not retain or share personal data**, unless explicitly stated or with your consent.
        * Since the Innovation Navigator leverages **third-party APIs and AI services** (e.g., for language processing or data analysis), user input **may be transmitted to external services** for processing.
        * We strongly recommend that users **avoid entering any confidential, sensitive, or personally identifiable information (PII)** when using the tool.
        """
    )
    st.markdown(
        "Your use of the tool constitutes acceptance of this data handling policy."
    )
    st.markdown("---")
    st.markdown("## **3. Safety and Ethical Use**")
    st.markdown(
        "The Innovation Navigator is intended solely for **educational, creative, and exploratory use**. Users are expected to:"
    )
    st.markdown(
        """
        * **Refrain from using the tool to produce or disseminate harmful, misleading, unethical, or illegal content**.
        * Ensure that their usage complies with all applicable **laws, regulations, and institutional policies**.
        * Understand that outputs generated by the AI **do not represent factual or authoritative advice**, and should be interpreted with care.
        """
    )
    st.markdown(
        "We reserve the right to restrict access to the tool if misuse is detected."
    )
    st.markdown("---")
    st.markdown("## **4. Limitations of AI**")
    st.markdown(
        "The AI systems that power the Innovation Navigator are based on advanced, but imperfect, machine learning models. As such:"
    )
    st.markdown(
        """
        * They may generate **outputs that are inaccurate, irrelevant, or biased**, reflecting limitations in training data or model design.
        * They **do not possess human judgment, understanding, or intentionality**, and should not be treated as authoritative sources.
        * Users are advised to **critically evaluate any content** produced and **consult subject matter experts** before taking action based on AI-generated insights.
        """
    )
    st.markdown("---")
    st.markdown("## **5. Limited Availability**")
    st.markdown(
        "At this stage, the Innovation Navigator is being offered as part of a **limited release** for research, testing, and user feedback. It is:"
    )
    st.markdown(
        """
        * Intended for use by a **select group of participants** and is not yet suitable for public or enterprise-scale deployment.
        * Not licensed or certified for **commercial, professional, or regulatory use**.
        * Subject to change, deprecation, or discontinuation at any time without prior notice.
        """
    )
    st.markdown("---")
    st.markdown(
        "By continuing to use the Innovation Navigator, you acknowledge and accept these terms and conditions. If you have any questions, concerns, or suggestions, please contact the development team at [Insert Contact Information]."
    )
    st.markdown("---")

    # Add a "Get Started" button in the middle of the page
    st.divider()
    if st.button("Get Started", type="primary", use_container_width=True):
        sst.selected_template_name = "Start"  # Set to "start" to open the project creation screen
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()


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


view_assignment_dict = {"general": general_creation_view}
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
    elif sst.current_view == "datastore_browser":
        import streamlit_datastore_browser
        streamlit_datastore_browser.main()
