import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- 1. Page Config ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭", layout="wide")

# --- 2. API & Password Setup ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Error: Secret {e} not found.")
    st.stop()

def get_model():
    # Keeping the logic that worked for you
    try:
        return genai.GenerativeModel("gemini-1.5-flash")
    except:
        return genai.GenerativeModel("gemini-pro")

# --- 3. Helper Functions ---
def extract_pdf_text(file):
    if file is None: return ""
    try:
        file.seek(0) 
        text = ""
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return text.strip()
    except Exception as e:
        st.error(f"PDF Error: {e}")
        return ""

def call_gemini(model, prompt):
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error: {str(e)}"

# --- 4. NEW & IMPROVED WORD GENERATION ---
def create_word_report(report_text):
    try:
        # Load your template.docx
        doc = DocxTemplate("template.docx")
        
        # Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # Content Cleaning for Word
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        # Remove bold markdown as requested in prompt instructions
        clean_body = clean_body.replace("**", "")

        rt = RichText()
        lines = clean_body.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n')
                continue
            
            if line.startswith('###'):
                # Subheader: Navy, 14pt (28 in docxtpl size)
                rt.add(line.replace('###', '').strip(), font='Calibri', size=28, color='1D457C')
                rt.add('\n')
            else:
                # Body: Light Grey, 12pt (24 in docxtpl size)
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
        st.error(f"Word Export Error: {e}")
        return None

# --- 5. UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

with st.sidebar:
    st.header("Admin Access")
    pass_input = st.text_input("Password", type="password")
    
if pass_input != APP_PASSWORD:
    st.info("Enter password in sidebar")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD text", height=100)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            active_model = get_model()
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Could not read CV content.")
            else:
                # This is the AI Prompt - UNCHANGED
                report = call_gemini(active_model, f"""
                You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
                
                METADATA (MANDATORY):
                NAME_START: [Candidate Full Name] NAME_END
                CATEGORY: [READY, IMPROVE, or MAJOR] 

                INSTRUCTIONS: 
                - Use '###' for subheadings.
                - Do NOT use any bold markdown (**).

                ### 1. CV PERFORMANCE SCORECARD
                ### 2. SWISS COMPLIANCE & FORMATTING
                ### 3. TECHNICAL & KEYWORD ALIGNMENT
                ### 4. EVIDENCE OF IMPACT (KPIs)
                ### 5. PRIORITY ACTION PLAN

                CV DATA: {cv_raw[:6000]}
                JD DATA: {jd_raw[:3000]}
                """)
                
                # 1. Display Output (The part you liked)
                st.divider()
                st.markdown(report)
                
                # 2. Add the Word Download Button (The fix)
                word_file = create_word_report(report)
                if word_file:
                    st.download_button(
                        label="📩 Download Branded Word Report",
                        data=word_file,
                        file_name="Swiss_CV_Audit.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
