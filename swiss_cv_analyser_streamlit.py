import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- 1. Page Config ---
st.set_page_config(page_title="Swiss CV Analyser PRO", page_icon="🇨🇭", layout="wide")

# --- 2. API Key Rotation Logic ---
def configure_genai(key_index=1):
    """Switches between Primary and Backup keys."""
    try:
        key_name = "GEMINI_API_KEY" if key_index == 1 else "GEMINI_API_KEY_2"
        api_key = st.secrets.get(key_name)
        if api_key:
            genai.configure(api_key=api_key)
            return True
        return False
    except:
        return False

# Initial config with primary key
configure_genai(1)

def get_model():
    # 2026 Stable model name
    return genai.GenerativeModel("gemini-2.0-flash")

# --- 3. Text Extraction ---
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

# --- 4. Smart Analysis with Failover ---
def run_analysis_with_failover(cv_text, jd_text):
    prompt = f"""
    Evaluate this CV against the JD. Use '###' for headers. No bold (**).
    NAME_START: [Candidate Name] NAME_END
    CATEGORY: [READY/IMPROVE/MAJOR]
    
    ### 1. PERFORMANCE SCORECARD
    ### 2. SWISS COMPLIANCE
    ### 3. TECHNICAL ALIGNMENT
    ### 4. IMPACT & KPIs
    ### 5. PRIORITY ACTION PLAN

    CV: {cv_text[:7000]}
    JD: {jd_text[:3000]}
    """
    
    # Try Primary Key
    try:
        model = get_model()
        response = model.generate_content(prompt)
        return response.text.strip(), "Primary"
    except Exception as e:
        if "429" in str(e):
            # Try Backup Key
            st.warning("🔄 Primary Quota Full. Switching to Backup Account...")
            if configure_genai(2):
                try:
                    model = get_model()
                    response = model.generate_content(prompt)
                    return response.text.strip(), "Backup"
                except Exception as e2:
                    return f"ERROR: Both accounts exhausted for today. Reset at 15:00 Hanoi time. Details: {e2}", "None"
            else:
                return "ERROR: Primary exhausted and no Backup Key found in secrets.", "None"
        return f"API Error: {e}", "None"

# --- 5. Word Export (Unchanged logic) ---
def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        cand_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"
        
        rt = RichText()
        clean_text = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_text = re.sub(r"CATEGORY:.*?\n", "", clean_text).replace("**", "")
        
        for line in clean_text.split('\n'):
            line = line.strip()
            if line.startswith('###'):
                rt.add(line.replace('###', '').strip(), font='Calibri', size=28, color='1D457C')
            else:
                rt.add(line, font='Calibri', size=24, color='E7E6E6')
            rt.add('\n')

        context = {
            'CANDIDATE_NAME': cand_name.upper(),
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
    except: return None

# --- 6. Main UI ---
st.title("🇨🇭 Swiss CV Analyser (Dual-Key Mode)")

with st.sidebar:
    pass_input = st.text_input("Password", type="password")
    if pass_input != st.secrets.get("APP_PASSWORD"):
        st.info("Enter password to start")
        st.stop()
    st.success("Authenticated")

cv_file = st.file_uploader("Upload CV", type=["pdf"])
jd_file = st.file_uploader("Upload JD", type=["pdf"])

if st.button("🚀 Run Analysis"):
    if cv_file:
        with st.spinner("Processing with dual-account failover..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else "Standard Swiss Life Sciences JD"
            
            report, source = run_analysis_with_failover(cv_raw, jd_raw)
            
            if "ERROR" in report:
                st.error(report)
            else:
                st.caption(f"Used {source} Account")
                st.markdown(report)
                word_file = create_word_report(report)
                if word_file:
                    st.download_button("📩 Download Report", word_file, "Audit.docx")
