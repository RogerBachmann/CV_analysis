import os
import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap

# ============================
# CONFIG
# ============================

APP_PASSWORD = "swisscareer"   # change if you want

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in environment variables")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

MAX_CHUNK_SIZE = 6000   # safe for Gemini


# ============================
# HELPERS
# ============================

def extract_pdf_text(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"
    return clean_text(text)


def clean_text(text):
    return " ".join(text.replace("\n", " ").split())


def chunk_text(text, size=MAX_CHUNK_SIZE):
    return wrap(text, size)


def call_gemini(prompt):
    response = model.generate_content(prompt)
    return response.text.strip()


# ============================
# CORE ANALYSIS
# ============================

def run_analysis(cv_text, jd_text):

    cv_chunks = chunk_text(cv_text)
    jd_chunks = chunk_text(jd_text) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    # ---- Summarise CV ----
    for chunk in cv_chunks:
        prompt = f"""
Summarise the following CV content clearly focusing on:
- skills
- experience
- seniority
- life sciences relevance
- Swiss market readiness

TEXT:
{chunk}
"""
        cv_summary += call_gemini(prompt) + "\n"

    # ---- Summarise JD ----
    for chunk in jd_chunks:
        prompt = f"""
Summarise this job description focusing on:
- required skills
- keywords
- seniority
- expectations

TEXT:
{chunk}
"""
        jd_summary += call_gemini(prompt) + "\n"

    # ---- Final Swiss style analysis ----

    final_prompt = f"""
You are a Swiss Life Sciences recruiter.

Analyse this CV against Swiss hiring standards and the job description.

Focus on:

1. Swiss CV structure issues
2. Missing keywords
3. Seniority mismatch
4. Searchability (ATS + LinkedIn logic)
5. Cultural fit for Switzerland
6. Concrete improvement actions

CV SUMMARY:
{cv_summary}

JOB DESCRIPTION SUMMARY:
{jd_summary}

Deliver in clear sections with bullet points.
Be precise and professional.
"""

    return call_gemini(final_prompt)


# ============================
# STREAMLIT UI
# ============================

st.set_page_config(page_title="Swiss CV Analyser", layout="centered")

st.title("Swiss CV & Job Fit Analyser")

# ---- Password gate ----

password = st.text_input("Enter access password", type="password")

if password != APP_PASSWORD:
    st.stop()

st.success("Access granted")

# ---- Uploads ----

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload Job Description (optional PDF)", type=["pdf"])

jd_text_manual = st.text_area("Or paste Job Description text (optional)")

if st.button("Run Analysis"):

    if not cv_file:
        st.warning("Please upload a CV PDF")
        st.stop()

    with st.spinner("Reading CV..."):
        cv_text = extract_pdf_text(cv_file)

    if jd_file:
        with st.spinner("Reading Job Description..."):
            jd_text = extract_pdf_text(jd_file)
    else:
        jd_text = clean_text(jd_text_manual)

    st.info(f"CV characters: {len(cv_text)}")
    st.info(f"JD characters: {len(jd_text)}")

    with st.spinner("Analysing with Swiss market logic..."):
        result = run_analysis(cv_text, jd_text)

    st.subheader("Swiss CV Analysis Result")
    st.write(result)
