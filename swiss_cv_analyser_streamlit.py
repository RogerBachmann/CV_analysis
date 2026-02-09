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
    st.error(f"Error: Secret {e} not found in Streamlit Secrets.")
    st.stop()

@st.cache_resource
def get_best_available_model():
    """
    Dynamically finds the best available Flash model for your API key.
    This prevents 404 errors when Google retires old models (like 1.5-flash).
    """
    try:
        # Get all models that support content generation
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 2026 Priority List (Newest to Oldest)
        priority = [
            "models/gemini-3-flash", 
            "models/gemini-3-flash-preview",
            "models/gemini-2.5-flash",
            "models/gemini-2.0-flash",
            "models/gemini-1.5-flash-latest" # Legacy fallback
        ]
        
        for p in priority:
            if p in models:
                return genai.GenerativeModel(p)
        
        # Absolute fallback: use the first available model in the list
        return genai.GenerativeModel(models[0])
    except Exception as e:
        st.sidebar.error(f"Critical: Could not list models. {e}")
        # Defaulting to the standard 2.5/3 stable name if listing fails
        return genai.GenerativeModel("gemini-2.5-flash")

model_instance = get_best_available_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    if file is None: return ""
    text = ""
    try:
        # Reset file pointer to ensure we read from the start
        file.seek(0) 
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"PDF Extraction Error: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return "Error: Empty Prompt"
    
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            return "Error: AI returned an empty response."
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg: # Rate Limit
                st.warning(f"Rate limit hit. Retrying in 10s... ({attempt+1}/3)")
                time.sleep(10)
                continue
            elif "403" in err_msg: # Security / MFA
                return f"Authentication Blocked: Enable 2-Step Verification in Google Cloud. Details: {err_msg}"
            elif "404" in err_msg: # Model Not Found
                return f"Model Error (404): The requested model version is no longer available. Please refresh the app."
            else:
                return f"API Error: {err_msg}"
    return "Error: Maximum retries reached."

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata Parsing
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # Content Cleaning
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").strip()

        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n')
                continue
            
            if line.startswith('###') or line.startswith('##'):
                display_text = line.lstrip('#').strip()
                rt.add(display_text, font='Calibri', size=28, color='1D457C')
                rt.add('\n')
            else:
                rt.add(line, font='Calibri', size=24, color='E7E6E6')
                rt.add('\n')

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

def run_analysis(cv_text, jd_text):
    # Summaries to stay within Free Tier token limits
    cv_summary = call_gemini(f"Extract career facts and skills: {cv_text[:6000]}")
    jd_summary = call_gemini(f"Extract core requirements: {jd_text[:3000]}") if jd_text else "General Standard"

    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    
    METADATA (MANDATORY):
    NAME_START: [Candidate Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 

    INSTRUCTIONS: 
    - Use '###' for subheadings.
    - Do NOT include a main title.
    - Do NOT use any bold markdown (**).

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100

    ### 2. SWISS COMPLIANCE & FORMATTING
    Audit: [Review]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    Audit: [Mapping]

    ### 4. EVIDENCE OF IMPACT (KPIs)
    Audit: [Metrics]

    ### 5. PRIORITY ACTION PLAN
    1. [Task]
    2. [Task]

    CV DATA: {cv_summary}
    JD DATA: {jd_summary}
    """
    return call_gemini(final_prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

with st.sidebar:
    st.header("Admin Access")
    pass_input = st.text_input("Password", type="password")
    if pass_input != APP_PASSWORD:
        st.info("Authenticate in the sidebar.")
        st.stop()
    st.success("Authenticated")
    st.write(f"🤖 **Model:** {model_instance.model_name}")

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD text", height=100)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Extraction failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                st.divider()
                
                if "Error" in report or "Authentication" in report:
                    st.error(report)
                else:
                    st.markdown(report)
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button(
                            label="📩 Download Report",
                            data=word_file,
                            file_name=f"CV_Audit_{int(time.time())}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
