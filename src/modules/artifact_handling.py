import os
import io
from PIL import Image
from streamlit import session_state as sst
from .state import update_data_store

def add_artifact(toggle_key, element_name, artifact_id, artifact):
    widget_state = sst[toggle_key]
    artifacts_dict = sst.confirmed_artifacts[element_name]
    if widget_state:
        artifacts_dict[artifact_id] = artifact
    else:
        artifacts_dict.pop(artifact_id, None)
    sst.confirmed_artifacts[element_name] = artifacts_dict

def add_to_generated_artifacts(element_name, values):
    artifacts_dict = {}
    if not isinstance(values, list):
        values = [values]
    for i, value in enumerate(values):
        artifacts_dict[i] = value
    sst.generated_artifacts[element_name] = artifacts_dict
    sst.confirmed_artifacts[element_name] = {}

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

def add_image_to_image_store(element_selected, element_store, image):
    directory_path = './stores/image_store'
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)
    image = Image.open(image)
    filename = element_selected + "_" + sst.project_name + '.jpg'
    full_path = os.path.join(directory_path, filename)
    image.save(full_path)
    element_store[element_selected] = [full_path]

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
    
    for i, (artifact, artifact_key) in enumerate(zip(all_artifacts, artifact_keys)):
        with st.container():
            columns = st.columns([0.2, 2.5, 0.2, 1], gap="small")
            with columns[1]:
                if isinstance(artifact, str) and artifact.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    st.image(artifact, use_container_width=True)
                elif hasattr(artifact, 'getvalue') and callable(artifact.getvalue):
                    st.image(artifact, use_container_width=True)
                else:
                    st.markdown(str(artifact))
            with columns[3]:
                is_assigned = artifact in assigned
                toggled = st.toggle("Add", value=is_assigned, key=f"toggle_{element_name}_{artifact_key}")
                if toggled and not is_assigned:
                    if hasattr(artifact, 'getvalue') and callable(artifact.getvalue):
                        import hashlib
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