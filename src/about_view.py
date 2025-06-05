import streamlit as st
import os
from datetime import datetime

def about_view():
    st.title("Welcome to Innovation Navigator")
    st.markdown(
        """
        ### Your Guide to Structured Innovation
        
        Innovation Navigator is a powerful tool designed to help innovators, entrepreneurs, and teams 
        systematically develop impactful solutions. Using the proven Double Diamond framework, 
        we guide you through four key phases:
        
        1. **Discover** - Research and understand your target users and market
        2. **Define** - Frame the right problem to solve
        3. **Develop** - Generate and refine creative solutions
        4. **Deliver** - Test and implement your innovations
        
        Each phase provides structured templates and AI-powered guidance to help you make informed decisions.
        """
    )

    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Getting Started")
        st.markdown(
            """
            1. Click **Start** in the sidebar to create a new project
            2. Choose a template based on your current phase
            3. Fill in the required information
            4. Move through phases as you complete each step
            5. Export or share your results when ready
            """
        )
    
    with col2:
        st.markdown("### Key Features")
        st.markdown(
            """
            - 📋 Step-by-step innovation templates
            - 🤖 AI-powered insights and suggestions
            - 📊 Visual progress tracking
            - 🔄 Iterative development workflow
            - 💾 Automatic progress saving
            - 📤 Export and sharing capabilities
            """
        )

    st.divider()
    
    # Important Notes section
    st.markdown("### Important Notes")
    st.info(
        """
        - This is an experimental tool under active development
        - Your data is processed securely and not retained without consent
        - Always review AI-generated suggestions critically
        - For optimal results, be thorough in providing information
        """
    )

    if st.button("Get Started", type="primary", use_container_width=True):
        from streamlit_modular import sst
        sst.selected_template_name = "Start"
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()

    # Footer with version and contact
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
        Version 1.0 Beta | Contact: innovationnavigator@support.com
        </div>
        """,
        unsafe_allow_html=True
    )
