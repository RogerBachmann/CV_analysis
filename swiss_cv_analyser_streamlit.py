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
    st.error(f"Error: Secret {e} not found.")
    st.stop()

@st.cache_resource
def get_best_model():
    # Using the standard string that works across most environments
    return genai.GenerativeModel("gemini-1.5-flash")

model_instance = get_best_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
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
    except Exception: return ""

def call_gemini_with_retry(prompt, retries=3, delay=8):
    for i in range(retries):
        try:
            response = model_instance.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            return "AI ERROR: Empty response."
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            return f"AI ERROR: {str(e)}"
    return "AI ERROR: Maximum retries reached."

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text, re.DOTALL | re.IGNORECASE)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:\s*(READY|IMPROVE|MAJOR)", report_text, re.IGNORECASE)
        category = cat_match.group(1).upper() if cat_match else "IMPROVE"

        # 2. Body Cleaning (From your working snippet)
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text, flags=re.DOTALL)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").replace("__", "").strip()

        # 3. Build RichText for Word
        rt = RichText()
        lines = clean_body.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                # Add a blank line with regular formatting
                rt.add('\n', font='Calibri', size=24, bold=False)
                continue

            if line.startswith('###') or line.startswith('##'):
                display_text = line.lstrip('#').strip()
                # Subheader: Navy (1D457C), 14pt (Size 28)
                rt.add('\n' + display_text + '\n', font='Calibri', size=28, color='1D457C', bold=False)
            else:
                # Main Body: Pure Black (000000), 12pt (Size 24), NOT BOLD
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

def run_analysis(cv_text, jd_text):
    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    
    METADATA (MANDATORY):
    NAME_START: [Candidate Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 

    INSTRUCTIONS: 
    - Use '###' for subheadings.
    - Do NOT include a main title.
    - Do NOT use ANY bold markdown (** or __).
    - Provide a professional, clean audit.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: [Observation]
    Audit: [Review]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: [Observation]
    Audit: [Review]

    ### 4. EVIDENCE OF IMPACT (KPIs)
    The Fact: [Observation]
    Audit: [Review]

    ### 5. PRIORITY ACTION PLAN
    1. [Task]
    2. [Task]

    CV DATA: {cv_text[:10000]}
    JD DATA: {jd_text[:4000] if jd_text else "General Swiss Standard"}
    """
    return call_gemini_with_retry(final_prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# Session State Persistence
if "report" not in st.session_state: st.session_state.report = None
if "word" not in st.session_state: st.session_state.word = None

pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Authenticate in the sidebar.")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD text manually", height=150)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Generating Audit..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Extraction failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                st.session_state.report = report
                st.session_state.word = create_word_report(report)

# Persistent Display
if st.session_state.report:
    st.divider()
    if "AI ERROR" in st.session_state.report:
        st.error(st.session_state.report)
    else:
        # Clean preview for UI
        preview = re.sub(r"NAME_START:.*?NAME_END", "", st.session_state.report, flags=re.DOTALL)
        preview = re.sub(r"CATEGORY:.*?\n", "", preview)
        st.markdown(preview)
        
        if st.session_state.word:
            st.download_button(
                label="📩 Download Branded Word Report",
                data=st.session_state.word,
                file_name="Swiss_CV_Audit.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
