import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- 1. SETUP ---
st.set_page_config(page_title="Swiss CV Analyser", page_icon="🇨🇭")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # Using the most standard, no-prefix model name
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.stop()

# --- 2. CORE FUNCTIONS ---
def extract_text(file):
    """Simple extraction: if no file, return empty string."""
    if file is None:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            text = " ".join([p.extract_text() for p in pdf.pages if p.extract_text()])
            return text.strip()
    except:
        return ""

def call_gemini(prompt):
    """Direct API call with a simple retry for rate limits."""
    if not prompt:
        return ""
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        if "429" in str(e):
            time.sleep(10)
            return model.generate_content(prompt).text.strip()
        st.error(f"API Error: {e}")
        return ""

# --- 3. UI LAYOUT ---
st.title("🇨🇭 Swiss CV Analyser")

# Sidebar Authentication
if st.sidebar.text_input("Password", type="password") != st.secrets["APP_PASSWORD"]:
    st.info("Please enter password in sidebar.")
    st.stop()

# Uploaders with explicit keys to prevent UI hanging
cv_file = st.file_uploader("1. Upload CV (PDF)", type=["pdf"], key="cv_key")
jd_file = st.file_uploader("2. Upload JD (PDF)", type=["pdf"], key="jd_key")
jd_text = st.text_area("3. OR Paste JD Text", height=100, key="txt_key")

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            # A. Get CV Text
            cv_raw = extract_text(cv_file)
            
            # B. Get JD Text (Priority: Uploader > Text Area)
            jd_raw = extract_text(jd_file) if jd_file else jd_text

            if not cv_raw:
                st.error("Error: Could not extract text from the CV.")
                st.stop()

            # C. Phase 1: CV Summary
            cv_info = call_gemini(f"List skills and experience from this CV: {cv_raw[:6000]}")
            if not cv_info:
                st.stop()
            
            time.sleep(2) # Brief pause to avoid burst limit

            # D. Phase 2: Final Report
            report = call_gemini(f"""
                Swiss Life Sciences Recruiter Mode. 
                Match this CV: {cv_info}
                To this JD: {jd_raw[:4000]}
                Format: NAME_START: [Name] NAME_END, CATEGORY: [READY/IMPROVE/MAJOR], then full audit.
            """)

            if report:
                st.divider()
                st.markdown(report)
                
                # E. Word Report Generation
                try:
                    doc = DocxTemplate("template.docx")
                    name_match = re.search(r"NAME_START:(.*?)NAME_END", report)
                    name = name_match.group(1).strip() if name_match else "CANDIDATE"
                    
                    rt = RichText()
                    # Remove the metadata tags for the final Word document
                    clean_content = re.sub(r"NAME_START:.*?NAME_END", "", report).strip()
                    rt.add(clean_content)
                    
                    doc.render({'CANDIDATE_NAME': name.upper(), 'REPORT_CONTENT': rt})
                    out = io.BytesIO()
                    doc.save(out)
                    st.download_button("📩 Download Word Report", out.getvalue(), "CV_Audit.docx")
                except Exception as e:
                    st.error(f"Word Error: {e}")
