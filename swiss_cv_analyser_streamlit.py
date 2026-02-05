import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap
import re
import io
import time
from docxtpl import DocxTemplate

# --- Page Configuration ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭", layout="wide")

# --- API & Password Setup ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Error: Secret {e} not found in Streamlit Secrets.")
    st.stop()

@st.cache_resource
def get_best_model():
    """Dynamically finds available models to prevent 404 errors."""
    try:
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        # Priority: 1.5 Flash is best for Free Tier limits
        priority = [
            "models/gemini-1.5-flash", 
            "models/gemini-1.5-flash-latest", 
            "models/gemini-pro"
        ]
        for p in priority:
            if p in available_models:
                return genai.GenerativeModel(p)
        return genai.GenerativeModel(available_models[0])
    except Exception:
        return genai.GenerativeModel("models/gemini-1.5-flash")

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
    """Calls Gemini with 3 retries and 8-second delay for 429 errors."""
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                time.sleep(8)
                continue
            return f"\n[Model Error: {err_msg}]\n"
    return "Error: API Rate Limit reached. Please wait 10 seconds and try again."

def create_word_report(report_text):
    """Injects AI data into the branded template.docx."""
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # Clean report text for the Word body
        clean_report = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_report = re.sub(r"CATEGORY:.*?\n", "", clean_report).strip()

        context = {
            'CANDIDATE_NAME': candidate_name.upper(),
            'REPORT_CONTENT': clean_report,
            'REC_READY': "✅" if category == "READY" else "⬜",
            'REC_IMPROVE': "✅" if category == "IMPROVE" else "⬜",
            'REC_MAJOR': "✅" if category == "MAJOR" else "⬜",
        }

        doc.render(context)
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return bio
    except Exception as e:
        st.error(f"Word Template Error: {e}. Check if template.docx is in your repo.")
        return None

def run_analysis(cv_text, jd_text):
    """Main analysis logic with chunking and Swiss-specific prompts."""
    cv_chunks = wrap(cv_text, 8000)
    jd_chunks = wrap(jd_text, 8000) if jd_text else []
    cv_summary, jd_summary = "", ""

    progress = st.progress(0, text="Swiss Recruiter AI is processing...")

    for i, chunk in enumerate(cv_chunks):
        cv_summary += call_gemini(f"Extract key career facts, technical skills, and achievements: {chunk}") + "\n"
        progress.progress((i + 0.5) / (len(cv_chunks) + max(len(jd_chunks), 1)))
        time.sleep(1)

    for i, chunk in enumerate(jd_chunks):
        jd_summary += call_gemini(f"Extract core requirements and KPIs: {chunk}") + "\n"
        progress.progress((len(cv_chunks) + i + 1) / (len(cv_chunks) + len(jd_chunks)))
        time.sleep(1)

    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    
    CRITICAL METADATA:
    NAME_START: [Candidate Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 
    (READY if score > 85, IMPROVE if 60-85, MAJOR if < 60)

    STRUCTURE:
    ## 1. CV PERFORMANCE SCORECARD
    **OVERALL JOB-FIT SCORE: [Score]/100**

    ## 2. DETAILED CV AUDIT
    ### 2.1 SWISS COMPLIANCE & FORMATTING
    - **The Fact:** 85% of Swiss recruiters expect Nationality/Permit and language levels.
    - **Audit:** [Review photo, personal data, layout]
    - **Strengthening:** [Specific changes]

    ### 2.2 TECHNICAL & KEYWORD ALIGNMENT
    - **The Fact:** ATS systems spend 6 seconds on initial screen; 75% rejection if keywords missing.
    - **Audit:** [Map CV skills against JD]
    - **Strengthening:** [List 10 specific keywords]

    ### 2.3 EVIDENCE OF IMPACT (KPIs)
    - **The Fact:** Quantifiable metrics increase interview chances by 40%.
    - **Audit:** [Analyze current bullet points]
    - **Strengthening:** [Suggest 5 KPI-based bullets]

    ## 3. PRIORITY ACTION PLAN
    1. [Most Urgent]
    2. [High Impact]
    3. [Strategic Tip]

    CV DATA: {cv_summary}
    JD DATA: {jd_summary if jd_summary else "General Swiss Life Sciences Standard"}
    """
    
    result = call_gemini(final_prompt)
    progress.empty()
    return result

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    if pass_input: st.sidebar.error("Incorrect Password")
    st.info("Authenticate in the sidebar to begin.")
    st.stop()

st.sidebar.success("✅ Authenticated")
st.sidebar.caption(f"Active Model: {model_instance.model_name}")

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
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Text extraction failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                st.divider()
                st.subheader("Professional CV Audit Report")
                st.markdown(report)
                
                word_file = create_word_report(report)
                if word_file:
                    st.download_button(
                        label="📩 Download Branded Word Report",
                        data=word_file,
                        file_name="Swiss_CV_Audit_Report.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
