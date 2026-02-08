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

@st.cache_resource
def get_best_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ["models/gemini-1.5-flash", "models/gemini-1.5-flash-latest", "models/gemini-pro"]
        for p in priority:
            if p in available_models: return genai.GenerativeModel(p)
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
    except Exception: return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e): 
                time.sleep(4)
                continue
            return ""
    return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text, re.DOTALL | re.IGNORECASE)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        cat_match = re.search(r"CATEGORY:\s*(READY|IMPROVE|MAJOR)", report_text, re.IGNORECASE)
        category = cat_match.group(1).upper() if cat_match else "IMPROVE"

        # Body Cleaning
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
            
            if line.startswith('#'):
                # Subheaders: 13pt (Size 26), Blue (2F5496), No Bold
                rt.add('\n' + line.lstrip('#').strip() + '\n', font='Calibri', size=26, color='2F5496', bold=False)
            else:
                # Body: 12pt (Size 24), Black (000000), No Bold
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
        st.error(f"Word Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    
    NAME_START: [Candidate Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]

    INSTRUCTIONS:
    - Use '###' for subheadings.
    - No bold markdown (**).
    - Use '•' for bullets.

    ### 1. CV PERFORMANCE SCORECARD
    Score: [X]/100

    ### 2. SWISS COMPLIANCE
    [Analysis]

    ### 3. TECHNICAL ALIGNMENT
    [Analysis]

    ### 4. PRIORITY ACTION PLAN
    [Analysis]

    CV: {cv_text[:10000]}
    JD: {jd_text[:5000] if jd_text else "General Swiss Life Sciences Standards"}
    """
    return call_gemini(prompt)

# --- UI ---
st.title("🇨🇭 Swiss CV Analyser")

pass_input = st.sidebar.text_input("Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Authenticate in sidebar.")
    st.stop()

cv_file = st.file_uploader("CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Paste JD")

# Ensure state exists
if "report" not in st.session_state: st.session_state.report = None
if "word" not in st.session_state: st.session_state.word = None

if st.button("🚀 Run Analysis"):
    if cv_file:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            res = run_analysis(cv_raw, jd_raw)
            st.session_state.report = res
            st.session_state.word = create_word_report(res)
    else:
        st.warning("Upload a CV.")

# Display results if they exist in state
if st.session_state.report:
    st.divider()
    # Display the raw analysis immediately
    st.markdown(st.session_state.report)
    
    if st.session_state.word:
        st.download_button(
            label="📩 Download Word Report",
            data=st.session_state.word,
            file_name="Swiss_CV_Audit.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
