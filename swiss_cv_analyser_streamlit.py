import os
import re
import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap

# Configuration
APP_PASSWORD = "swisscareer"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in environment variables.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

MAX_CHUNK_SIZE = 4000

def clean_text(text):
    if not text:
        return ""
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

def chunk_text(text):
    if not text:
        return []
    return wrap(text, MAX_CHUNK_SIZE)

def call_gemini(prompt):
    # Check for empty prompt
    if not prompt or not prompt.strip():
        return ""
    try:
        # Pass the string directly rather than a list for simple text
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error calling Gemini: {str(e)}"

def run_analysis(cv_text, jd_text):
    cv_chunks = chunk_text(cv_text)
    jd_chunks = chunk_text(jd_text) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    # Progress bar for better UX
    progress_bar = st.progress(0)
    
    for i, chunk in enumerate(cv_chunks):
        if chunk.strip():
            prompt = f"Summarise this CV content for Swiss Life Sciences hiring:\n\n{chunk}"
            cv_summary += call_gemini(prompt) + "\n"
        progress_bar.progress((i + 1) / (len(cv_chunks) + (len(jd_chunks) or 1)))

    for i, chunk in enumerate(jd_chunks):
        if chunk.strip():
            prompt = f"Summarise this job description:\n\n{chunk}"
            jd_summary += call_gemini(prompt) + "\n"
        # Update progress for JD chunks
        progress_val = (len(cv_chunks) + i + 1) / (len(cv_chunks) + len(jd_chunks))
        progress_bar.progress(min(progress_val, 1.0))

    final_prompt = f"""
You are a senior Swiss Life Sciences recruiter.
Analyse this CV against Swiss standards and the job description.

Focus on:
- Swiss CV structure (e.g., photo requirements, personal details, language levels)
- Keyword gaps
- ATS searchability
- Seniority alignment
- Concrete improvements

CV SUMMARY:
{cv_summary}

JD SUMMARY:
{jd_summary if jd_summary else "No job description provided. Analyse the CV generally for Swiss Life Sciences standards."}
"""
    result = call_gemini(final_prompt)
    progress_bar.empty()
    return result

# --- Streamlit UI ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

password = st.text_input("Password", type="password")

if password != APP_PASSWORD:
    if password:
        st.error("Incorrect password")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF optional)", type=["pdf"])
jd_text_manual = st.text_area("Or paste JD text")

if st.button("Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV first.")
        st.stop()

    with st.spinner("Extracting and analyzing..."):
        cv_text = extract_pdf_text(cv_file)
        
        if jd_file:
            jd_text = extract_pdf_text(jd_file)
        else:
            jd_text = clean_text(jd_text_manual)

        if not cv_text:
            st.error("Could not extract text from CV.")
            st.stop()

        st.info(f"CV Processed: {len(cv_text)} characters")
        
        result = run_analysis(cv_text, jd_text)

        st.subheader("Analysis Results")
        st.markdown(result)
