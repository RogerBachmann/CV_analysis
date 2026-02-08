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
    st.error(f"Secret {e} not found in Streamlit Secrets.")
    st.stop()
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.stop()

@st.cache_resource
def get_best_model():
    try:
        # Standard fallback logic for model availability
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ["models/gemini-1.5-flash", "models/gemini-pro"]
        for p in priority:
            if p in available_models: return genai.GenerativeModel(p)
        return genai.GenerativeModel(available_models[0])
    except Exception:
        return genai.GenerativeModel("models/gemini-1.5-flash")

model_instance = get_best_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
    # Remove non-printable characters and collapse whitespace
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception:
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e): # Handle Rate Limiting
                time.sleep(5)
                continue
            return ""
    return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction (Using robust regex)
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text, re.DOTALL)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # 2. Body Cleaning
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text, flags=re.DOTALL)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        # Scrub all markdown bold/italic markers
        clean_body = clean_body.replace("**", "").replace("__", "").replace("*", "").strip()

        # 3. Build RichText for Word
        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line_content = line.strip()
            
            if not line_content:
                # Force a plain newline that breaks any style chain
                rt.add('\n', font='Calibri', size=24, bold=False, italic=False)
                continue
            
            if line_content.startswith('###') or line_content.startswith('##'):
                # SUBHEADER: Blue (2F5496), 14pt (Size 28), Explicitly NOT bold
                display_text = line_content.lstrip('#').strip()
                rt.add(display_text, font='Calibri', size=28, color='2F5496', bold=False, italic=False)
                rt.add('\n', font='Calibri', size=28, bold=False)
            else:
                # BODY: Black (000000), 12pt (Size 24), Explicitly NOT bold
                rt.add(line_content, font='Calibri', size=24, color='000000', bold=False, italic=False)
                rt.add('\n', font='Calibri', size=24, bold=False)

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
        st.error(f"Critical Formatting/Word Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    cv_summary = call_gemini(f"Summarize CV: {cv_text[:8000]}")
    jd_summary = call_gemini(f"Summarize JD: {jd_text[:8000]}") if jd_text else "General Life Sciences Standards"

    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate the CV.
    
    METADATA (MANDATORY):
    NAME_START: [Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 

    INSTRUCTIONS: 
    - Use '###' for subheadings.
    - NEVER use bold markdown (**).
    - Provide a direct, professional audit.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Fit: [Score]/100

    ### 2. SWISS COMPLIANCE
    Status: [Review]

    ### 3. TECHNICAL ALIGNMENT
    Mapping: [Mapping]

    ### 4. IMPACT & KPIs
    Evidence: [Metrics]

    ### 5. PRIORITY ACTIONS
    - [Task]

    CV: {cv_summary}
    JD: {jd_summary}
    """
    return call_gemini(final_prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# Authentication
if "APP_PASSWORD" in st.secrets:
    pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
    if pass_input != st.secrets["APP_PASSWORD"]:
        st.info("Please authenticate to continue.")
        st.stop()

# File Uploads
cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload Job Description (PDF)", type=["pdf"])
jd_manual = st.text_area("Or Paste JD Text Here", height=150)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing with Gemini AI..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Failed to read CV content.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                
                # Display Results
                st.divider()
                st.markdown(report)
                
                # Generate Document
                word_file = create_word_report(report)
                if word_file:
                    st.download_button(
                        label="📩 Download Branded Word Report",
                        data=word_file,
                        file_name="Swiss_CV_Audit.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
