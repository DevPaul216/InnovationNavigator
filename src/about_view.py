import streamlit as st

def about_view():
    st.title("Welcome to Innovation Navigator.")
    st.markdown(
        """
        ## Your AI-Powered Guide for Innovation
        
        **Innovation Navigator** is a digital platform that empowers teams and individuals to turn ideas into impactful solutions. It combines proven innovation frameworks with advanced AI to guide you through every step of the innovation journey—making the process more structured, creative, and effective.
        """
    )


    st.markdown(
        """
        ### What is Innovation Navigator?
        
        Innovation Navigator was developed as a master thesis research project at the [University of Applied Sciences Upper Austria](https://fh-ooe.at/). It is designed for anyone who wants to innovate—whether you are an entrepreneur, product manager, student, or part of a corporate team.
        
        The tool is based on the double diamond innovation process, supporting both divergent (exploring problems and ideas) and convergent (focusing and validating solutions) phases. It provides a clear, step-by-step structure while allowing flexibility and creativity.
        """
    )

    st.divider()
    st.markdown(
        """
        ### How Does It Work?
        
        1. **Start a New Project**: Define your challenge and target audience.
        2. **Follow the Guided Templates**: Move through a curated sequence of templates:
            - **Strategy & Analysis**: Strategic Foundation, PESTEL, SWOT, Trend Radar
            - **User Understanding**: Personas, Empathy Maps, Jobs-to-be-Done
            - **Ideation**: Structured brainstorming, ABC method, lateral thinking
            - **Idea Evaluation**: DFVS (Desirability, Feasibility, Viability, Sustainability)
            - **Value Proposition & Business Model**: Canvas tools, product concept
            - **Experimentation & Feedback**: Test cards, user feedback, learnings
        3. **Leverage AI at Every Step**: Use AI to generate insights, reframe problems, suggest ideas, and evaluate concepts.
        4. **Visualize and Track Progress**: All your work is visually organized and connected, helping you see the big picture and track your journey.
        """
    )

    st.divider()
    st.markdown(
        """
        ### Key Features
        - 🧠 **AI Guidance**: Get creative suggestions, insights, and evaluations powered by advanced AI.
        - 📊 **Framework Integration**: Seamlessly connect insights across multiple innovation tools.
        - 🔄 **Iterative Development**: Test and refine ideas with structured experiments.
        - 📈 **Progress Tracking**: Monitor your journey with visual indicators.
        - 🤝 **Collaboration Support**: Share and iterate on ideas with your team.
        - 📱 **Product Visualization**: Generate and visualize product concepts.
        """
    )

    st.divider()
    st.markdown(
        """
        ### Who Is It For?
        - Innovation managers and product teams
        - Entrepreneurs and startups
        - Students and educators
        - Anyone seeking a structured, creative approach to innovation
        """
    )

    st.divider()
    st.markdown(
        """
        ### Getting Started
        1. Click **Create new Project** below or **Project** in the sidebar to create a new innovation project.
        2. Define your challenge and target audience.
        3. Follow the suggested templates in sequence.
        4. Use AI to generate insights and ideas.
        5. Iterate and refine based on feedback and learnings.
        """
    )

    if st.button("Create New Project", type="primary", use_container_width=True):
        from streamlit_modular import sst
        sst.selected_template_name = "Start"
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()

    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; margin-top: 20px;'>
        Version 1.0 Beta | Research Contact: paul.scheichl@gmail.com
        </div>
        """,
        unsafe_allow_html=True
    )
