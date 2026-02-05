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
    st.error(f"Error: Secret {e} not found in Streamlit Secrets.")
    st.stop()

@st.cache_resource
def get_best_model():
    """Updated discovery logic to fix 404 errors by finding the exact model string."""
    try:
        # Get all models that support 'generateContent'
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # We prioritize 'flash-latest' as it is the most stable endpoint for v1beta
        priority_list = [
            "models/gemini-1.5-flash-latest",
            "models/gemini-1.5-flash",
            "models/gemini-pro"
        ]
        
        for model_path in priority_list:
            if model_path in models:
                return genai.GenerativeModel(model_path)
        
        # If none of the priority list is found, use the first available model
        return genai.GenerativeModel(models[0])
    except Exception as e:
        # Hard fallback to standard string if listing fails
        return genai.GenerativeModel("gemini-1.5-flash")

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
        # Create a fresh bytes stream from the file
        file_bytes = file.read()
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"PDF Extraction Error: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            return "AI Error: Response was empty or blocked by safety filters."
        except Exception as e:
            if "429" in str(e):
                time.sleep(10)
                continue
            return f"AI Error: {str(e)}"
    return "AI Error: Failed after 3 retries."

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

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
        st.error(f"Word Doc Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate the CV against the JD. 
    Maintain high consistency in scoring by using the following rubric:
    - Technical (40%), Seniority (20%), Swiss Compliance (20%), Impact/KPIs (20%)

    REQUIRED METADATA:
    NAME_START: [Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]

    INSTRUCTIONS:
    - NO bold markdown (**).
    - Use '###' for headers.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100
    Breakdown: [Brief explanation of score per category]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: Swiss standards require clear Permit/Language levels.
    Audit: [Review]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: Keywords are essential for passing Swiss ATS screening.
    Audit: [Comparison]

    ### 4. PRIORITY ACTION PLAN
    1. [Action 1]
    2. [Action 2]

    CV DATA: {cv_text[:7000]}
    JD DATA: {jd_text[:3000] if jd_text else "General Swiss Life Sciences Industry Standard"}
    """
    return call_gemini(prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    if pass_input: st.sidebar.error("Incorrect Password")
    st.info("Authenticate in the sidebar to begin.")
    st.stop()

st.sidebar.success("✅ Authenticated")

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Upload CV")
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"], key="cv_upload")

with col2:
    st.subheader("2. Target Job")
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"], key="jd_upload")
    jd_manual = st.text_area("Or paste JD text manually", height=100)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("AI is analyzing... please wait."):
            # Re-read to ensure buffer is at start
            cv_file.seek(0)
            cv_raw = extract_pdf_text(cv_file)
            
            if jd_file:
                jd_file.seek(0)
                jd_raw = extract_pdf_text(jd_file)
            else:
                jd_raw = clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Could not extract text from the CV.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                
                if report and "AI Error" not in report:
                    st.divider()
                    st.markdown(report)
                    
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button(
                            label="📩 Download Branded Word Report",
                            data=word_file,
                            file_name="Swiss_CV_Audit.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                else:
                    st.error(f"Analysis failed: {report}")
