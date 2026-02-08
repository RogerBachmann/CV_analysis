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
    # Ensure these are set in your Streamlit Secrets
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Error: Secret {e} not found. Please check your secrets.toml or Streamlit Cloud settings.")
    st.stop()

@st.cache_resource
def get_best_model():
    """Identifies and initializes the best available Gemini model."""
    try:
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        priority = [
            "models/gemini-1.5-flash", 
            "models/gemini-1.5-flash-latest", 
            "models/gemini-pro"
        ]
        for p in priority:
            if p in available_models:
                return genai.GenerativeModel(p)
        return genai.GenerativeModel(available_models[0])
    except Exception:
        return genai.GenerativeModel("models/gemini-1.5-flash")

model_instance = get_best_model()

# --- Helper Functions ---

def clean_text(text):
    """Removes control characters and normalizes whitespace."""
    if not text:
        return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    """Extracts and cleans text from an uploaded PDF file."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content:
                    text += content + " "
        return clean_text(text)
    except Exception:
        return ""

def call_gemini(prompt):
    """Handles API calls to Gemini with retry logic for rate limits (429)."""
    if not prompt.strip():
        return ""
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
    """Parses the AI response and renders it into a DocxTemplate."""
    try:
        # Note: You must have a 'template.docx' file in your directory
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction via Regex
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"
        
        # 2. Body Cleaning (Remove tags and bolding for the Word export)
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").strip()
        
        # 3. Build RichText for Word Formatting
        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n')
                continue
            
            if line.startswith('###') or line.startswith('##'):
                display_text = line.lstrip('#').strip()
                # Headers: Navy Blue, 14pt (Size 28)
                rt.add('\n' + display_text + '\n', font='Calibri', size=28, color='1D457C')
            else:
                # Body: Dark Grey/Black, 12pt (Size 24)
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
        st.error(f"Formatting Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    """Runs the full analysis pipeline."""
    cv_summary = call_gemini(f"Extract key career facts, technical skills, and achievements: {cv_text[:8000]}")
    jd_summary = call_gemini(f"Extract core requirements and KPIs: {jd_text[:8000]}") if jd_text else "General Life Sciences Standards"
    
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
    The Fact: [Statistic/Observation]
    Audit: [Review against Swiss standards]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: [Skill matching percentage]
    Audit: [Gap analysis]

    ### 4. EVIDENCE OF IMPACT (KPIs)
    The Fact: [Quantifiable achievement count]
    Audit: [Analysis of impact]

    ### 5. PRIORITY ACTION PLAN
    1. [Task]
    2. [Task]

    CV DATA: {cv_summary}
    JD DATA: {jd_summary}
    """
    return call_gemini(final_prompt)

# --- UI Interface ---

st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# Sidebar Authentication
pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Please enter the correct password in the sidebar to access the tool.")
    st.stop()

# Layout for Uploads
col1, col2 = st.columns(2)
with col1:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
with col2:
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])

jd_manual = st.text_area("Or paste Job Description text manually", height=150)

# Main Button Action
if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV to continue.")
    else:
        with st.spinner("Analyzing candidate profile..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Text extraction failed. Is the PDF password protected or an image?")
            else:
                report = run_analysis(cv_raw, jd_raw)
                
                # Display Results
                st.divider()
                st.markdown(report)
                
                # Generate Word Document
                word_file = create_word_report(report)
                if word_file:
                    st.download_button(
                        label="📩 Download Branded Word Report",
                        data=word_file,
                        file_name="Swiss_CV_Audit_Report.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
