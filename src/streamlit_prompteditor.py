import streamlit as st
import os
import json
from typing import Dict, List, Tuple


def load_elements_config() -> Dict:
    """Load the elements configuration to understand prompt relationships."""
    try:
        config_path = os.path.join("module_files", "elements_config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load elements config: {e}")
        return {}


def load_templates_config() -> Dict:
    """Load the templates configuration."""
    try:
        config_path = os.path.join("module_files", "templates_config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load templates config: {e}")
        return {}


def get_prompt_categories(txt_files: List[str], elements_config: Dict) -> Dict[str, List[str]]:
    """Organize prompts by their categories/templates."""
    categories = {
        "Core Generation": [],
        "Import/Utility": [],
        "Business Models": [],
        "Analysis & Research": [],
        "Product & Design": [],
        "Ideas & Innovation": [],
        "Uncategorized": []
    }
    
    # Categorize prompts based on their names and usage
    for file in txt_files:
        base_name = file.replace('.txt', '')
        
        # Check if prompt is used by elements
        used_by_elements = []
        for element_name, element_config in elements_config.items():
            if element_config.get("prompt_name") == base_name or element_config.get("prompt_name_import") == base_name:
                used_by_elements.append(element_name)
        
        # Categorize based on name patterns
        if "import" in base_name.lower() or "generic" in base_name.lower():
            categories["Import/Utility"].append(file)
        elif any(term in base_name.lower() for term in ["businessmodel", "swot", "pestel", "canvas", "strategy"]):
            categories["Business Models"].append(file)
        elif any(term in base_name.lower() for term in ["trends", "empathy", "persona", "research", "feedback"]):
            categories["Analysis & Research"].append(file)
        elif any(term in base_name.lower() for term in ["product", "design", "testcard", "experiment", "image"]):
            categories["Product & Design"].append(file)
        elif any(term in base_name.lower() for term in ["idea", "innovation", "rating", "problem", "solution", "challenge"]):
            categories["Ideas & Innovation"].append(file)
        elif used_by_elements:
            categories["Core Generation"].append(file)
        else:
            categories["Uncategorized"].append(file)
    
    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def get_prompt_info(filename: str, elements_config: Dict) -> Tuple[List[str], str]:
    """Get information about which elements use this prompt and its description."""
    base_name = filename.replace('.txt', '')
    used_by = []
    description = ""
    
    for element_name, element_config in elements_config.items():
        if element_config.get("prompt_name") == base_name:
            used_by.append(f"{element_name} (generation)")
            if not description and element_config.get("description"):
                description = element_config["description"]
        elif element_config.get("prompt_name_import") == base_name:
            used_by.append(f"{element_name} (import)")
    
    return used_by, description


def prompt_editor_view(folder_path):
    # Apply consistent styling from the main app
    st.markdown("""
        <style>
        .prompt-category {
            margin-bottom: 1rem;
        }
        .prompt-item {
            padding: 0.5rem;
            margin: 0.2rem 0;
            border-radius: 0.5rem;
            border: 1px solid rgba(49, 51, 63, 0.2);
            background-color: rgba(240, 242, 246, 0.5);
        }
        .prompt-item:hover {
            background-color: rgba(240, 242, 246, 0.8);
        }
        .selected-prompt {
            background-color: rgba(255, 217, 102, 0.3) !important;
            border-color: #FFD966 !important;
        }
        .stTextArea > div > div > textarea {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        }
        </style>
    """, unsafe_allow_html=True)

    # Header with consistent styling
    st.markdown("""
        <div style='text-align: center; margin-bottom: 2rem;'>
            <h1 style='margin-bottom: 0.1em; font-size:2.7em;'>Prompt Editor</h1>
            <div style='font-size: 1.0em; color: #666; margin-bottom:0.5em;'>Manage and edit AI prompts used throughout the system</div>
        </div>
    """, unsafe_allow_html=True)

    # Load configurations
    elements_config = load_elements_config()
    templates_config = load_templates_config()

    # Get list of .txt files
    try:
        txt_files = [f for f in os.listdir(folder_path) if f.endswith(".txt")]
        txt_files.sort()  # Sort alphabetically
    except Exception as e:
        st.error(f"Could not read prompt folder: {e}")
        return

    # Initialize session state
    if "selected_file" not in st.session_state:
        st.session_state.selected_file = txt_files[0] if txt_files else None
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False

    # Main layout
    col1, col2 = st.columns([1, 2], gap="large")

    with col1:
        with st.container(border=True):
            st.markdown("### 📁 Prompt Library")
            
            if not txt_files:
                st.info("No prompt files found.")
            else:
                # Organize prompts by categories
                categories = get_prompt_categories(txt_files, elements_config)
                
                for category, files in categories.items():
                    if files:
                        with st.expander(f"📂 {category} ({len(files)})", expanded=True):
                            for file in files:
                                used_by, description = get_prompt_info(file, elements_config)
                                
                                # Create a clickable prompt item
                                cols = st.columns([1])
                                with cols[0]:
                                    is_selected = st.session_state.selected_file == file
                                    
                                    if st.button(
                                        f"📄 {file.replace('.txt', '')}",
                                        key=f"select_{file}",
                                        help=f"Used by: {', '.join(used_by) if used_by else 'Not linked'}\n{description[:100] + '...' if len(description) > 100 else description}",
                                        use_container_width=True,
                                        type="primary" if is_selected else "secondary"
                                    ):
                                        st.session_state.selected_file = file
                                        st.session_state.confirm_delete = False
                                        st.rerun()

        # File management section
        with st.container(border=True):
            st.markdown("### ⚙️ File Management")
            
            # Create new file
            st.markdown("**Create New Prompt**")
            new_name = st.text_input(
                "Prompt name (without .txt)",
                key="new_file",
                placeholder="e.g., prompt_newfeature",
                help="Use descriptive names like 'prompt_elementname' for consistency"
            )
            
            col_create, col_clear = st.columns([2, 1])
            with col_create:
                if st.button("➕ Create", use_container_width=True, type="primary"):
                    if not new_name.strip():
                        st.error("Please enter a file name.")
                    else:
                        filename = new_name.strip()
                        if not filename.endswith(".txt"):
                            filename += ".txt"
                        
                        path = os.path.join(folder_path, filename)
                        if os.path.exists(path):
                            st.error("File already exists.")
                        else:
                            try:
                                with open(path, "w", encoding="utf-8") as f:
                                    f.write("# Enter your prompt here\n\n")
                                st.success(f"✅ Created {filename}")
                                st.session_state.selected_file = filename
                                st.session_state.new_file = ""
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to create file: {e}")
            
            with col_clear:
                if st.button("🗑️ Clear", use_container_width=True):
                    st.session_state.new_file = ""
                    st.rerun()

            # Delete file
            if st.session_state.selected_file and txt_files:
                st.markdown("**Delete Current Prompt**")
                used_by, _ = get_prompt_info(st.session_state.selected_file, elements_config)
                
                if used_by:
                    st.warning(f"⚠️ This prompt is used by: {', '.join(used_by)}")
                
                if not st.session_state.confirm_delete:
                    if st.button("🗑️ Delete Prompt", type="secondary", use_container_width=True):
                        st.session_state.confirm_delete = True
                        st.rerun()
                else:
                    st.error(f"⚠️ Confirm deletion of '{st.session_state.selected_file}'?")
                    col_confirm, col_cancel = st.columns([1, 1])
                    with col_confirm:
                        if st.button("✅ Yes, Delete", type="primary", use_container_width=True):
                            try:
                                os.remove(os.path.join(folder_path, st.session_state.selected_file))
                                st.success(f"🗑️ Deleted {st.session_state.selected_file}")
                                # Select next available file
                                remaining_files = [f for f in txt_files if f != st.session_state.selected_file]
                                st.session_state.selected_file = remaining_files[0] if remaining_files else None
                                st.session_state.confirm_delete = False
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to delete file: {e}")
                    with col_cancel:
                        if st.button("❌ Cancel", use_container_width=True):
                            st.session_state.confirm_delete = False
                            st.rerun()

    with col2:
        if st.session_state.selected_file and st.session_state.selected_file in txt_files:
            full_path = os.path.join(folder_path, st.session_state.selected_file)
            
            with st.container(border=True):
                # Header with file info
                used_by, description = get_prompt_info(st.session_state.selected_file, elements_config)
                
                st.markdown(f"### 📝 Editing: `{st.session_state.selected_file}`")
                
                if used_by:
                    st.info(f"🔗 **Used by:** {', '.join(used_by)}")
                
                if description:
                    st.markdown(f"**Purpose:** {description}")
                
                st.divider()
                
                # File content editor
                if os.path.exists(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        # Character count and basic stats
                        char_count = len(content)
                        word_count = len(content.split())
                        line_count = len(content.splitlines())
                        
                        col_stats = st.columns(3)
                        col_stats[0].metric("Characters", char_count)
                        col_stats[1].metric("Words", word_count)
                        col_stats[2].metric("Lines", line_count)

                        # Editor
                        edited = st.text_area(
                            "Prompt Content",
                            value=content,
                            height=600,
                            help="Edit the prompt content. Changes are saved when you click the Save button below.",
                            label_visibility="collapsed"
                        )
                        
                        # Save section
                        col_save, col_preview = st.columns([1, 1])
                        with col_save:
                            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                                try:
                                    with open(full_path, "w", encoding="utf-8") as f:
                                        f.write(edited)
                                    st.success(f"✅ Saved changes to {st.session_state.selected_file}")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed to save file: {e}")
                        
                        with col_preview:
                            if content != edited:
                                st.warning("⚠️ Unsaved changes")
                            else:
                                st.success("✅ Up to date")
                                
                    except Exception as e:
                        st.error(f"Could not read file: {e}")
                else:
                    st.warning(f"⚠️ File `{st.session_state.selected_file}` no longer exists.")
        
        elif txt_files:
            with st.container(border=True):
                st.info("👈 Select a prompt file from the left panel to start editing.")
        else:
            with st.container(border=True):
                st.info("📁 No prompt files found. Create a new one to get started.")
