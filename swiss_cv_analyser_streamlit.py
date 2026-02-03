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

# safer stable model
model = genai.GenerativeModel("gemini-1.5-flash")

# ============================
# HELPERS
# ============================

def extract_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(BytesIO(uploaded_file.read())) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def trim_text(text, max_chars=12000):
    return text[:max_chars]


def build_prompt(cv_text, jd_text=None):

    prompt = f"""
You are a senior Swiss Life Sciences recruiter and career strategist.

Analyse the following CV strictly according to Swiss industry hiring standards.

Focus on:

- Structure and formatting quality
- Industry readiness vs academic style
- Seniority positioning
- Searchability and recruiter keyword optimisation
- Quantification of impact
- Role scope clarity
- Swiss market expectations
- Overqualification risks
- Concrete improvement recommendations

Return a structured professional report with:

1. Executive Summary
2. Structure & Formatting
3. Content Quality
4. Keyword & Searchability
5. Swiss Market Fit
6. Main Risks
7. Concrete Actionable Improvements

CV CONTENT:
----------------
{cv_text}
"""

    if jd_text:
        prompt += f"""

JOB DESCRIPTION:
----------------
{jd_text}

Additionally include:

- Role match analysis
- Missing keywords
- Suggested job title optimisation for LinkedIn and ATS
"""

    return prompt


def run_analysis(cv_text, jd_text=None):

    if not cv_text.strip():
        st.error("CV text extraction failed. PDF may be scanned.")
        st.stop()

    cv_text = trim_text(cv_text)

    if jd_text:
        if not jd_text.strip():
            st.error("Job description extraction failed.")
            st.stop()
        jd_text = trim_text(jd_text)

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

# ---- Upload CV ----

st.subheader("Upload CV (PDF)")

cv_file = st.file_uploader("CV PDF", type=["pdf"])

# ---- Upload Job Description ----

st.subheader("Optional. Upload Job Description (PDF)")

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
