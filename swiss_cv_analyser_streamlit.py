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
def get_best_model():
    try:
        # Use the most stable 2026 model names
        model = genai.GenerativeModel("gemini-1.5-flash")
        return model
    except Exception as e:
        st.sidebar.error(f"Model Initialization Error: {e}")
        return None

model_instance = get_best_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    if file is None: return ""
    text = ""
    try:
        # CRITICAL: Reset file pointer in case it was read elsewhere
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
    if not model_instance: return "Error: Model not initialized"
    
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            else:
                return "Error: AI returned an empty response (check safety filters)."
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                st.warning(f"Rate limit hit. Retrying in 10s... ({attempt+1}/3)")
                time.sleep(10)
                continue
            elif "403" in err_msg:
                return f"Authentication Error: {err_msg}. Ensure 2-Step Verification is ON in Google Cloud."
            else:
                return f"API Error: {err_msg}"
    return "Error: Maximum retries reached."

def create_word_report(report_text):
    try:
        # Ensure template.docx exists in your repo
        doc = DocxTemplate("template.docx")
        
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

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
        st.error(f"Formatting Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    # Truncate to save tokens and avoid quota spikes
    cv_summary = call_gemini(f"Extract key career facts and technical skills: {cv_text[:5000]}")
    jd_summary = call_gemini(f"Extract core requirements: {jd_text[:3000]}") if jd_text else "General Standard"

    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    
    METADATA (MANDATORY):
    NAME_START: [Candidate Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 

    INSTRUCTIONS: 
    - Use '###' for subheadings.
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
    st.header("Authentication")
    pass_input = st.text_input("Enter Admin Password", type="password")
    if pass_input != APP_PASSWORD:
        st.info("Please authenticate to continue.")
        st.stop()
    st.success("Authenticated")
    if model_instance:
        st.write("🟢 AI Connection Active")

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD text manually", height=150)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing with Gemini AI..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Could not extract text from CV. Is the PDF empty or scanned?")
            else:
                report = run_analysis(cv_raw, jd_raw)
                st.divider()
                
                # Check if the report is actually content or an error message
                if "Error" in report or "API" in report:
                    st.error(report)
                else:
                    st.markdown(report)
                    
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button(
                            label="📩 Download Branded Word Report",
                            data=word_file,
                            file_name="Swiss_CV_Audit.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
