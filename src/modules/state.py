import json
import os
from streamlit import session_state as sst

data_store_path = os.path.join("stores", "data_stores")

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

def load_json_dictionary(path):
    with open(path, "r", encoding="utf-8") as f:
        loaded_dictionary = json.load(f)
    return loaded_dictionary

def get_full_data_store_path():
    store_name = f"data_store_{sst.project_name}.json"
    return os.path.join(data_store_path, store_name)

def update_data_store():
    # Synchronize shared elements before saving
    from utils import synchronize_shared_elements
    synchronize_shared_elements(sst.data_store, sst.elements_config, sst.template_config)
    
    # Fix: Remove any BytesIO objects before saving
    for template, element_store in sst.data_store.items():
        for element, values in element_store.items():
            if isinstance(values, list):
                filtered = []
                for v in values:
                    if hasattr(v, 'getvalue') and callable(v.getvalue):
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
                print(f"Element config of {element} referenced from template {template_name} not found in the element config!")
        sst.data_store[template_name] = element_store
    update_data_store() 