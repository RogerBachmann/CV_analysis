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
    st.error(f"Missing Secret: {e}")
    st.stop()

@st.cache_resource
def get_best_model():
    # Use 1.5-flash as it is most stable for high-volume text
    return genai.GenerativeModel("models/gemini-1.5-flash")

model_instance = get_best_model()

# --- Helper Functions ---
def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return text.strip()
    except Exception as e:
        st.error(f"PDF Extraction Error: {e}")
        return ""

def call_gemini(prompt):
    try:
        response = model_instance.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        else:
            return "ERROR: AI returned an empty response. Check safety filters."
    except Exception as e:
        return f"AI ERROR: {str(e)}"

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text, re.DOTALL | re.IGNORECASE)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:\s*(READY|IMPROVE|MAJOR)", report_text, re.IGNORECASE)
        category = cat_match.group(1).upper() if cat_match else "IMPROVE"

        # Content Cleaning
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text, flags=re.DOTALL)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "")

        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n')
                continue
            
            if line.startswith('###'):
                # 13pt (Size 26), Blue (2F5496)
                rt.add('\n' + line.replace('#', '').strip() + '\n', font='Calibri', size=26, color='2F5496', bold=False)
            else:
                # 12pt (Size 24), Black
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
        st.error(f"Word Generation Error: {e}")
        return None

# --- UI ---
st.title("🇨🇭 Swiss CV Analyser")

if "report" not in st.session_state: st.session_state.report = None
if "word" not in st.session_state: st.session_state.word = None

pass_input = st.sidebar.text_input("Password", type="password")

if pass_input == APP_PASSWORD:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
    jd_manual = st.text_area("Or Paste JD Text")

    if st.button("🚀 Run Analysis"):
        if cv_file:
            with st.spinner("Processing..."):
                cv_text = extract_pdf_text(cv_file)
                jd_text = extract_pdf_text(jd_file) if jd_file else jd_manual
                
                if not cv_text:
                    st.error("No text found in CV. Is it a scanned image?")
                else:
                    # Explicit prompt for structured analysis
                    prompt = f"""
                    You are a Senior Swiss Recruiter. Analyze this CV against the JD.
                    
                    NAME_START: [Name] NAME_END
                    CATEGORY: [READY, IMPROVE, or MAJOR]

                    ### 1. PERFORMANCE SCORECARD
                    [Provide score and fit]

                    ### 2. SWISS COMPLIANCE
                    [Audit formatting/standards]

                    ### 3. TECHNICAL ALIGNMENT
                    [Check keywords/skills]

                    ### 4. ACTION PLAN
                    [List improvements]

                    CV TEXT: {cv_text[:12000]}
                    JD TEXT: {jd_text[:4000] if jd_text else "General Life Sciences Standards"}
                    """
                    
                    result = call_gemini(prompt)
                    st.session_state.report = result
                    st.session_state.word = create_word_report(result)
        else:
            st.warning("Please upload a CV.")

    # Persistent Display
    if st.session_state.report:
        st.divider()
        if "AI ERROR" in st.session_state.report:
            st.error(st.session_state.report)
        else:
            st.markdown(st.session_state.report)
            if st.session_state.word:
                st.download_button("📩 Download Report", st.session_state.word, "Swiss_CV_Audit.docx")
else:
    st.info("Enter password to begin.")
