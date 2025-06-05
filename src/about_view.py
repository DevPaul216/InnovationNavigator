import streamlit as st
import os
from datetime import datetime

def about_view():
    st.title("Welcome")
    st.markdown(
        "<h2 style='font-size:18px;'>Brrrrr Welcome to the Innovation Navigator — an experimental tool that helps innovators tackle real-world challenges by designing impactful products and business models. <br> Based on the Double Diamond framework, this tool guides you through a structured innovation journey using step-by-step templates tailored to each stage. <br> To begin, click the Start box on the far left to create a new project, or choose an existing one. Work through each template in sequence — complete one step to unlock the next, and keep moving forward on your innovation path!",
        unsafe_allow_html=True)
    # Add disclaimer
    st.markdown("---")
    st.markdown("# **Disclaimer - Read before use**")
    
    st.markdown("---")
    st.markdown("## **1. Experimental Nature**")
    st.markdown(
        "The Innovation Navigator is a **prototype tool currently under active development**. It is provided on an “as-is” and “as-available” basis and may include:"
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
        from streamlit_modular import sst
        sst.selected_template_name = "Start"  # Set to "start" to open the project creation screen
        sst.current_view = "detail"
        sst.sidebar_state = "expanded"
        sst.update_graph = True
        st.rerun()
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
       """
    )
