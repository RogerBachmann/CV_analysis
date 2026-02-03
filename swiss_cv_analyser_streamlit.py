import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap
import re
import io

# --- Page Configuration ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭", layout="wide")

# --- API & Password from Streamlit Secrets ---
try:
    # Pulling credentials from the Secrets section of your Streamlit Dashboard
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Error: Secret {e} not found in Streamlit Secrets.")
    st.info("Ensure GEMINI_API_KEY and APP_PASSWORD are added to your Streamlit Cloud 'Secrets' settings.")
    st.stop()

# --- Model Discovery ---
@st.cache_resource
def get_best_model():
    """Finds the best available model for your specific API key."""
    MODEL_PRIORITY = ["gemini-3-flash", "gemini-2.5-flash", "gemini-1.5-flash-latest"]
    try:
        available_models = [m.name.split('/')[-1] for m in genai.list_models() 
                           if 'generateContent' in m.supported_generation_methods]
        for model_name in MODEL_PRIORITY:
            if model_name in available_models:
                return genai.GenerativeModel(model_name)
        return genai.GenerativeModel(available_models[0])
    except Exception:
        return genai.GenerativeModel("gemini-1.5-flash")

model_instance = get_best_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"PDF Extraction Error: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    try:
        response = model_instance.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"\n[Model Error: {str(e)}]\n"

def run_analysis(cv_text, jd_text):
    cv_chunks = wrap(cv_text, 10000)
    jd_chunks = wrap(jd_text, 10000) if jd_text else []

    cv_summary = ""
    jd_summary = ""

    progress = st.progress(0, text="Swiss Recruiter AI is processing your CV...")

    # Processing Chunks
    for i, chunk in enumerate(cv_chunks):
        cv_summary += call_gemini(f"Extract key career facts, technical skills, and achievements from this CV chunk:\n\n{chunk}") + "\n"
        progress.progress((i + 0.5) / (len(cv_chunks) + max(len(jd_chunks), 1)))

    for i, chunk in enumerate(jd_chunks):
        jd_summary += call_gemini(f"Extract core requirements and required KPIs from this Job Description:\n\n{chunk}") + "\n"
        progress.progress((len(cv_chunks) + i + 1) / (len(cv_chunks) + len(jd_chunks)))

    # FINAL CV ANALYSIS PROMPT
    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the Job Description.
    
    CRITICAL: For every section, lead with 'The Fact' (a statistic or Swiss hiring standard).
    
    STRUCTURE FOR WORD TEMPLATE:
    ## 1. CV PERFORMANCE SCORECARD
    **OVERALL JOB-FIT SCORE: [Score]/100**
    (Based on Technical Gap Analysis, Swiss Market Compliance, and Impact-Evidence)

    ## 2. DETAILED CV AUDIT

    ### 2.1 SWISS COMPLIANCE & FORMATTING
    - **The Fact:** 85% of Swiss recruiters expect to see Nationality/Permit status and language levels (A1-C2) clearly stated. A missing photo can reduce engagement by 15-20% in the DACH region.
    - **Audit:** [Review photo, personal data, and layout professionality]
    - **Strengthening:** [Specific layout/data changes]

    ### 2.2 TECHNICAL & KEYWORD ALIGNMENT
    - **The Fact:** ATS systems and recruiters spend an average of 6 seconds on an initial screen; 75% of CVs are rejected because keywords from the JD are not found in the 'Professional Experience' bullets.
    - **Audit:** [Map CV skills against JD requirements]
    - **Strengthening:** [List 10 specific keywords/skills to integrate]

    ### 2.3 EVIDENCE OF IMPACT (KPIs)
    - **The Fact:** CVs in Life Sciences with quantifiable metrics (e.g., 'Reduced deviations by 20%') have a 40% higher chance of reaching the interview stage.
    - **Audit:** [Analyze current bullet points for quantifiable results]
    - **Strengthening:** [Suggest 5 KPI-based bullet points based on the role]

    ### 2.4 SENIORITY & SALARY EXPECTATION
    - **The Fact:** In the Basel/Zurich hub, titles like 'Senior' or 'Lead' have specific year-of-experience benchmarks. Misalignment leads to automatic rejection.
    - **Audit:** [Does this candidate's history match the seniority of the JD?]
    - **Strengthening:** [How to reposition the narrative to match the target level]

    ## 3. PRIORITY ACTION PLAN (TOP 3 IMPROVEMENTS)
    1. [Most Urgent]
    2. [High Impact]
    3. [Strategic Tip]

    CV DATA: {cv_summary}
    JD DATA: {jd_summary if jd_summary else "General Swiss Life Sciences Market Standard"}
    """
    
    result = call_gemini(final_prompt)
    progress.empty()
    return result

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# Sidebar Authentication using Secrets
pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    if pass_input: st.sidebar.error("Incorrect Password")
    st.info("Authenticate in the sidebar to begin analysis.")
    st.stop()

st.sidebar.success("✅ Authenticated")
st.sidebar.caption(f"Model: {model_instance.model_name}")

# Main Layout
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Upload CV")
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])

with col2:
    st.subheader("2. Target Job")
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
    jd_manual = st.text_area("Or paste JD text manually", height=150)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV to proceed.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Text extraction failed. Please ensure the PDF is not an image.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                st.divider()
                st.subheader("Professional CV Audit Report")
                st.markdown(report)
                
                # Download button for Word Template use
                st.download_button(
                    label="📩 Download Report for Word",
                    data=report,
                    file_name="Swiss_CV_Audit.txt",
                    mime="text/plain"
                )
