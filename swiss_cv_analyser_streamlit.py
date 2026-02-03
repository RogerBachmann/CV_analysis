import os
import streamlit as st
import pdfplumber
import google.generativeai as genai
from datetime import datetime
from io import BytesIO

# ============================
# CONFIG
# ============================

APP_PASSWORD = "swisscareer"   # change later

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in environment variables")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ============================
# HELPERS
# ============================

def extract_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(BytesIO(uploaded_file.read())) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"
    return text


def build_prompt(cv_text, jd_text=None):

    base_prompt = f"""
You are a Swiss Life Sciences recruitment expert.

Analyse this CV strictly against Swiss market standards.

Focus on:
- structure and formatting
- industry readiness
- keyword optimisation for recruiter search
- seniority positioning
- quantified impact
- academic vs industry language
- risks of overqualification
- clarity of role scope

Return a structured professional report with:

1. Executive Summary
2. Structure & Formatting
3. Content Quality
4. Keyword & Searchability
5. Swiss Market Fit
6. Concrete Improvement Actions

CV CONTENT:
----------------
{cv_text}
"""

    if jd_text:
        base_prompt += f"""

JOB DESCRIPTION:
----------------
{jd_text}

Also include:
- Match analysis
- Missing keywords
- Suggested job title optimisation
"""

    return base_prompt


def run_analysis(cv_text, jd_text=None):

    prompt = build_prompt(cv_text, jd_text)

    response = model.generate_content(prompt)

    return response.text


def save_report(text):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Swiss_CV_Analysis_{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)

    return filename


# ============================
# STREAMLIT UI
# ============================

st.set_page_config(page_title="Swiss CV Analyser", layout="centered")

st.title("Swiss CV & Market Fit Analyser")

# ---- Password Gate ----

password = st.text_input("Enter access password", type="password")

if password != APP_PASSWORD:
    st.warning("Access restricted")
    st.stop()

st.success("Access granted")

# ---- Uploads ----

st.subheader("Upload CV (PDF)")

cv_file = st.file_uploader("CV PDF", type=["pdf"])

st.subheader("Optional: Upload Job Description (PDF)")

jd_file = st.file_uploader("Job Description PDF", type=["pdf"])

st.subheader("Or paste Job Description text")

jd_text_manual = st.text_area("Job Description text", height=150)

# ---- Analyse Button ----

if st.button("Run Swiss Market Analysis"):

    if not cv_file:
        st.error("Please upload a CV PDF")
        st.stop()

    with st.spinner("Extracting CV..."):
        cv_text = extract_pdf_text(cv_file)

    jd_text = None

    if jd_file:
        with st.spinner("Extracting Job Description..."):
            jd_text = extract_pdf_text(jd_file)

    elif jd_text_manual.strip():
        jd_text = jd_text_manual

    with st.spinner("Running AI analysis..."):
        result = run_analysis(cv_text, jd_text)

    filename = save_report(result)

    st.success("Analysis completed")

    st.subheader("Preview")

    st.text_area("Analysis Report", result, height=400)

    with open(filename, "rb") as f:
        st.download_button(
            label="Download Report (.txt)",
            data=f,
            file_name=filename,
            mime="text/plain"
        )

