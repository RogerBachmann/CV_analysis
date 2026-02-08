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
    st.error(f"Missing Secret: {e}")
    st.stop()

@st.cache_resource
def get_best_model():
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
        st.error(f"PDF Error: {e}")
        return ""

def call_gemini(prompt, label="Task"):
    """Single-call handler with internal retry."""
    try:
        response = model_instance.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        if "429" in str(e):
            st.warning(f"Rate limit triggered on {label}. Retrying once...")
            time.sleep(10) # Heavy wait
            try:
                response = model_instance.generate_content(prompt)
                return response.text.strip()
            except:
                st.error(f"Retry failed for {label}.")
        else:
            st.error(f"Error in {label}: {e}")
    return ""

def run_analysis_sequential(cv_text, jd_text):
    """Executes tasks one-by-one with mandatory pauses to avoid concurrency flags."""
    
    # 1. Analyze CV
    st.write("⏳ Processing CV profile...")
    cv_summary = call_gemini(f"Summarize key skills and experience: {cv_text[:6000]}", "CV Analysis")
    if not cv_summary: return None
    
    # 2. Forced Pause
    time.sleep(2) 
    
    # 3. Analyze JD
    st.write("⏳ Processing Job Requirements...")
    jd_summary = call_gemini(f"Summarize core JD requirements: {jd_text[:4000]}", "JD Analysis") if jd_text else "General standard"
    if not jd_summary: return None
    
    # 4. Forced Pause
    time.sleep(2)
    
    # 5. Final Comparison
    st.write("🚀 Generating final Swiss-standard report...")
    final_prompt = f"""
    You are a Swiss Recruiter. Match this CV to the JD.
    NAME_START: [Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]
    
    ### 1. SCORECARD
    Fit Score: [0-100]
    
    ### 2. ANALYSIS
    - Compliance
    - Gaps
    
    CV: {cv_summary}
    JD: {jd_summary}
    """
    return call_gemini(final_prompt, "Final Comparison")

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"
        
        # Format content for Word
        rt = RichText()
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body).replace("**", "").strip()
        
        for line in clean_body.split('\n'):
            line = line.strip()
            if not line: rt.add('\n')
            elif line.startswith('###'): rt.add('\n'+line.lstrip('#').strip()+'\n', size=28, color='1D457C')
            else: rt.add(line + '\n', size=24)

        doc.render({'CANDIDATE_NAME': candidate_name.upper(), 'REPORT_CONTENT': rt,
                    'REC_READY': "✅" if category == "READY" else "⬜",
                    'REC_IMPROVE': "✅" if category == "IMPROVE" else "⬜",
                    'REC_MAJOR': "✅" if category == "MAJOR" else "⬜"})
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return bio
    except Exception as e:
        st.error(f"Word Error: {e}")
        return None

# --- UI ---
st.title("🇨🇭 Swiss CV Analyser")

pass_input = st.sidebar.text_input("Password", type="password")
if pass_input != APP_PASSWORD:
    st.info("Authenticate in sidebar.")
    st.stop()

cv_file = st.file_uploader("CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("JD (PDF)", type=["pdf"])
jd_text = st.text_area("Or paste JD")

if st.button("Run Analysis"):
    if cv_file:
        with st.spinner("Executing sequential steps..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_text
            
            report = run_analysis_sequential(cv_raw, jd_raw)
            
            if report:
                st.markdown(report)
                word = create_word_report(report)
                if word:
                    st.download_button("📩 Download Word Report", word, "Swiss_Audit.docx")
    else:
        st.warning("Upload a CV first.")
