import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- Page Configuration ---
st.set_page_config(
    page_title="Swiss Life Sciences CV Analyser", 
    page_icon="🇨🇭", 
    layout="wide"
)

# --- API & Password Setup ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"FATAL ERROR: Secret {e} not found in Streamlit Secrets.")
    st.stop()

@st.cache_resource
def get_best_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ["models/gemini-1.5-flash", "models/gemini-pro"]
        for p in priority:
            if p in available_models: return genai.GenerativeModel(p)
        return genai.GenerativeModel(available_models[0])
    except Exception as e:
        st.warning(f"Model Discovery Error: {e}. Falling back to default.")
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

def call_gemini(prompt, label="API Call"):
    """Enhanced with error identification."""
    if not prompt.strip():
        return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            if not response.text:
                st.error(f"Empty response received from {label}.")
                return ""
            return response.text.strip()
        except Exception as e:
            # Check for Rate Limits
            if "429" in str(e):
                st.warning(f"{label}: Rate limit hit. Retrying in 8s... (Attempt {attempt+1}/3)")
                time.sleep(8)
                continue
            # Check for Safety Filters
            elif "safety" in str(e).lower():
                st.error(f"Blocked by Safety Filter: The content was flagged as sensitive.")
                return ""
            else:
                st.error(f"Gemini API Error ({label}): {e}")
                return ""
    return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"
        
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").strip()
        
        rt = RichText()
        for line in clean_body.split('\n'):
            line = line.strip()
            if not line:
                rt.add('\n')
            elif line.startswith('###') or line.startswith('##'):
                rt.add('\n' + line.lstrip('#').strip() + '\n', font='Calibri', size=28, color='1D457C')
            else:
                rt.add(line + '\n', font='Calibri', size=24, color='333333')
        
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
        st.error(f"Word Formatting Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    # STEP 1: CV Summary
    st.info("Step 1: Summarizing CV...")
    cv_summary = call_gemini(f"Extract key career facts: {cv_text[:8000]}", "CV Summary")
    if not cv_summary: return None
    
    # STEP 2: JD Summary
    st.info("Step 2: Summarizing Job Description...")
    jd_summary = call_gemini(f"Extract core requirements: {jd_text[:8000]}", "JD Summary") if jd_text else "General Standard"
    if not jd_summary: return None
    
    # STEP 3: Final Analysis
    st.info("Step 3: Generating Final Report...")
    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    NAME_START: [Candidate Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]
    ### 1. SCORECARD
    Score: [0-100]
    ### 2. AUDIT
    Details...
    CV: {cv_summary}
    JD: {jd_summary}
    """
    return call_gemini(final_prompt, "Final Analysis")

# --- UI Interface ---

st.title("🇨🇭 Swiss CV Analyser (Debug Mode)")

pass_input = st.sidebar.text_input("Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Enter password to start.")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD manually")

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        # Clear previous states
        with st.status("Work in progress...", expanded=True) as status:
            st.write("Extracting text from PDF...")
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("CV Text extraction failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                
                if report:
                    st.divider()
                    st.markdown(report)
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button("📩 Download Report", word_file, "Swiss_Audit.docx")
                else:
                    st.error("The analysis process returned no data. Check API logs above.")
            status.update(label="Analysis Complete!", state="complete", expanded=False)
