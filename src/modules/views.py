import os
import streamlit as st
from streamlit import session_state as sst
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
from streamlit_flow.layouts import LayeredLayout
from streamlit_flow.state import StreamlitFlowState

from .ui_components import add_empty_lines, get_config_value
from .state import update_data_store, load_data_store, get_full_data_store_path
from .artifact_handling import display_generated_artifacts_view

# Define color scheme
COLOR_BLOCKED = "rgb(250, 240, 220)"
COLOR_COMPLETED = "rgb(104, 223, 200)"
COLOR_IN_PROGRESS = "rgb(255, 165, 0)"

# Define data store path
data_store_path = os.path.join("stores", "data_stores")

# Define view assignment dictionary
view_assignment_dict = {"general": None}  # This will be set by the main module

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

def legend_subview():
    legend_cols = st.columns([1, 1, 1, 1,1,1,1,1], gap="small")
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
    
    special_templates = [
        "align", "discover", "define", "develop", "deliver", "continue",
        "empathize", "define+", "ideate", "prototype", "test"
    ]
    if updated_state.selected_id is not None and updated_state.selected_id.lower() not in special_templates:
        sst.selected_template_name = updated_state.selected_id
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        st.rerun()

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
                sst.update_graph = True
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
        """
        The Innovation Navigator is a **prototype tool currently under active development**. It is provided on an "as-is" and "as-available" basis and may include:
        """
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

def start_sub_view():
    from pathlib import Path
    import shutil
    from datetime import datetime
    import time
    
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

def end_sub_view():
    st.header("Overview")
    for template_name in sst.template_config.keys():
        if template_name.lower() != "start" and template_name.lower() != "end":
            display_name = get_config_value(template_name)
            st.subheader(display_name)
            display_template_view(template_name)
            add_empty_lines(5)

def template_edit_subview():
    selected_template = sst.template_config[sst.selected_template_name]
    assigned_elements = selected_template["elements"]
    if assigned_elements is not None and len(assigned_elements) > 0:
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

def display_template_view(selected_template_name):
    element_store = sst.data_store[selected_template_name]
    selected_template_config = sst.template_config[selected_template_name]
    max_characters = 0
    element_names = list(element_store.keys())
    artifact_texts, artifact_images = get_elements_to_show(element_names, element_store, max_characters)
    vertical_gap = 2
    display_elements_subview(artifact_texts, artifact_images, element_names, selected_template_config,
                             vertical_gap)

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
                        with st.container(border=True, height=height_single):
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