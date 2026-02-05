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
    """Finds available models and uses 1.5-Flash for better consistency on Free Tier."""
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
    """Handles API calls with automatic retries for Quota (429) errors."""
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
    """
    Formats the AI report:
    - Subheaders: Navy (1D457C), 14pt (Size 28)
    - Body: Black (000000), 12pt (Size 24), Explicitly NOT Bold
    """
    try:
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # 2. Body Cleaning: Force removal of all bold markdown
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").replace("__", "").strip()

        # 3. Build RichText
        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n', font='Calibri', size=24, bold=False)
                continue
            
            if line.startswith('###') or line.startswith('##'):
                display_text = line.lstrip('#').strip()
                # Subheader: Navy (1D457C), 14pt (Size 28), BOLD
                rt.add('\n' + display_text + '\n', font='Calibri', size=28, color='1D457C', bold=True)
            else:
                # Main Body: Pure Black (000000), 12pt (Size 24), NOT BOLD
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
        st.error(f"Formatting Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    """
    Main analysis with Weighted Rubric to ensure consistency 
    between repeated uploads of the same document.
    """
    progress = st.progress(0, text="Swiss Recruiter AI is gathering facts...")
    
    # Step 1: Fact Extraction (Anchors the AI to data rather than prose)
    cv_summary = call_gemini(f"List ONLY extracted facts: Name, Exp Years, Degree, Top 5 Hard Skills, Language Levels, Permit Status: {cv_text[:8000]}")
    progress.progress(0.4)
    
    jd_summary = call_gemini(f"List Top 5 Hard Skills and 3 Primary KPIs: {jd_text[:8000]}") if jd_text else "General Life Sciences Industry Standard"
    progress.progress(0.7)

    # Step 2: Analysis with Rigid Scoring
    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate the CV against the JD. 
    You must be highly consistent and clinical in your scoring.
    
    SCORING RUBRIC (MANDATORY):
    - Technical Alignment (40%): Presence of mandatory hard skills.
    - Experience Seniority (20%): Match with required career level.
    - Swiss Compliance (20%): Permit, language, and formatting.
    - Business Impact (20%): Presence of quantifiable KPIs.

    REQUIRED METADATA:
    NAME_START: [Candidate Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 

    INSTRUCTIONS: 
    - Use '###' for subheadings.
    - Do NOT use ANY bold markdown (** or __).
    - Provide a professional, detailed audit.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [X]/100 
    Breakdown: [Briefly explain the math per rubric category]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: 85% of Swiss recruiters expect specific permit and language proficiency details.
    Audit: [Compare CV against Swiss standards]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: ATS rejection in Life Sciences often occurs when less than 60% of keywords match.
    Audit: [Skill mapping comparison]

    ### 4. EVIDENCE OF IMPACT (KPIs)
    The Fact: CVs with quantifiable achievements receive 40% more interview requests.
    Audit: [Review of bullets for metrics and results]

    ### 5. PRIORITY ACTION PLAN
    1. [Task]
    2. [Task]

    CV DATA: {cv_summary}
    JD DATA: {jd_summary}
    """
    
    result = call_gemini(final_prompt)
    progress.empty()
    return result

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
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])

with col2:
    st.subheader("2. Target Job")
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
    jd_manual = st.text_area("Or paste JD text manually", height=150)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing with consistency checks..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Text extraction failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
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
