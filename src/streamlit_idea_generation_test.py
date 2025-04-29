import json

import streamlit as st
from streamlit import session_state as sst
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
from streamlit_flow.layouts import TreeLayout
from streamlit_flow.state import StreamlitFlowState

from utils import load_prompt, make_request_structured, load_schema


def init_idea_session_state():
    if "init_idea_generation" not in sst:
        sst.init_idea_generation = True
        sst.response_dict = None
        sst.update_idea_graph = False
        sst.layers = []
        sst.position = 0
        sst.flow_state_idea_graph = StreamlitFlowState([], [])
        sst.response_dict = {}
        sst.selected_id = None
        sst.selected_mode = "Manual"
        sst.root_node_id = None


init_idea_session_state()


def init_page():
    st.set_page_config(page_title="Innovation Assistant", layout="wide",
                       initial_sidebar_state="collapsed")
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


def get_graph_elements():
    nodes = []
    for node_id, values in sst.layers.items():
        value = values["value"]
        number_children = len(values["children"])
        if node_id == sst.root_node_id:
            node = StreamlitFlowNode(id=node_id, pos=(0, 0), data={'content': f"{value}"},
                                     node_type="input", source_position='right')
        elif number_children <= 0:
            node = StreamlitFlowNode(id=node_id, pos=(0, 0), data={'content': f"{value}"},
                                     node_type="output", target_position='left')
        else:
            node = StreamlitFlowNode(id=node_id, pos=(0, 0), data={'content': f"{value}"},
                                     draggable=False, focusable=False, node_type="default", source_position="right",
                                     target_position="left")
        nodes.append(node)
    edges = []
    for node_id, values in sst.layers.items():
        children = values["children"]
        for child in children:
            id = f'{node_id}-{child}'
            edge = StreamlitFlowEdge(id, str(node_id), str(child), marker_end={'type': 'arrowclosed'},
                                     animated=False, style={"backgroundColor": "green"})
            edges.append(edge)
    return nodes, edges


def append_child(parent_id, child):
    parent_value = sst.layers[parent_id]
    number_children = len(parent_value["children"])
    new_child_id = parent_id + f"_{number_children + 1}"
    sst.layers[new_child_id] = {"value": child, "children": []}
    parent_value["children"].append(new_child_id)


def delete_node(node_id):
    selected_value = sst.layers[node_id]
    children = selected_value["children"]
    for child in children:
        delete_node(child)
    sst.layers.pop(node_id)


def clean_dangling():
    for node_id, value in sst.layers.items():
        updated_values = []
        for child in value["children"]:
            if child in sst.layers:
                updated_values.append(child)
        value["children"] = updated_values


def idea_generation_view():
    theme = st.text_input("Topic", value="Zeitfresser im Alltag enttarnen")
    if st.button("New Idea tree topic", disabled=str(theme).strip() == ""):
        sst.position = 0
        node_id = "0"
        sst.layers = {node_id: {"value": theme, "children": []}}
        st.write(f"Using '{theme}' as new root")
        sst.update_idea_graph = True
        sst.root_node_id = node_id
    if sst.root_node_id is not None:
        root_node = sst.layers[sst.root_node_id]
        st.subheader("Thema: " + root_node["value"])
        # st.json(sst.layers)

    max_depth = 4
    # st.write(json.dumps(sst.layers))
    if sst.update_idea_graph:
        nodes, edges = get_graph_elements()
        # st.write("Nodes", nodes)
        # st.write("Edges", edges)
        sst.flow_state_idea_graph = StreamlitFlowState(nodes, edges)
        sst.update_idea_graph = False
        # st.rerun()
    with st.container():
        flow_state = streamlit_flow(key='idea_generation_graph' + str(len(sst.layers)),
                                    state=sst.flow_state_idea_graph,
                                    height=700,
                                    layout=TreeLayout(direction='right', node_node_spacing=200),
                                    fit_view=True,
                                    get_node_on_click=True,
                                    get_edge_on_click=False,
                                    show_controls=True,
                                    allow_zoom=True,
                                    pan_on_drag=True)
    # st.write(sst.selected_id)
    if flow_state.selected_id is not None and sst.selected_id != flow_state.selected_id:
        sst.selected_id = flow_state.selected_id
    # st.write("Selected id: ", sst.selected_id)
    # st.write("Float state id", flow_state.selected_id)
    # st.write(sst.layers)
    st.subheader("Auswahl")
    if sst.selected_id is not None and sst.selected_id in sst.layers:
        columns = st.columns([3, 1, 1, 1], vertical_alignment="bottom")
        with columns[0]:
            selected_value = sst.layers[sst.selected_id]
            st.markdown(f"**{selected_value['value']}**")
            selected_mode = st.segmented_control(label="Modus", options=["Manual", "AI"], default=sst.selected_mode)
            if selected_mode != sst.selected_mode:
                sst.selected_mode = selected_mode
                st.rerun()
            if selected_mode == "Manual":
                manual_creation_view()
            elif selected_mode == "AI":
                generate_child_nodes_view(selected_value)
        with columns[2]:
            if st.button("Knoten und dessen Unterknoten löschen", disabled=sst.selected_id == sst.root_node_id):
                st.write("Delete")
                delete_node(sst.selected_id)
                clean_dangling()
                st.write(sst.layers)
                sst.selected_id = None
                sst.update_idea_graph = True
                st.rerun()
        st.divider()
        st.subheader("Abschließen")
        if st.button("Ausgewählte Idee übernehmen"):
            selected_value = sst.layers[sst.selected_id]
            return selected_value["value"]
    else:
        st.write("Kein Element ausgewählt")


def manual_creation_view():
    manual_entry = st.text_input("Eintrag")
    if st.button("Hinzufügen", type="primary", key="ManualOK", disabled=str(manual_entry).strip() == ""):
        append_child(sst.selected_id, manual_entry)
        sst.update_idea_graph = True
        st.rerun()


def generate_child_nodes_view(selected_value):
    used_prompt = load_prompt("idea_generation")
    schema = load_schema("generic_schema")
    with st.expander("Prompt ansehen"):
        st.markdown(used_prompt)
    with st.expander("Schema ansehen"):
        st.json(schema)
    if st.button("Generate", type="primary"):
        element_value = selected_value["value"]
        with st.spinner("Processing..."):
            used_prompt += f"\nDie Idee, die zerlegt werden soll ist: {element_value}"
            response = make_request_structured(prompt_text=used_prompt, json_schema=schema)
            response_dict = json.loads(response)
            selected_values = response_dict["points"][0:5]
            selected_values = list(set(selected_values))
            for generated_value in selected_values:
                append_child(sst.selected_id, generated_value)
        sst.update_idea_graph = True
        st.rerun()


if __name__ == '__main__':
    init_page()
    idea_generation_view()
