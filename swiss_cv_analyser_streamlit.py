import os
import re
import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap

# --- Configuration & Security ---
APP_PASSWORD = "swisscareer"
# Use Gemini 3 Flash for the best balance of speed and intelligence in 2026
MODEL_NAME = "gemini-1.5-flash-latest"
MAX_CHUNK_SIZE = 8000  # Gemini 3 handles larger contexts easily

# --- Page Config ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭")

# Sidebar for API Key Management
st.sidebar.title("Settings")
api_key_input = st.sidebar.text_input("Enter Gemini API Key", type="password")
GEMINI_API_KEY = api_key_input or os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.info("Please enter your Gemini API Key in the sidebar or set it as an environment variable.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

# --- Helper Functions ---

def clean_text(text):
    if not text:
        return ""
    # Remove non-printable characters and normalize whitespace
    text = text.encode("utf-8", "ignore").decode()
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip():
        return ""
    try:
        # Direct string call for text generation
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"\n[Model Error: {str(e)}]\n"

def run_analysis(cv_text, jd_text):
    # Split text into manageable chunks
    cv_chunks = wrap(cv_text, MAX_CHUNK_SIZE) if cv_text else []
    jd_chunks = wrap(jd_text, MAX_CHUNK_SIZE) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    progress_bar = st.progress(0, text="Analyzing documents...")
    
    # Process CV
    for i, chunk in enumerate(cv_chunks):
        prompt = f"Summarise this CV content for Swiss Life Sciences hiring:\n\n{chunk}"
        cv_summary += call_gemini(prompt) + "\n"
        progress_bar.progress((i + 1) / (len(cv_chunks) + (len(jd_chunks) or 1)))

    # Process JD
    for i, chunk in enumerate(jd_chunks):
        prompt = f"Summarise this job description:\n\n{chunk}"
        jd_summary += call_gemini(prompt) + "\n"
        # Avoid division by zero if no JD
        total_steps = len(cv_chunks) + len(jd_chunks)
        progress_bar.progress((len(cv_chunks) + i + 1) / total_steps)

    final_prompt = f"""
You are an expert senior Swiss Life Sciences recruiter (specializing in Basel/Zurich hubs).
Analyse the CV against Swiss market standards and the provided job description.

Focus your feedback on:
1. **Swiss CV Standards:** (e.g., Inclusion of photo/DOB/nationality, language proficiency levels A1-C2, and layout).
2. **Technical Gaps:** Keyword discrepancies between CV and JD.
3. **ATS Optimization:** How to improve searchability for internal HR systems.
4. **Cultural Fit:** Swiss work culture alignment (precision, reliability, certifications).
5. **Seniority:** Does the experience match the JD level?

CV SUMMARY:
{cv_summary}

JD SUMMARY:
{jd_summary if jd_summary.strip() else "No JD provided. Provide a general Swiss market analysis."}
"""

    result = call_gemini(final_prompt)
    progress_bar.empty()
    return result

# --- Main UI ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# Simple Password Protection
password = st.text_input("Application Password", type="password")
if password != APP_PASSWORD:
    if password:
        st.error("Incorrect Password")
    st.stop()

# Layout for Uploads
col1, col2 = st.columns(2)
with col1:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
with col2:
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])

jd_text_manual = st.text_area("Or paste JD text here")

if st.button("Run Swiss Market Analysis"):
    if not cv_file:
        st.warning("Please upload a CV to begin.")
        st.stop()

    with st.spinner("Recruiter is reviewing your profile..."):
        cv_content = extract_pdf_text(cv_file)
        
        if jd_file:
            jd_content = extract_pdf_text(jd_file)
        else:
            jd_content = clean_text(jd_text_manual)

        if not cv_content:
            st.error("Could not read CV content. Please ensure the PDF is not password protected.")
            st.stop()

        # Display Stats
        st.caption(f"CV: {len(cv_content)} chars | JD: {len(jd_content)} chars")
        
        # Run Analysis
        analysis_result = run_analysis(cv_content, jd_content)

        # Output
        st.divider()
        st.subheader("Analysis & Recommendations")
        st.markdown(analysis_result)

        # Download button for the report
        st.download_button("Download Report", analysis_result, file_name="Swiss_CV_Analysis.md")
