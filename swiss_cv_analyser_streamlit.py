import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap
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
    st.error(f"Error: Secret {e} not found.")
    st.stop()

# --- Robust Model Setup ---
@st.cache_resource
def get_model():
    # Standardizing to 1.5-flash for the best free-tier performance
    # We apply 'BLOCK_NONE' to prevent the "Failed after 3 retries" caused by safety triggers
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        safety_settings=safety_settings
    )

model_instance = get_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    if file is None: return ""
    text = ""
    try:
        file.seek(0)
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"PDF Error: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            # Short delay to prevent 429 on button spam
            if attempt > 0: time.sleep(5) 
            response = model_instance.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            return "AI Error: Safety Filter triggered or empty response."
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                time.sleep(12)
                continue
            return f"AI Error: {err_msg}"
    return "AI Error: Connection timed out."

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # Formatting Clean-up
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").replace("__", "").strip()

        rt = RichText()
        lines = clean_body.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n', font='Calibri', size=24, bold=False)
                continue
            
            if line.startswith('###') or line.startswith('##'):
                display_text = line.lstrip('#').strip()
                rt.add('\n' + display_text + '\n', font='Calibri', size=28, color='1D457C', bold=True)
            else:
                rt.add(line + '\n', font='Calibri', size=24, color='000000', bold=False)

        context = {
            'CANDIDATE_NAME': candidate_name.upper(),
            'REPORT_CONTENT': rt,
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
        st.error(f"Word Creation Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    # Truncate aggressively to ensure stability
    cv_snip = cv_text[:6000]
    jd_snip = jd_text[:3000] if jd_text else "General Swiss Life Sciences Standard"

    prompt = f"""
    You are a Senior Swiss Recruiter. Analyse the CV against the JD. 
    Be highly consistent and mathematical in your scoring.

    RUBRIC: Technical (40%), Seniority (20%), Swiss Compliance (20%), KPIs (20%)

    METADATA:
    NAME_START: [Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [X]/100
    Math Breakdown: [Category scores]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: Swiss standards require clear Permit and Language levels.
    Audit: [Analysis]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: ATS systems require specific keyword density.
    Audit: [Review]

    ### 4. PRIORITY ACTION PLAN
    1. [Task]
    2. [Task]

    CV: {cv_snip}
    JD: {jd_snip}
    """
    return call_gemini(prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Enter password in sidebar.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])

with col2:
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
    jd_manual = st.text_area("Or paste JD", height=100)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Text extraction from PDF failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                
                if "AI Error" not in report:
                    st.divider()
                    st.markdown(report)
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button("📩 Download Word Report", word_file, "Swiss_Audit.docx")
                else:
                    st.error(report)
                    st.info("The AI might have found the content too complex. Try a smaller JD or a cleaner PDF.")
