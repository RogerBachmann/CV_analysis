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
    st.error(f"Error: Secret {e} not found.")
    st.stop()

# --- Bulletproof Model Discovery ---
@st.cache_resource
def get_working_model():
    """Tries multiple naming conventions to bypass the 404 error."""
    # List of possible strings for the same model
    model_names = [
        "gemini-1.5-flash-latest", 
        "gemini-1.5-flash", 
        "models/gemini-1.5-flash-latest",
        "models/gemini-1.5-flash"
    ]
    
    # Relaxed safety settings to prevent silent failures
    safety = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    for name in model_names:
        try:
            model = genai.GenerativeModel(model_name=name, safety_settings=safety)
            # Test the model with a tiny call to see if it actually exists (avoids 404 later)
            model.generate_content("test") 
            return model
        except Exception:
            continue
            
    st.error("Could not connect to any Gemini models. Please check your API key permissions.")
    st.stop()

model_instance = get_working_model()

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
            response = model_instance.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            return "AI Error: Safety Filter triggered or empty response."
        except Exception as e:
            if "429" in str(e):
                time.sleep(12)
                continue
            return f"AI Error: {str(e)}"
    return "AI Error: Failed after retries."

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # Content Cleaning (No Bold)
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
                # Subheader: Navy, 14pt
                rt.add('\n' + display_text + '\n', font='Calibri', size=28, color='1D457C', bold=True)
            else:
                # Body: Black, 12pt, NO BOLD
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
        st.error(f"Word Doc Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    # Shortened snips to prevent "Complexity" errors
    prompt = f"""
    You are a Senior Swiss Recruiter. Evaluate the CV against the JD. 
    Maintain a consistent, clinical score based on: Technical (40%), Seniority (20%), Swiss Compliance (20%), KPIs (20%).

    NAME_START: [Candidate Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]

    INSTRUCTIONS: NO bold markdown (**). Use '###' for headers.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100
    Breakdown: [Short Explanation]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: Swiss standards require clear Permit and Language levels.
    Audit: [Analysis]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: Keywords are essential for Swiss ATS systems.
    Audit: [Review]

    ### 4. PRIORITY ACTION PLAN
    1. [Task]
    2. [Task]

    CV: {cv_text[:6000]}
    JD: {jd_text[:3000] if jd_text else "General Swiss Life Sciences"}
    """
    return call_gemini(prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Enter password to start.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    cv_f = st.file_uploader("Upload CV", type=["pdf"])
with col2:
    jd_f = st.file_uploader("Upload JD", type=["pdf"])
    jd_m = st.text_area("Or paste JD", height=100)

if st.button("🚀 Run Analysis"):
    if cv_f:
        with st.spinner("Connecting to model and analysing..."):
            cv_txt = extract_pdf_text(cv_f)
            jd_txt = extract_pdf_text(jd_f) if jd_f else clean_text(jd_m)
            
            report = run_analysis(cv_txt, jd_txt)
            
            if "AI Error" not in report:
                st.divider()
                st.markdown(report)
                w_file = create_word_report(report)
                if w_file:
                    st.download_button("📩 Download Audit", w_file, "Swiss_Audit.docx")
            else:
                st.error(report)
