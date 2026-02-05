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

@st.cache_resource
def get_best_model():
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Using 1.5-flash for maximum reliability on free tier
        priority = ["models/gemini-1.5-flash", "models/gemini-1.5-flash-latest", "models/gemini-pro"]
        for p in priority:
            if p in available_models: return genai.GenerativeModel(p)
        return genai.GenerativeModel("models/gemini-1.5-flash")
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
    """Reliable call function with retry and validation."""
    if not prompt.strip(): 
        return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            if hasattr(response, 'text') and response.text:
                return response.text.strip()
            # If safety filters blocked it
            return "AI Error: Response was blocked or empty due to safety filters."
        except Exception as e:
            if "429" in str(e):
                time.sleep(10)
                continue
            return f"AI Error: {str(e)}"
    return "AI Error: Failed after 3 attempts."

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # Content Cleaning
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").replace("__", "").strip()

        # RichText Formatting
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
    """Single-call analysis for maximum consistency and success rate."""
    
    # We use one detailed prompt to ensure the AI doesn't 'lose' info between steps
    prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate the following CV against the JD.
    
    SCORING RUBRIC (BE CONSISTENT):
    - Technical Alignment (40%)
    - Experience Seniority (20%)
    - Swiss Compliance (20%)
    - Business Impact (20%)

    REQUIRED METADATA:
    NAME_START: [Candidate Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]

    INSTRUCTIONS:
    - No bold markdown (**).
    - Use '###' for headers.
    - Body text must be professional and concise.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100
    Math Breakdown: [Explain scores per rubric]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: Swiss recruiters require specific details on permits and language levels.
    Audit: [Compare CV to Swiss standard]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: Keywords are essential for passing initial ATS screening.
    Audit: [List matching and missing skills]

    ### 4. PRIORITY ACTION PLAN
    1. [Task 1]
    2. [Task 2]

    CV DATA: {cv_text[:7000]}
    JD DATA: {jd_text[:3000] if jd_text else "General Life Sciences Industry Standard"}
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

cv_file = st.file_uploader("1. Upload CV (PDF)", type=["pdf"])
jd_manual = st.text_area("2. Paste JD text", height=150)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("AI is thinking... please wait."):
            cv_raw = extract_pdf_text(cv_file)
            
            if not cv_raw:
                st.error("Could not extract text from the PDF.")
            else:
                # Perform analysis
                report = run_analysis(cv_raw, jd_manual)
                
                # Check if report is valid
                if report and "AI Error" not in report:
                    st.divider()
                    st.subheader("Analysis Results")
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
                    # If the output was empty or errored
                    st.error(f"Analysis failed. {report}")
                    st.info("Try refreshing the page or waiting 60 seconds.")
