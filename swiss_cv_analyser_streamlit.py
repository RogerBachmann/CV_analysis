import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- Page Configuration ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭", layout="wide")

# --- API & Password Setup ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Missing Secret: {e}")
    st.stop()

@st.cache_resource
def get_working_model():
    """Dynamically finds an available model to prevent 404 errors."""
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # Prioritize flash for speed/reliability
                if "flash" in m.name:
                    return genai.GenerativeModel(m.name)
        # Fallback to a hardcoded string if list fails
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception:
        return genai.GenerativeModel("gemini-1.5-flash")

model_instance = get_working_model()

# --- Helper Functions ---
def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return text.strip()
    except Exception as e:
        return f"ERROR_PDF: {str(e)}"

def call_gemini(prompt):
    try:
        response = model_instance.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        return "AI ERROR: Empty response from model."
    except Exception as e:
        return f"AI ERROR: {str(e)}"

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text, re.DOTALL | re.IGNORECASE)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:\s*(READY|IMPROVE|MAJOR)", report_text, re.IGNORECASE)
        category = cat_match.group(1).upper() if cat_match else "IMPROVE"

        # Content Cleaning (Remove Metadata and Markdown Bolding)
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text, flags=re.DOTALL)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "")

        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n')
                continue
            
            if line.startswith('###'):
                # Header: 13pt (Size 26), Blue (2F5496), No Bold
                header_text = line.replace('#', '').strip()
                rt.add('\n' + header_text + '\n', font='Calibri', size=26, color='2F5496', bold=False)
            else:
                # Body: 12pt (Size 24), Black (000000), No Bold
                rt.add(line + '\n', font='Calibri', size=24, color='000000', bold=False)

        context = {
            'CANDIDATE_NAME': candidate_name.upper(),
            'REPORT_CONTENT': rt,
            'REC_READY': "✅" if category == "READY" else "⬜",
            'REC_IMPROVE': "✅" if category == "IMPROVE" else "⬜",
            'REC_MAJOR': "✅" if category == "MAJOR" else "⬜",
        }
        doc.render(context)
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return bio
    except Exception as e:
        st.error(f"Formatting Error: {e}")
        return None

# --- UI Interface ---
st.title("🇨🇭 Swiss CV Analyser")

# Persist data using Session State
if "final_report" not in st.session_state:
    st.session_state.final_report = None
if "word_bytes" not in st.session_state:
    st.session_state.word_bytes = None

pass_input = st.sidebar.text_input("Password", type="password")

if pass_input == APP_PASSWORD:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
    jd_manual = st.text_area("Or Paste JD Text")

    if st.button("🚀 Run Analysis"):
        if cv_file:
            with st.spinner("Processing Analysis..."):
                cv_text = extract_pdf_text(cv_file)
                jd_text = extract_pdf_text(jd_file) if jd_file else jd_manual
                
                if "ERROR_PDF" in cv_text:
                    st.error(cv_text)
                else:
                    prompt = f"""
                    You are a Senior Swiss Recruiter. Analyze this CV.
                    
                    NAME_START: [Candidate Name] NAME_END
                    CATEGORY: [READY, IMPROVE, or MAJOR]

                    ### 1. PERFORMANCE SCORECARD
                    [Score]/100 - Brief overview.

                    ### 2. SWISS COMPLIANCE
                    [Audit formatting]

                    ### 3. TECHNICAL ALIGNMENT
                    [Skills match]

                    ### 4. ACTION PLAN
                    [Improvement steps]

                    INSTRUCTIONS: No bold (**). Use ### for headers.
                    
                    CV: {cv_text[:12000]}
                    JD: {jd_text[:4000] if jd_text else "Swiss Industry Standards"}
                    """
                    
                    analysis_result = call_gemini(prompt)
                    st.session_state.final_report = analysis_result
                    st.session_state.word_bytes = create_word_report(analysis_result)
        else:
            st.warning("Please upload a CV.")

    # Show results
    if st.session_state.final_report:
        st.divider()
        if "AI ERROR" in st.session_state.final_report:
            st.error(st.session_state.final_report)
        else:
            # Clean UI preview (removing metadata tags)
            display_text = re.sub(r"NAME_START:.*?NAME_END", "", st.session_state.final_report, flags=re.DOTALL)
            display_text = re.sub(r"CATEGORY:.*?\n", "", display_text)
            st.markdown(display_text)
            
            if st.session_state.word_bytes:
                st.download_button(
                    label="📩 Download Report",
                    data=st.session_state.word_bytes,
                    file_name="Swiss_CV_Audit.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
else:
    st.info("Authentication required.")
