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
COLOR_COMPLETED = "rgb(76, 175, 80)"  # Green - more professional looking
COLOR_IN_PROGRESS = "rgb(255, 152, 0)"  # Orange - warmer tone
COLOR_NOT_STARTED = "rgb(224, 224, 224)"  # Light gray - neutral
COLOR_NEXT = "rgb(33, 150, 243)"  # Bright blue - stands out for recommended next



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
    # Ensure the graph is updated after data changes
    sst.update_graph = True


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


def get_template_status(template_name):
    """Determine the completion status of a template based on its elements."""
    if template_name in ["Start", "End"]:
        return "special"
        
    template_config = sst.template_config[template_name]
    element_store = sst.data_store.get(template_name, {})
    
    # Get all elements for this template
    elements = template_config.get("elements", [])
    if not elements:
        return "not_started"
        
    # Count total elements and filled elements
    total_elements = 0
    filled_elements = 0
    
    for element in elements:
        element_config = sst.elements_config.get(element, {})
        if element_config.get("type") == "group":
            # For group elements, check all sub-elements
            group_elements = element_config.get("elements", [])
            for sub_element in group_elements:
                total_elements += 1
                if sub_element in element_store and element_store[sub_element]:
                    filled_elements += 1
        else:
            # For regular elements
            total_elements += 1
            if element in element_store and element_store[element]:
                filled_elements += 1
    
    if total_elements == 0:
        return "not_started"
        
    completion_ratio = filled_elements / total_elements
    
    if completion_ratio == 0:
        return "not_started"
    elif completion_ratio == 1:
        return "completed"
    else:
        return "in_progress"


def init_flow_graph(connection_states, completed_templates, in_progress_templates, next_templates, blocked_templates):
    if sst.update_graph:
        nodes = []
        for i, template_name in enumerate(sst.template_config.keys()):
            template_display_name = get_config_value(template_name)
            template_status = get_template_status(template_name)
            
            # Special formatting for key templates
            special_templates = []
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
                # Set color based on template status
                if template_status == "completed":
                    bg_color = COLOR_COMPLETED
                elif template_status == "in_progress":
                    bg_color = COLOR_IN_PROGRESS
                else:  # not_started
                    bg_color = COLOR_NOT_STARTED
                    
                style = {
                    'background-color': bg_color,
                    'color': 'white',
                    'border': '1px solid #ccc',
                    'width': '90px',
                    'padding': '1px'
                }
                
                node = StreamlitFlowNode(
                    id=template_name,
                    pos=(0, 0),
                    data={'content': f"{template_display_name}"},
                    draggable=True,
                    focusable=False,
                    node_type="default",
                    source_position="right",
                    target_position="left",
                    style=style
                )
            nodes.append(node)
        edges = []
        for source, value in sst.template_config.items():
            for target in value["connects"]:
                edge_id = f'{source}-{target}'
                connection_state = connection_states.get(edge_id, False)
                edge = StreamlitFlowEdge(edge_id, str(source), str(target), marker_end={'type': 'arrowclosed'},
                                     animated=connection_state,
                                     style={"backgroundColor": "#ccc"})  # Use neutral gray for all edges
                edges.append(edge)
        sst.flow_state = StreamlitFlowState(nodes, edges)
        sst.update_graph = False


def init_graph():
    connection_states = {}
    
    for template_name, template_config in sst.template_config.items():
        # Skip special templates and Start/End
        if template_name in ["Start", "End"]:
            continue
        # Set all connections to non-animated by default
        for target in template_config.get("connects", []):
            edge_id = f"{template_name}-{target}"
            connection_states[edge_id] = False

    return connection_states, [], [], [], []  # Empty lists for the status arrays since we're not using them


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
                toggled = st.toggle("+", value=is_assigned, key=f"toggle_{element_name}_{artifact_key}")
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

    # --- Resource selection above Generation parameters ---
    home_url, query, number_entries_used, uploaded_files = resource_selection_view(element_name)
    
    # --- Generation parameters with presets and sliders ---
    with st.expander("Generation Parameters"):
        # Initialize session state values if they don't exist
        st.session_state.setdefault("temperature", 1.0)
        st.session_state.setdefault("top_p", 1.0)
        
        # Create two columns for better layout
        preset_col, slider_col = st.columns([1, 2])
        
        with preset_col:
            st.markdown("##### Parameter Presets")
            preset_buttons = st.columns(3)
            if preset_buttons[0].button("Creative", key="creative_button", use_container_width=True):
                st.session_state.update(temperature=1.6, top_p=1.0)
            if preset_buttons[1].button("Logic", key="logic_button", use_container_width=True):
                st.session_state.update(temperature=0.2, top_p=1.0)
            if preset_buttons[2].button("Simplify", key="simple_button", use_container_width=True):
                st.session_state.update(temperature=1.0, top_p=0.1)
        
        with slider_col:
            st.markdown("##### Fine-tune Parameters")
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.8,
                step=0.1,
                key="temperature",
                help="Higher values produce more creative results, lower values produce more focused results"
            )
            top_p = st.slider(
                "Top-P",
                min_value=0.0,
                max_value=1.0,
                step=0.1,
                key="top_p",
                help="Controls diversity of output. Lower values make output more focused"
            )
            temperature = st.session_state.temperature
            top_p = st.session_state.top_p    # --- Combine Template selection and individual elements selection ---
    with st.expander("Information Sources"):
        st.markdown("##### Select Templates and Elements to Use as Context")
        
        # Template selection
        all_templates = list(sst.template_config.keys())
        selected_keys = st.multiselect(
            label="Templates to use as information sources",
            placeholder="Choose templates to use",
            options=all_templates,
            default=required_items,
            help="Select templates to use as context for generation"
        )
        
        if selected_keys:
            st.divider()
            st.markdown("##### Select Elements from Each Template")
            
            # Element selection with better organization
            selected_elements = {}
            columns = st.columns(2)
            position = 0
            
            for selected_key in selected_keys:
                element_store = sst.data_store[selected_key]
                with columns[position]:
                    with st.container(border=True):
                        st.markdown(f"**{selected_key}**")
                        element_names = [element for element in element_store.keys() if element != element_name]
                        selection = st.multiselect(
                            label="Available elements",
                            options=element_names,
                            default=element_names, 
                            key=f"multiselect_{selected_key}"
                        )
                        selected_elements[selected_key] = selection
                position = (position + 1) % 2
                
            # Process selected elements to create resource text
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
                        selected_resources[name_display] = resource_text    # --- Combine Prompt and Schema into one expander ---
    prompt_name = element_config['prompt_name']
    prompt = load_prompt(prompt_name)
    schema = None
    if not is_image:
        schema_name = element_config['schema_name']
        schema = load_schema(schema_name)
    
    with st.expander("Prompt & Response Details"):
        # Create tabs for better organization
        prompt_tab, schema_tab, context_tab = st.tabs(["Prompt", "Response Schema", "Context"])
        
        with prompt_tab:
            st.markdown(f"##### System Prompt: `{prompt_name}.txt`")
            if prompt:
                with st.container(border=False, height=300):
                    st.markdown(prompt)
            else:
                st.error("No prompt assigned to this element")
                
        with schema_tab:
            if not is_image and schema is not None:
                st.markdown(f"##### Response Schema: `{schema_name}.json`")
                with st.container(border=False, height=300):
                    st.json(schema)
            else:
                if is_image:
                    st.info("Image generation does not use a response schema")
                else:
                    st.warning("No schema defined for this element")
                
        with context_tab:
            st.markdown("##### Contextual Information Used in Generation")
            if selected_resources:
                with st.container(border=False, height=300):
                    user_prompt = "\n".join([f"**{key}:**\n{value}\n" for key, value in selected_resources.items()])
                    st.markdown(user_prompt)
            else:
                st.info("No contextual information selected yet")

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
        st.info("Import is not available for this element type")
        return
        
    prompt_name = element_config['prompt_name_import']
    schema_name = element_config['schema_name_import']
    prompt = load_prompt(prompt_name)
    schema = load_schema(schema_name)

    # Add disclaimer in a more prominent container
    with st.container(border=True):
        cols = st.columns([1, 10])
        cols[0].markdown("⚠️")
        cols[1].warning(
            "The uploaded document must be a PDF containing selectable text. Image-based PDFs or scanned documents are not supported."
        )

    # File upload with clear instructions
    uploaded_files = st.file_uploader(
        "Upload document for importing (PDF format)", 
        type="pdf", 
        accept_multiple_files=False,
        help="Upload a document to extract structured information"
    )
    
    # Show details in tabs for better organization
    with st.expander("Import Details"):
        prompt_tab, schema_tab = st.tabs(["Import Prompt", "Import Schema"])
        
        with prompt_tab:
            st.markdown(f"##### System Prompt: `{prompt_name}.txt`")
            with st.container(border=False, height=300):
                st.markdown(prompt)
                
        with schema_tab:
            st.markdown(f"##### Import Schema: `{schema_name}.json`")
            with st.container(border=False, height=300):
                st.json(schema)

    # Only run the import if the button was clicked
    if generate_now_clicked:
        if not uploaded_files:
            st.error("Please upload a document before importing")
        else:
            with st.spinner("Processing uploaded document..."):
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
    legend_cols = st.columns([1, 1, 1, 1], gap="small")  # Back to 4 columns for the new status
    with legend_cols[0]:
        st.markdown(
            f"<div style='background-color: {COLOR_COMPLETED}; width: 20px; height: 20px; display: inline-block;'></div> Completed (All Required Elements)",
            unsafe_allow_html=True,
        )
    with legend_cols[1]:
        st.markdown(
            f"<div style='background-color: {COLOR_IN_PROGRESS}; width: 20px; height: 20px; display: inline-block;'></div> In Progress",
            unsafe_allow_html=True,
        )
    with legend_cols[2]:
        st.markdown(
            f"<div style='background-color: {COLOR_NEXT}; width: 20px; height: 20px; display: inline-block; border: 2px solid white;'></div> Next Recommended",
            unsafe_allow_html=True,
        )
    with legend_cols[3]:
        st.markdown(
            f"<div style='background-color: {COLOR_NOT_STARTED}; width: 20px; height: 20px; display: inline-block; border: 1px solid #9999FF;'></div> Not Started",
            unsafe_allow_html=True,
        )


def get_progress_stats():
    total_elements = 0
    total_filled_elements = 0

    # Skip special templates like "Start", "End"
    special_templates = ["Start", "End"]

    for template_name, template_config in sst.template_config.items():
        if template_name in special_templates or template_name.lower() in special_templates:
            continue

        elements = template_config.get("elements", [])
        element_store = sst.data_store.get(template_name, {})

        for element in elements:
            total_elements += 1
            if element in element_store:
                values = element_store[element]
                if (isinstance(values, list) and len(values) > 0) or (isinstance(values, str) and values.strip()):
                    total_filled_elements += 1

    progress = (total_filled_elements / total_elements) if total_elements > 0 else 0

    return progress, total_filled_elements, total_elements


def chart_view():
    add_empty_lines(3)
    # Progress bar next to project title
    progress, filled_elements, total_elements = get_progress_stats()
    
    cols = st.columns([3, 7])
    with cols[0]:
        st.subheader(f"Project: {sst.project_name}")
    with cols[1]:
        # Add more context to the progress display
        progress_text = f"Progress: {int(progress*100)}% ({filled_elements}/{total_elements} elements Templates)"
        st.progress(progress, text=progress_text)
        
    add_empty_lines(1)
    #legend_subview()

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
    special_templates = []
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
    top_cols = st.columns([1, 1, 1, 2], gap="medium")
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
    with top_cols[1]:
        # Use st.radio for robust single selection, avoid session state key conflicts
        new_creation_mode = st.radio(
            label="Select Mode:",
            options=["Manual", "Generate", "Import"],
            index=["Manual", "Generate", "Import"].index(creation_mode) if creation_mode in ["Manual", "Generate", "Import"] else 1,
            help="Select the mode to create artifacts."
        )
        if new_creation_mode != creation_mode:
            sst['creation_mode'] = new_creation_mode
            st.rerun()
        creation_mode = new_creation_mode
    generate_now_clicked = False
    with top_cols[2]:
        if creation_mode == "Generate":
            generate_now_clicked = st.button("Generate now!", type="primary", use_container_width=True)
        elif creation_mode == "Import":
            generate_now_clicked = st.button("Import now!", type="primary", use_container_width=True)
    with top_cols[3]:
        auto_assign_max = False
        if creation_mode != "Manual":
            auto_assign_max = st.toggle(
                "Auto-assign max allowed artifacts after generation",
                key="auto_assign_max_toggle",
                value=False,
                help="Automatically assigns the maximum allowed number of generated artifacts after generation."
            )

    element_store = sst.data_store[sst.selected_template_name]
    element_config = sst.elements_config[element_selected]
    is_image = element_config.get("type") == "image"
    is_single = not (element_config.get("type") == "group")
    selected_template_config = sst.template_config[sst.selected_template_name]
    vertical_gap = 1

    def auto_assign_artifacts(elements, is_image_type=False):
        rerun_needed = False
        for element in elements:
            generated = sst.generated_artifacts.get(element, {})
            assigned = element_store[element]
            config = sst.elements_config[element]
            max_entries = config.get("max", len(generated))
            new_artifacts = [artifact for artifact in generated.values() if artifact not in assigned]
            to_add = new_artifacts[:max_entries - len(assigned)]
            if config.get("type") == "image":
                rerun_needed = _assign_image_artifacts(element, element_store, to_add) or rerun_needed
            else:
                if to_add:
                    assigned.extend(to_add)
                    rerun_needed = True
        if rerun_needed:
            update_data_store()
            st.rerun()

    def _assign_image_artifacts(element, element_store, to_add):
        rerun = False
        for artifact in to_add:
            if not isinstance(artifact, str):
                add_image_to_image_store(element, element_store, artifact)
                rerun = True
            else:
                element_store[element].append(artifact)
                rerun = True
        return rerun

    def display_group_elements(elements_group, manual=False):
        position = 0
        for row_config in selected_template_config['display']:
            sub_rows = row_config['format']
            height = row_config['height'] * 2
            number_cols = len(sub_rows)
            cols = st.columns(number_cols, vertical_alignment='center')
            for col, sub_row in zip(cols, sub_rows):
                with col:
                    height_single = int(height / sub_row) - (sub_row - 1) * vertical_gap
                    for _ in range(sub_row):
                        if position < len(elements_group):
                            _display_group_element(elements_group[position], height_single, manual)
                            position += 1

    def _display_group_element(element_name, height_single, manual):
        config = sst.elements_config[element_name]
        display_name = config.get("display_name", element_name)
        description = config.get("description", "")
        with st.container(border=True, height=height_single):
            st.markdown(
                f"<span style='font-weight:bold;font-size:1.1em'>{display_name}</span> "
                f"<span style='color:#888;font-size:0.98em'>{description}</span>",
                unsafe_allow_html=True)
            if manual:
                artifact_input_subview(element_name, element_store)
                st.divider()
                st.markdown("**Assigned & Available Artifacts**")
            display_generated_artifacts_view(element_name)
            if not manual:
                st.divider()

    if creation_mode == "Manual":
        if is_single:
            with st.container(border=True):
                if not is_image:
                    artifact_input_subview(element_selected, element_store)
                else:
                    image_input_subview(element_selected, element_store)
                display_generated_artifacts_view(element_selected)
        else:
            elements_group = element_config["elements"]
            display_group_elements(elements_group, manual=True)
    elif creation_mode in ("Generate", "Import"):
        if creation_mode == "Generate":
            generate_artifacts(element_selected, is_image, generate_now_clicked)
            if generate_now_clicked and auto_assign_max:
                if is_single:
                    auto_assign_artifacts([element_selected], is_image)
                else:
                    elements_group = element_config["elements"]
                    auto_assign_artifacts(elements_group)
        if creation_mode == "Import":
            import_artifacts(element_selected, generate_now_clicked)
        st.divider()
        if is_single:
            st.subheader("Generated Artifacts")
            display_generated_artifacts_view(element_selected)
            if auto_assign_max:
                auto_assign_artifacts([element_selected], is_image)
        else:
            elements_group = element_config["elements"]
            display_group_elements(elements_group)
            if auto_assign_max:
                auto_assign_artifacts(elements_group)
    if is_single and is_image:
        st.divider()
        display_artifact_view_image(element_selected, element_store)


def template_edit_subview():
    selected_template = sst.template_config[sst.selected_template_name]
    assigned_elements = selected_template["elements"]
    if assigned_elements is not None and len(assigned_elements) > 0:
        # st.subheader("Overview")
        display_template_view(sst.selected_template_name)
        # Add confirmation for removing all artifacts
        if 'remove_all_confirm' not in sst:
            sst['remove_all_confirm'] = False
        if not sst['remove_all_confirm']:
            if st.button("Remove all artifacts from this template", type="secondary"):
                sst['remove_all_confirm'] = True
                st.rerun()
        else:
            st.warning("Are you sure you want to remove all artifacts from this template? This cannot be undone.")
            cols = st.columns([1,1])
            with cols[0]:
                if st.button("Yes, remove all", type="primary"):
                    # Find all elements that are shared across templates (including group elements)
                    elements_to_clear = set(assigned_elements)
                    # Recursively add group elements
                    def add_group_elements(el):
                        el_config = sst.elements_config.get(el, {})
                        if el_config.get("type") == "group":
                            for sub_el in el_config.get("elements", []):
                                elements_to_clear.add(sub_el)
                                add_group_elements(sub_el)
                    for el in list(elements_to_clear):
                        add_group_elements(el)
                    # Remove images from disk for image-type elements
                    for el in elements_to_clear:
                        el_config = sst.elements_config.get(el, {})
                        if el_config.get("type") == "image":
                            for template, element_store in sst.data_store.items():
                                if el in element_store:
                                    # Optionally: remove image file from disk here
                                    pass
                    # Clear the element in all templates (for all element stores, for all elements to clear)
                    for template, element_store in sst.data_store.items():
                        for el in elements_to_clear:
                            if el in element_store:
                                element_store[el] = []
                    update_data_store()
                    sst['remove_all_confirm'] = False
                    st.rerun()
            with cols[1]:
                if st.button("Cancel"):
                    sst['remove_all_confirm'] = False
                    st.rerun()
        st.divider()
        function = view_assignment_dict["general"]
        if sst.selected_template_name in view_assignment_dict:
            function = view_assignment_dict[sst.selected_template_name]
        function(assigned_elements)
    else:
        st.warning("No functions available. Check configuration!")


# def special_view_idea_generation(assigned_elements):
#     element_selected = st.selectbox(key="Select_Idea", label="Select Element to generate: ",
#                                     options=assigned_elements,
#                                     format_func=element_selection_format_func)
#     element_store = sst.data_store[sst.selected_template_name]
#     selected_idea = idea_generation_view()
#     st.divider()
#     display_artifacts_view(element_selected, element_store)
#     if selected_idea is not None:
#         element_store[element_selected] = [selected_idea]
#         update_data_store()
#         st.rerun()


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
            update_data_store()
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
            update_data_store()
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
        "The Innovation Navigator is a **prototype tool currently under active development**. It is provided on an "as-is" and "as-available" basis and may include:"
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
    if st.sidebar.button(label="About :(", type="secondary", use_container_width=True):
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
    connection_states, completed_templates, in_progress_templates, next_templates, blocked_templates = init_graph()
    init_flow_graph(connection_states, completed_templates, in_progress_templates, next_templates, blocked_templates)
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
