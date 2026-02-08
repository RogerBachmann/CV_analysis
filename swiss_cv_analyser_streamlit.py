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
    """Dynamically finds the correct model string to avoid 404 errors."""
    try:
        # Get all models that support content generation
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Priority list for Life Sciences analysis
        priority = ["models/gemini-1.5-flash-latest", "models/gemini-1.5-flash", "models/gemini-pro"]
        
        for p in priority:
            if p in available_models:
                return genai.GenerativeModel(p)
        
        # Fallback to the first available if none of the above match
        return genai.GenerativeModel(available_models[0])
    except Exception as e:
        # Hard fallback if list_models fails
        return genai.GenerativeModel("gemini-1.5-flash")

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
    except Exception:
        return ""

def call_gemini(prompt, label="Task"):
    """Strict sequential call with error handling."""
    if not prompt.strip(): return ""
    try:
        response = model_instance.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        if "429" in str(e):
            st.warning(f"Rate limit hit on {label}. Waiting 10 seconds...")
            time.sleep(10)
            # One retry after wait
            try:
                response = model_instance.generate_content(prompt)
                return response.text.strip()
            except:
                return ""
        st.error(f"Error in {label}: {e}")
    return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"
        
        # Body Cleaning
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
                rt.add('\n' + line.lstrip('#').strip() + '\n', font='Calibri', size=28, color='1D457C')
            else:
                rt.add(line + '\n', font='Calibri', size=24, color='1D457C')
        
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
    """Steps performed one after another to avoid concurrency errors."""
    # Step 1: CV Summary
    st.write("🔄 Summarizing CV...")
    cv_summary = call_gemini(f"Extract key career facts, technical skills: {cv_text[:7000]}", "CV Analysis")
    if not cv_summary: return ""
    
    time.sleep(2) # Mandatory cooling pause
    
    # Step 2: JD Summary
    st.write("🔄 Summarizing JD...")
    jd_summary = call_gemini(f"Extract core requirements: {jd_text[:7000]}", "JD Analysis") if jd_text else "General Standard"
    if not jd_summary: return ""
    
    time.sleep(2) # Mandatory cooling pause
    
    # Step 3: Final Report
    st.write("🔄 Finalizing Swiss Audit...")
    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    NAME_START: [Candidate Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]
    
    INSTRUCTIONS:
    - Use '###' for subheadings.
    - No bold (**).
    
    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100
    ### 2. SWISS COMPLIANCE & FORMATTING
    Audit: [Review]
    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    Audit: [Mapping]
    ### 4. PRIORITY ACTION PLAN
    1. [Task]
    
    CV DATA: {cv_summary}
    JD DATA: {jd_summary}
    """
    return call_gemini(final_prompt, "Final Report")

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Authenticate in the sidebar.")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD text manually", height=150)

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
                if report:
                    st.divider()
                    st.markdown(report)
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button(
                            label="📩 Download Word Report",
                            data=word_file,
                            file_name="Swiss_CV_Audit.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
