import os
import streamlit as st
import pdfplumber
import google.generativeai as genai
from io import BytesIO
from datetime import datetime

# =========================
# SETTINGS
# =========================

APP_PASSWORD = "swisscareer"

MAX_CV_CHARS = 18000
MAX_JD_CHARS = 12000

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in environment variables")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

# =========================
# PDF EXTRACTION
# =========================

def extract_pdf_text(file):

    text = ""

    with pdfplumber.open(BytesIO(file.read())) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                page_text = page_text.replace("\x00", " ")
                page_text = " ".join(page_text.split())
                text += page_text + "\n"

    return text


def clean_and_limit(text, max_chars):
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = " ".join(text.split())

    return text[:max_chars]


# =========================
# PROMPT BUILDER
# =========================

def build_prompt(cv_text, jd_text=None):

    prompt = f"""
You are a senior Swiss Life Sciences recruiter.

Analyse the CV according to Swiss industry standards.

Focus on:

• Structure and formatting
• Industry readiness
• Seniority positioning
• Swiss hiring expectations
• Measurable impact
• Keyword optimisation
• Recruiter red flags

Provide a structured professional report with:

1. Executive summary
2. Formatting & structure
3. Content quality
4. Searchability & keywords
5. Swiss market fit
6. Risks
7. Concrete improvement actions

CV:
----------------
{cv_text}
"""

    if jd_text:
        prompt += f"""

JOB DESCRIPTION:
----------------
{jd_text}

Additionally include:

• Role match evaluation
• Missing critical keywords
• Optimised job titles
• Profile positioning advice
"""

    return prompt


# =========================
# AI ANALYSIS
# =========================

def run_analysis(cv_text, jd_text=None):

    if not cv_text.strip():
        st.error("No CV text extracted. Possibly scanned PDF.")
        st.stop()

    prompt = build_prompt(cv_text, jd_text)

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 2048
        }
    )

    return response.text


# =========================
# SAVE OUTPUT
# =========================

def save_report(text):

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Swiss_CV_Analysis_{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(text)

    return filename


# =========================
# STREAMLIT UI
# =========================

st.set_page_config(page_title="Swiss CV & JD Analyser", layout="centered")

st.title("Swiss CV & Market Fit Analyser")

password = st.text_input("Access password", type="password")

if password != APP_PASSWORD:
    st.warning("Restricted access")
    st.stop()

st.success("Access granted")

st.subheader("Upload CV PDF")
cv_file = st.file_uploader("CV", type=["pdf"], key="cv")

st.subheader("Upload Job Description PDF (optional)")
jd_file = st.file_uploader("Job Description", type=["pdf"], key="jd")

st.subheader("Or paste Job Description text")
jd_manual = st.text_area("Job Description text", height=150)

if st.button("Run Analysis"):

    if not cv_file:
        st.error("Please upload a CV")
        st.stop()

    with st.spinner("Extracting CV..."):
        raw_cv = extract_pdf_text(cv_file)

    cv_text = clean_and_limit(raw_cv, MAX_CV_CHARS)

    jd_text = None

    if jd_file:
        with st.spinner("Extracting JD..."):
            raw_jd = extract_pdf_text(jd_file)
        jd_text = clean_and_limit(raw_jd, MAX_JD_CHARS)

    elif jd_manual.strip():
        jd_text = clean_and_limit(jd_manual, MAX_JD_CHARS)

    st.write("CV characters used:", len(cv_text))
    if jd_text:
        st.write("JD characters used:", len(jd_text))

    with st.spinner("Running Swiss market analysis..."):
        result = run_analysis(cv_text, jd_text)

    filename = save_report(result)

    st.success("Analysis completed")

    st.text_area("Preview", result, height=450)

    with open(filename, "rb") as f:
        st.download_button(
            "Download full report",
            f,
            file_name=filename,
            mime="text/plain"
        )
