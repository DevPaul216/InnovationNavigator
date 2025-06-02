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

    # Load configs
    templates = load_json(TEMPLATES_PATH)
    elements = load_json(ELEMENTS_PATH)

    tab1, tab2, tab3 = st.tabs(["Templates", "Elements", "Process Flow"])

    with tab1:
        st.header('Templates')
        selected_template = st.selectbox('Select template', list(templates.keys()))
        template_data = templates[selected_template]
        st.subheader('Current Template Data')
        st.json(template_data)
        st.markdown('**Edit as raw JSON (advanced):**')
        template_json = st.text_area('Edit template JSON', value=json.dumps(template_data, indent=2), height=300, key='template_json')
        if st.button('Save Template Changes'):
            try:
                new_data = json.loads(template_json)
                templates[selected_template] = new_data
                save_json(TEMPLATES_PATH, templates)
                st.success('Template updated!')
            except Exception as e:
                st.error(f'Invalid JSON: {e}')
        st.markdown('---')
        new_name = st.text_input('New template key')
        if st.button('Add New Template'):
            if new_name and new_name not in templates:
                templates[new_name] = {}
                save_json(TEMPLATES_PATH, templates)
                st.experimental_rerun()

    with tab2:
        st.header('Elements')
        selected_element = st.selectbox('Select element', list(elements.keys()))
        element_data = elements[selected_element]
        st.subheader('Current Element Data')
        st.json(element_data)
        st.markdown('**Edit as raw JSON (advanced):**')
        element_json = st.text_area('Edit element JSON', value=json.dumps(element_data, indent=2), height=300, key='element_json')
        if st.button('Save Element Changes'):
            try:
                new_data = json.loads(element_json)
                elements[selected_element] = new_data
                save_json(ELEMENTS_PATH, elements)
                st.success('Element updated!')
            except Exception as e:
                st.error(f'Invalid JSON: {e}')
        st.markdown('---')
        new_elem_name = st.text_input('New element key')
        if st.button('Add New Element'):
            if new_elem_name and new_elem_name not in elements:
                elements[new_elem_name] = {}
                save_json(ELEMENTS_PATH, elements)
                st.experimental_rerun()

    with tab3:
        st.header('Process Flow')
        st.markdown('Visualize and edit the process assembled from templates.')
        import graphviz
        dot = graphviz.Digraph()
        for t_key, t_val in templates.items():
            dot.node(t_key, t_val.get('display_name', t_key))
            for conn in t_val.get('connects', []):
                # Handle comma-separated connects
                if isinstance(conn, str) and ',' in conn:
                    for c in conn.split(','):
                        dot.edge(t_key, c.strip())
                else:
                    dot.edge(t_key, conn)
        st.graphviz_chart(dot)
        st.info('To edit the process, modify the "connects" field in the Templates tab.')

if __name__ == '__main__':
    main()
