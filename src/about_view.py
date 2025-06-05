import streamlit as st
import os
from datetime import datetime

def about_view():
    st.title("Welcome to Innovation Navigator")
    st.markdown(
        """
        ### Your Intelligent Innovation Companion
        
        Innovation Navigator empowers teams to transform ideas into impactful solutions using AI-guided 
        frameworks and proven innovation methodologies. Our platform combines strategic thinking tools 
        with artificial intelligence to help you navigate every step of your innovation journey.
        """
    )

    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Available Templates")
        st.markdown(
            """
            📌 **Strategy & Analysis**
            - Strategic Foundation
            - PESTEL Analysis
            - SWOT Analysis
            - Trend Radar
            
            🎯 **User Understanding**
            - Customer Persona Creation
            - Empathy Mapping
            - Jobs-to-be-Done Analysis
            
            💡 **Innovation Process**
            - Structured Ideation
            - Idea Evaluation (DFVS Framework)
            - Value Proposition Canvas
            - Business Model Canvas
            - Product Concept Testing
            """
        )
    
    with col2:
        st.markdown("### AI-Powered Features")
        st.markdown(
            """
            - 🧠 **Intelligent Guidance**
                Generate creative solutions and insights using advanced AI

            - 📊 **Framework Integration**
                Seamlessly connect insights across multiple innovation tools
            
            - 🔄 **Iterative Development**
                Test and refine ideas with structured experiments
            
            - 📈 **Progress Tracking**
                Monitor your innovation journey with visual progress indicators
            
            - 🤝 **Collaboration Support**
                Share and iterate on ideas with your team
            
            - 📱 **Product Visualization**
                Generate and visualize product concepts
            """
        )

    st.divider()
    
    # Important Notes section
    st.markdown("### Getting Started")
    st.info(
        """
        1. Click **Start** in the sidebar to create a new innovation project
        2. Define your challenge and target audience
        3. Follow the suggested templates in sequence
        4. Use AI assistance to generate insights and ideas
        5. Iterate and refine based on feedback and learnings
        """
    )

    if st.button("Create New Project", type="primary", use_container_width=True):
        from streamlit_modular import sst
        sst.selected_template_name = "Start"
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()    # Research Project Information
    st.markdown("---")
    st.markdown("""
        ### About This Project
        
        Innovation Navigator was developed as a master thesis research project at the 
        [University of Applied Sciences Upper Austria](https://fh-ooe.at/) by:
        
        - **Paul Scheichl** - AI & Innovation Research
        - **Martin Hanreich** - Innovation Process Design
        
        This tool represents the culmination of research in AI-assisted innovation methodologies, 
        combining proven frameworks with state-of-the-art artificial intelligence to create 
        a guided innovation experience.
        
        <div style='text-align: center; margin-top: 20px;'>
            <img src="https://www.fh-ooe.at/fileadmin/user_upload/responsive-images/logo_fhooe_projektil_RGB_positiv.png" width="200">
        </div>
        
        <div style='text-align: center; color: #666; margin-top: 20px;'>
        Version 1.0 Beta | Research Contact: paul.scheichl@gmail.com
        </div>
        """,
        unsafe_allow_html=True
    )
