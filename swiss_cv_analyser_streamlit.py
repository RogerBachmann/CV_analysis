import os
import re
import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap

APP_PASSWORD = "swisscareer"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

MAX_CHUNK_SIZE = 4000


def clean_text(text):
    text = text.encode("utf-8", "ignore").decode()
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_pdf_text(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + " "
    return clean_text(text)


def chunk_text(text):
    return wrap(text, MAX_CHUNK_SIZE)


def call_gemini(prompt):
    response = model.generate_content([prompt])   # <<< FIX
    return response.text.strip()


def run_analysis(cv_text, jd_text):

    cv_chunks = chunk_text(cv_text)
    jd_chunks = chunk_text(jd_text) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    for chunk in cv_chunks:
        prompt = f"""
Summarise this CV content for Swiss Life Sciences hiring:

{chunk}
"""
        cv_summary += call_gemini(prompt) + "\n"

    for chunk in jd_chunks:
        prompt = f"""
Summarise this job description:

{chunk}
"""
        jd_summary += call_gemini(prompt) + "\n"

    final_prompt = f"""
You are a senior Swiss Life Sciences recruiter.

Analyse this CV against Swiss standards and the job description.

Focus on:
- Swiss CV structure
- keyword gaps
- ATS searchability
- seniority alignment
- concrete improvements

CV SUMMARY:
{cv_summary}

JD SUMMARY:
{jd_summary}
"""

    return call_gemini(final_prompt)


st.title("Swiss CV & Job Fit Analyser")

password = st.text_input("Password", type="password")

if password != APP_PASSWORD:
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF optional)", type=["pdf"])

jd_text_manual = st.text_area("Or paste JD text")

if st.button("Run Analysis"):

    if not cv_file:
        st.warning("Upload CV first")
        st.stop()

    cv_text = extract_pdf_text(cv_file)

    if jd_file:
        jd_text = extract_pdf_text(jd_file)
    else:
        jd_text = clean_text(jd_text_manual)

    st.write("CV chars:", len(cv_text))
    st.write("JD chars:", len(jd_text))

    result = run_analysis(cv_text, jd_text)

    st.subheader("Result")
    st.write(result)
