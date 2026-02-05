import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- 1. Page Configuration ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭", layout="wide")

# --- 2. API & Password Setup ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Missing Secret: {e}. Please check your Streamlit Cloud secrets.")
    st.stop()

# --- 3. Stable Model Discovery (The 404 Fix) ---
@st.cache_resource
def get_stable_model():
    """Queries your specific API key to find the correct model path."""
    try:
        # Get all models that support content generation
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priority order for the most robust model naming conventions
        priority = [
            "models/gemini-1.5-flash-latest",
            "models/gemini-1.5-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash"
        ]
        
        selected_model = next((p for p in priority if p in available_models), None)
        
        if not selected_model and available_models:
            selected_model = available_models[0]
            
        if not selected_model:
            st.error("No compatible Gemini models found for this API key.")
            st.stop()

        # Relaxed safety settings to prevent failures on medical/science jargon
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        return genai.GenerativeModel(model_name=selected_model, safety_settings=safety)
    except Exception as e:
        st.error(f"Connection Error: {e}")
        st.stop()

model_instance = get_stable_model()

# --- 4. Helper Functions ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    if file is None: return ""
    text = ""
    try:
        file.seek(0) 
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"PDF Error: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            return "AI Error: Response was empty."
        except Exception as e:
            if "429" in str(e):
                time.sleep(10)
                continue
            return f"AI Error: {str(e)}"
    return "AI Error: Max retries exceeded."

def create_word_report(report_text):
    """Formats the report with strict font controls."""
    try:
        doc = DocxTemplate("template.docx")
        
        # Parse Metadata
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # Content Cleaning (Stripping internal tags and all bold markdown)
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
                # Subheaders: Navy, 14pt (Size 28), Bold
                rt.add('\n' + display_text + '\n', font='Calibri', size=28, color='1D457C', bold=True)
            else:
                # Main Body: Black, 12pt (Size 24), NOT BOLD
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

def run_analysis(cv_text, jd_text):
    """Main prompt with weighted rubric for scoring consistency."""
    prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Analyze the CV against the JD. 
    SCORING RUBRIC: Technical (40%), Seniority (20%), Swiss Compliance (20%), KPIs (20%).

    NAME_START: [Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]

    INSTRUCTIONS: 
    - NO bold markdown (**). 
    - Use '###' for section headers.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [X]/100
    Breakdown: [Brief explanation of score per category]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: Swiss standards require clear Permit and Language levels.
    Audit: [Analysis]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: Keywords are essential for Swiss ATS systems.
    Audit: [Review]

    ### 4. PRIORITY ACTION PLAN
    1. [Strategic Task]
    2. [Critical Task]

    CV: {cv_text[:7000]}
    JD: {jd_text[:3000] if jd_text else "General Swiss Life Sciences Industry Standard"}
    """
    return call_gemini(prompt)

# --- 5. UI Interface ---
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
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"], key="cv_final")

with col2:
    st.subheader("2. Target Job")
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"], key="jd_final")
    jd_manual = st.text_area("Or paste JD text manually", height=100)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Text extraction failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                
                if "AI Error" not in report:
                    st.divider()
                    st.markdown(report)
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button("📩 Download Audit", word_file, "Swiss_CV_Audit.docx")
                else:
                    st.error(report)
