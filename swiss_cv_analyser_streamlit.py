import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap
import re

# --- Configuration ---
APP_PASSWORD = "swisscareer"
MAX_CHUNK_SIZE = 10000 

# --- Page Config ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭")

# --- API Key from Streamlit Secrets ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError:
    st.error("Error: GEMINI_API_KEY not found in Streamlit Secrets.")
    st.info("Please add GEMINI_API_KEY to your secrets.toml or Streamlit Cloud settings.")
    st.stop()

# --- Model Discovery ---
@st.cache_resource
def get_best_model():
    """Finds the best available model for your specific API key."""
    # Priority list for 2026 standards
    MODEL_PRIORITY = [
        "gemini-3-flash", 
        "gemini-3-flash-preview", 
        "gemini-2.5-flash", 
        "gemini-2.0-flash",
        "gemini-1.5-flash-latest"
    ]
    try:
        available_models = [m.name.split('/')[-1] for m in genai.list_models() 
                           if 'generateContent' in m.supported_generation_methods]
        
        for model_name in MODEL_PRIORITY:
            if model_name in available_models:
                return genai.GenerativeModel(model_name)
        
        return genai.GenerativeModel(available_models[0])
    except Exception as e:
        st.error(f"Could not connect to Gemini API: {e}")
        st.stop()

model_instance = get_best_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"PDF Extraction Error: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    try:
        response = model_instance.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"\n[Model Error: {str(e)}]\n"

def run_analysis(cv_text, jd_text):
    cv_chunks = wrap(cv_text, MAX_CHUNK_SIZE)
    jd_chunks = wrap(jd_text, MAX_CHUNK_SIZE) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    progress = st.progress(0, text="Recruiter is analyzing your profile...")

    # Summarize CV
    for i, chunk in enumerate(cv_chunks):
        cv_summary += call_gemini(f"Summarise this CV for a Swiss Life Sciences role:\n\n{chunk}") + "\n"
        progress.progress((i + 0.5) / (len(cv_chunks) + max(len(jd_chunks), 1)))

    # Summarize JD
    for i, chunk in enumerate(jd_chunks):
        jd_summary += call_gemini(f"Summarise this Job Description:\n\n{chunk}") + "\n"
        progress.progress((len(cv_chunks) + i + 1) / (len(cv_chunks) + len(jd_chunks)))

    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter (Basel/Zurich/Zug hubs).
    Analyse this CV against Swiss standards and the Job Description.
    
    REQUIRED HEADERS:
    1. **Swiss Market Fit** (Photo presence, Nationality/Work Permit info, Language levels A1-C2)
    2. **Technical Gap Analysis** (Specific keyword discrepancies)
    3. **Seniority & Salary Alignment** (Swiss industry standard alignment)
    4. **ATS & Visibility Optimization**
    5. **Priority Checklist** (Top 3 immediate improvements)

    CV SUMMARY: {cv_summary}
    JD SUMMARY: {jd_summary if jd_summary else "General Swiss Life Sciences Market Standard"}
    """
    
    result = call_gemini(final_prompt)
    progress.empty()
    return result

# --- UI ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")
st.sidebar.caption(f"Connected to: {model_instance.model_name}")

# App Password Protection
pass_input = st.text_input("Enter App Password", type="password")
if pass_input != APP_PASSWORD:
    if pass_input: st.error("Incorrect Password")
    st.stop()

# Uploads
col1, col2 = st.columns(2)
with col1:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
with col2:
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])

jd_manual = st.text_area("Or paste Job Description text here")

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Could not read CV. Check if the file is empty or scanned as an image.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                st.divider()
                st.subheader("Professional Recruiter Feedback")
                st.markdown(report)
                st.download_button("Download Report", report, "Swiss_CV_Analysis.txt")
