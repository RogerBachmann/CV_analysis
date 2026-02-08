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
                time.sleep(8)
                continue
            return ""
    return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # 2. Body Cleaning (Remove AI markdown)
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").strip()

        # 3. Build RichText
        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line_content = line.strip()
            if not line_content:
                rt.add('\n')
                continue
            
            if line_content.startswith('###') or line_content.startswith('##'):
                # Subheadings: Blue (2F5496), No Bold
                rt.add(line_content.lstrip('#').strip(), color='2F5496', bold=False)
                rt.add('\n')
            else:
                # Body Text: Standard Black, No Bold
                # This will adopt the font/size you set for the tag in Word
                rt.add(line_content, color='000000', bold=False)
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
    cv_summary = call_gemini(f"Extract key career facts: {cv_text[:8000]}")
    jd_summary = call_gemini(f"Extract core requirements: {jd_text[:8000]}") if jd_text else "General Standard"

    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV.
    METADATA:
    NAME_START: [Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 

    INSTRUCTIONS: 
    - Use '###' for subheadings.
    - No bold markdown (**).

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100
    ### 2. SWISS COMPLIANCE
    Review: [Review]
    ### 3. TECHNICAL ALIGNMENT
    Mapping: [Mapping]
    ### 4. EVIDENCE OF IMPACT
    Metrics: [Metrics]
    ### 5. PRIORITY ACTION PLAN
    1. [Task]

    CV: {cv_summary}
    JD: {jd_summary}
    """
    return call_gemini(final_prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Authenticate in the sidebar.")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD text", height=150)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if cv_raw:
                report = run_analysis(cv_raw, jd_raw)
                st.markdown(report)
                word_file = create_word_report(report)
                if word_file:
                    st.download_button("📩 Download Word Report", word_file, "Swiss_CV_Audit.docx")
