import streamlit as st
import json
import os

MODULE_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.abspath(os.path.join(MODULE_PATH, '../module_files'))
TEMPLATES_PATH = os.path.join(CONFIG_DIR, 'templates_config.json')
ELEMENTS_PATH = os.path.join(CONFIG_DIR, 'elements_config.json')

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    st.title('Config Editor: Templates & Elements')
    st.markdown('View, edit, and expand your process configuration files.')

    # Use session state to persist selected tab and selection
    if 'config_tab' not in st.session_state:
        st.session_state['config_tab'] = 0
    if 'selected_template' not in st.session_state:
        st.session_state['selected_template'] = None
    if 'selected_element' not in st.session_state:
        st.session_state['selected_element'] = None

    # Load configs
    templates = load_json(TEMPLATES_PATH)
    elements = load_json(ELEMENTS_PATH)

    tab1, tab2, tab3 = st.tabs(["Templates", "Elements", "Process Flow"])

    with tab1:
        st.header('Templates')
        template_keys = list(templates.keys())
        selected_template = st.selectbox('Select template', template_keys, key='template_select',
                                         index=template_keys.index(st.session_state['selected_template']) if st.session_state['selected_template'] in template_keys else 0)
        st.session_state['selected_template'] = selected_template
        if selected_template:
            template_data = templates[selected_template]
            st.subheader('Current Template Data')
            st.json(template_data)
            st.markdown('**Edit as raw JSON (advanced):**')
            template_json = st.text_area('Edit template JSON', value=json.dumps(template_data, indent=2), height=300, key=f'template_json_{selected_template}')
            if st.button('Save Template Changes', key=f'save_template_{selected_template}'):
                try:
                    new_data = json.loads(template_json)
                    templates[selected_template] = new_data
                    save_json(TEMPLATES_PATH, templates)
                    st.success('Template updated!')
                except Exception as e:
                    st.error(f'Invalid JSON: {e}')
        st.markdown('---')
        new_name = st.text_input('New template key', key='new_template_key')
        if st.button('Add New Template', key='add_new_template'):
            if new_name and new_name not in templates:
                templates[new_name] = {}
                save_json(TEMPLATES_PATH, templates)
                st.session_state['selected_template'] = new_name
                st.experimental_rerun()

    with tab2:
        st.header('Elements')
        element_keys = list(elements.keys())
        selected_element = st.selectbox('Select element', element_keys, key='element_select',
                                        index=element_keys.index(st.session_state['selected_element']) if st.session_state['selected_element'] in element_keys else 0)
        st.session_state['selected_element'] = selected_element
        if selected_element:
            element_data = elements[selected_element]
            st.subheader('Current Element Data')
            st.json(element_data)
            st.markdown('**Edit as raw JSON (advanced):**')
            element_json = st.text_area('Edit element JSON', value=json.dumps(element_data, indent=2), height=300, key=f'element_json_{selected_element}')
            if st.button('Save Element Changes', key=f'save_element_{selected_element}'):
                try:
                    new_data = json.loads(element_json)
                    elements[selected_element] = new_data
                    save_json(ELEMENTS_PATH, elements)
                    st.success('Element updated!')
                except Exception as e:
                    st.error(f'Invalid JSON: {e}')
        st.markdown('---')
        new_elem_name = st.text_input('New element key', key='new_element_key')
        if st.button('Add New Element', key='add_new_element'):
            if new_elem_name and new_elem_name not in elements:
                elements[new_elem_name] = {}
                save_json(ELEMENTS_PATH, elements)
                st.session_state['selected_element'] = new_elem_name
                st.experimental_rerun()

    with tab3:
        st.header('Process Flow')
        st.markdown('Visualize and edit the process assembled from templates.')
        try:
            from streamlit_flow import streamlit_flow
            from streamlit_flow.layouts import LayeredLayout
            from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
            from streamlit_flow.state import StreamlitFlowState
            # Prepare nodes and edges
            nodes = []
            edges = []
            for t_key, t_val in templates.items():
                nodes.append(StreamlitFlowNode(
                    id=t_key,
                    pos=(0, 0),
                    data={'content': t_val.get('display_name', t_key)},
                    node_type="default",
                    draggable=True,
                    focusable=False,
                    source_position="right",
                    target_position="left",
                    style={"width": "120px", "padding": "2px"}
                ))
                for conn in t_val.get('connects', []):
                    if isinstance(conn, str) and ',' in conn:
                        for c in conn.split(','):
                            edges.append(StreamlitFlowEdge(f'{t_key}-{c.strip()}', t_key, c.strip(), marker_end={'type': 'arrowclosed'}))
                    else:
                        edges.append(StreamlitFlowEdge(f'{t_key}-{conn}', t_key, conn, marker_end={'type': 'arrowclosed'}))
            flow_state = StreamlitFlowState(nodes, edges)
            streamlit_flow(
                key="config_editor_flow",
                state=flow_state,
                height=800,
                layout=LayeredLayout(direction="right"),
                fit_view=True,
                get_node_on_click=False,
                get_edge_on_click=False,
                show_controls=True,
                allow_zoom=True,
                pan_on_drag=True,
            )
        except ImportError:
            st.warning('streamlit_flow is not installed. Please install it to view the process flow.')
        st.info('To edit the process, modify the "connects" field in the Templates tab.')

if __name__ == '__main__':
    main()
