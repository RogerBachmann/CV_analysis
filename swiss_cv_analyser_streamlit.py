import os
import streamlit as st
import pdfplumber
import google.generativeai as genai
from datetime import datetime

# =============================
# CONFIG
# =============================

APP_PASSWORD = "swisscv"   # change later

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in environment variables.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# Use stable public model
model = genai.GenerativeModel("models/gemini-1.5-flash")


# =============================
# HELPERS
# =============================

def extract_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def build_prompt(cv_text, jd_text=None):

    base_prompt = f"""
You are a Swiss Life Sciences recruitment expert and ATS optimisation specialist.

Analyse the following CV in detail.

Focus on:
- Swiss market expectations
- ATS searchability
- Keyword density and relevance
- Seniority positioning
- Clear value proposition
- Missing competencies

Provide:

1. Overall CV quality score (0 to 100)
2. Strengths
3. Weaknesses
4. Keyword gaps (expand deeply by skills, tools, domains, titles)
5. Swiss market alignment feedback
6. Concrete improvement suggestions

CV:
{cv_text}
"""

    if jd_text:
        base_prompt += f"""

Additionally compare the CV to this Job Description.

Identify:
- Matching skills
- Missing skills
- Suggested profile positioning
- Recommended keywords and job titles to improve discoverability

Job Description:
{jd_text}
"""

    return base_prompt


def run_analysis(cv_text, jd_text=None):

    if not cv_text.strip():
        st.error("No CV text extracted.")
        st.stop()

    prompt = build_prompt(cv_text, jd_text)

    response = model.generate_content(prompt)

    return response.text


# =============================
# UI
# =============================

st.set_page_config(page_title="Swiss CV Analyser", layout="wide")

st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# -----------------------------
# Password Gate
# -----------------------------

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:

    pw = st.text_input("Enter password", type="password")

    if st.button("Login"):
        if pw == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Wrong password")

    st.stop()

# -----------------------------
# Uploads
# -----------------------------

st.subheader("Upload CV (PDF)")

cv_file = st.file_uploader("Upload CV PDF", type=["pdf"])

st.subheader("Optional: Upload Job Description")

jd_file = st.file_uploader("Upload JD PDF (optional)", type=["pdf"])

jd_text_manual = st.text_area("Or paste Job Description text here (optional)", height=150)

# -----------------------------
# Run
# -----------------------------

if st.button("Analyse CV"):

    if not cv_file:
        st.warning("Please upload a CV.")
        st.stop()

    with st.spinner("Extracting CV text..."):
        cv_text = extract_pdf_text(cv_file)

    jd_text = ""

    if jd_file:
        with st.spinner("Extracting JD text..."):
            jd_text = extract_pdf_text(jd_file)

    elif jd_text_manual.strip():
        jd_text = jd_text_manual

    st.write(f"CV characters used: {len(cv_text)}")

    if jd_text:
        st.write(f"JD characters used: {len(jd_text)}")

    with st.spinner("Running AI analysis..."):
        result = run_analysis(cv_text, jd_text)

    st.success("Analysis completed")

    st.subheader("Results")

    st.text_area("CV Analysis Output", result, height=600)

    # Optional save

    if st.button("Save Analysis to File"):

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Swiss_CV_Analysis_{timestamp}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(result)

        st.success(f"Saved as {filename}")
