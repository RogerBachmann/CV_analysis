import os
import re
import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap

# --- Configuration ---
APP_PASSWORD = "swisscareer"
MAX_CHUNK_SIZE = 10000  # Modern Gemini models handle large chunks easily

# --- Streamlit Setup ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭")

st.sidebar.title("Settings")
user_api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

# Priority list for models (2026 Standards)
MODEL_PRIORITY = [
    "gemini-3-flash", 
    "gemini-3-flash-preview", 
    "gemini-2.5-flash", 
    "gemini-2.0-flash",
    "gemini-1.5-flash-latest"
]

def initialize_gemini(api_key):
    """Dynamically finds the best available model for your API key."""
    try:
        genai.configure(api_key=api_key)
        # List all models that support content generation
        available_models = [m.name.split('/')[-1] for m in genai.list_models() 
                           if 'generateContent' in m.supported_generation_methods]
        
        # Pick the best one from our priority list
        for model_name in MODEL_PRIORITY:
            if model_name in available_models:
                return genai.GenerativeModel(model_name)
        
        # Fallback to the first available if none of our favorites exist
        return genai.GenerativeModel(available_models[0])
    except Exception as e:
        st.sidebar.error(f"Initialization Error: {e}")
        return None

# --- Logic Functions ---

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
        st.error(f"PDF Error: {e}")
        return ""

def call_gemini(model, prompt):
    if not prompt.strip(): return ""
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"\n[Analysis Error: {str(e)}]\n"

def run_analysis(model, cv_text, jd_text):
    cv_chunks = wrap(cv_text, MAX_CHUNK_SIZE)
    jd_chunks = wrap(jd_text, MAX_CHUNK_SIZE) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    progress = st.progress(0, text="Recruiter is reading documents...")

    # Summarize CV
    for i, chunk in enumerate(cv_chunks):
        cv_summary += call_gemini(model, f"Summarise this CV for a Swiss Life Sciences role:\n\n{chunk}") + "\n"
        progress.progress((i + 1) / (len(cv_chunks) + (len(jd_chunks) or 1)))

    # Summarize JD
    for i, chunk in enumerate(jd_chunks):
        jd_summary += call_gemini(model, f"Summarise this Job Description:\n\n{chunk}") + "\n"
        progress.progress((len(cv_chunks) + i + 1) / (len(cv_chunks) + len(jd_chunks)))

    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. 
    Compare this CV SUMMARY to the JD SUMMARY and provide a professional gap analysis.
    
    Structure your response using these headers:
    1. **Swiss Market Fit** (Photo, Language levels A1-C2, Certifications)
    2. **Technical & Keyword Gaps** (What is missing from the CV that the JD requires?)
    3. **Seniority & Salary Alignment** (Based on Swiss industry standards)
    4. **ATS & Visibility Tips**
    5. **Actionable Checklist** (Top 3 changes to make now)

    CV SUMMARY: {cv_summary}
    JD SUMMARY: {jd_summary if jd_summary else "General Swiss Life Sciences Market"}
    """
    
    result = call_gemini(model, final_prompt)
    progress.empty()
    return result

# --- UI Layout ---

st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# Authentication
pass_input = st.text_input("Enter App Password", type="password")
if pass_input != APP_PASSWORD:
    if pass_input: st.error("Wrong Password")
    st.stop()

# Key Check
if not user_api_key:
    st.info("Please enter your Gemini API Key in the sidebar to start.")
    st.stop()

# Model Init
model_instance = initialize_gemini(user_api_key)
if model_instance:
    st.sidebar.success(f"Using: {model_instance.model_name}")
else:
    st.stop()

# Files
col1, col2 = st.columns(2)
with col1:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
with col2:
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])

jd_manual = st.text_area("Or paste Job Description text here")

if st.button("🚀 Analyze My Profile"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Could not read CV. Is it empty or scanned as an image?")
            else:
                report = run_analysis(model_instance, cv_raw, jd_raw)
                st.divider()
                st.subheader("Professional Recruiter Feedback")
                st.markdown(report)
                st.download_button("Download Feedback (.txt)", report, "Swiss_CV_Analysis.txt")
