import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- Page Configuration ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭", layout="wide")

# --- API & Password Setup ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Secret {e} not found.")
    st.stop()

# CHANGE: Using the most compatible model string format
try:
    model_instance = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    st.error(f"Model Init Error: {e}")
    st.stop()

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
    except Exception: return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    try:
        # Generate content with a timeout/safety check
        response = model_instance.generate_content(prompt)
        if hasattr(response, 'text'):
            return response.text.strip()
        else:
            return "Error: Response blocked by safety filters or empty."
    except Exception as e:
        if "429" in str(e):
            time.sleep(10)
            response = model_instance.generate_content(prompt)
            return response.text.strip()
        st.error(f"API Error: {e}")
        return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"
        
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body).replace("**", "").strip()
        
        rt = RichText()
        for line in clean_body.split('\n'):
            line = line.strip()
            if not line: rt.add('\n')
            elif line.startswith('###'): rt.add('\n'+line.lstrip('#').strip()+'\n', size=28, color='1D457C')
            else: rt.add(line + '\n', size=24)

        doc.render({
            'CANDIDATE_NAME': candidate_name.upper(), 
            'REPORT_CONTENT': rt,
            'REC_READY': "✅" if category == "READY" else "⬜",
            'REC_IMPROVE': "✅" if category == "IMPROVE" else "⬜",
            'REC_MAJOR': "✅" if category == "MAJOR" else "⬜"
        })
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return bio
    except Exception: return None

def run_analysis(cv_text, jd_text):
    # Step 1: CV Summary
    cv_sum = call_gemini(f"Extract key career facts: {cv_text[:8000]}")
    if not cv_sum: return None
    time.sleep(2)
    
    # Step 2: JD Summary
    jd_sum = call_gemini(f"Extract core requirements: {jd_text[:8000]}") if jd_text else "General CQV standard"
    if not jd_sum: return None
    time.sleep(2)
    
    # Step 3: Comparison
    prompt = f"""
    You are a Swiss Recruiter. Evaluate this CV vs JD for a Life Sciences role.
    NAME_START: [Candidate Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]
    ### 1. SCORECARD
    Fit Score: [X]/100
    ### 2. AUDIT
    Review: ...
    CV DATA: {cv_sum}
    JD DATA: {jd_sum}
    """
    return call_gemini(prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV Analyser")

pass_input = st.sidebar.text_input("Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Please enter the admin password in the sidebar.")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD manually")

if st.button("🚀 Run Analysis"):
    if cv_file:
        with st.spinner("Processing Sequential Steps..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            report = run_analysis(cv_raw, jd_raw)
            if report:
                st.markdown(report)
                word = create_word_report(report)
                if word:
                    st.download_button("📩 Download Word Report", word, "Swiss_CV_Audit.docx")
    else:
        st.warning("Please upload a CV.")
        
