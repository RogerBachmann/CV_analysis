import os
import re
import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap


# =============================
# CONFIG
# =============================

APP_PASSWORD = "swisscareer"   # keep or change as you like

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in environment variables")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

MAX_CHUNK_SIZE = 4000


# =============================
# TEXT CLEANING
# =============================

def clean_text(text):
    text = text.encode("utf-8", "ignore").decode()
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_pdf_text(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
    return clean_text(text)


def chunk_text(text):
    return wrap(text, MAX_CHUNK_SIZE)


# =============================
# GEMINI CALL
# =============================

def call_gemini(prompt):
    response = model.generate_content(prompt)
    return response.text.strip()


# =============================
# CORE ANALYSIS
# =============================

def run_analysis(cv_text, jd_text):

    cv_chunks = chunk_text(cv_text)
    jd_chunks = chunk_text(jd_text) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    # ---- CV summarisation ----

    for chunk in cv_chunks:
        prompt = f"""
Summarise the following CV content focusing on:
- professional experience
- technical and scientific skills
- seniority level
- relevance for Swiss Life Sciences market

TEXT:
{chunk}
"""
        cv_summary += call_gemini(prompt) + "\n"

    # ---- JD summarisation ----

    for chunk in jd_chunks:
        prompt = f"""
Summarise the following job description focusing on:
- required competencies
- keywords
- seniority
- expectations

TEXT:
{chunk}
"""
        jd_summary += call_gemini(prompt) + "\n"

    # ---- Final Swiss market analysis ----

    final_prompt = f"""
You are a senior Swiss Life Sciences recruiter.

Analyse the CV against Swiss hiring standards and the job description.

Focus on:

1. Swiss CV structure and formatting issues
2. Missing or weak keywords (ATS + LinkedIn searchability)
3. Seniority alignment
4. Market competitiveness in Switzerland
5. Cultural and communication fit
6. Concrete improvement actions

CV SUMMARY:
{cv_summary}

JOB DESCRIPTION SUMMARY:
{jd_summary}

Provide structured sections with bullet points.
Be precise and professional.
"""

    return call_gemini(final_prompt)


# =============================
# STREAMLIT UI
# =============================

st.set_page_config(page_title="Swiss CV Analyser", layout="centered")

st.title("Swiss CV & Job Fit Analyser")

password = st.text_input("Enter access password", type="password")

if password != APP_PASSWORD:
    st.stop()

st.success("Access granted")

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload Job Description (PDF optional)", type=["pdf"])

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

    with st.spinner("Running Swiss market analysis..."):
        result = run_analysis(cv_text, jd_text)

    st.subheader("Analysis Result")

    st.write(result)
