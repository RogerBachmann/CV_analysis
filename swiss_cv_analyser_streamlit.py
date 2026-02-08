import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- Page Config ---
st.set_page_config(page_title="Swiss CV Analyser", page_icon="🇨🇭")

# --- API Setup ---
try:
    # Ensure the API Key is set
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    
    # This list covers all naming conventions (with and without prefixes)
    # The code will stop at the FIRST one that doesn't 404.
    MODEL_NAMES = [
        "gemini-1.5-flash", 
        "gemini-1.5-flash-latest", 
        "models/gemini-1.5-flash",
        "gemini-pro"
    ]
    
    working_model = None
    for name in MODEL_NAMES:
        try:
            m = genai.GenerativeModel(name)
            # Short test call
            m.generate_content("test", generation_config={"max_output_tokens": 1})
            working_model = m
            break 
        except:
            continue

    if not working_model:
        st.error("Connection Failed: All model variants returned 404. Please generate a NEW API Key at aistudio.google.com.")
        st.stop()
except Exception as e:
    st.error(f"Initialization Error: {e}")
    st.stop()

# --- Core Logic Functions ---
def extract_text(file):
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            return " ".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    except: return ""

def call_ai(prompt):
    try:
        # Standard call with no complex parameters to minimize errors
        res = working_model.generate_content(prompt)
        return res.text.strip()
    except Exception as e:
        if "429" in str(e):
            time.sleep(15)
            return working_model.generate_content(prompt).text.strip()
        return ""

def generate_docx(report_text):
    try:
        doc = DocxTemplate("template.docx")
        name_search = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        name = name_search.group(1).strip() if name_search else "CANDIDATE"
        
        # Strip markers for the final document
        body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        body = re.sub(r"CATEGORY:.*?\n", "", body).replace("**", "").strip()
        
        rt = RichText()
        rt.add(body, font='Calibri', size=24)
        doc.render({'CANDIDATE_NAME': name.upper(), 'REPORT_CONTENT': rt})
        
        out = io.BytesIO()
        doc.save(out)
        return out.getvalue()
    except: return None

# --- UI Layout ---
st.title("🇨🇭 Swiss CV Analyser")

# Sidebar Auth
if st.sidebar.text_input("Password", type="password") != st.secrets["APP_PASSWORD"]:
    st.stop()

cv_up = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_up = st.text_area("Paste JD")

if st.button("🚀 Run Analysis"):
    if cv_up:
        with st.spinner("Analyzing..."):
            cv_raw = extract_text(cv_up)
            
            # Step 1: Summary (keeps payload small to avoid 429)
            cv_sum = call_ai(f"Summary of CV: {cv_raw[:5000]}")
            time.sleep(5)
            
            # Step 2: Final Report
            report = call_ai(f"""
                Swiss Recruiter Mode. 
                Match this CV: {cv_sum} 
                To this JD: {jd_up[:4000]}
                Format: NAME_START: [Name] NAME_END, CATEGORY: [READY/IMPROVE/MAJOR], then full audit.
            """)
            
            if report:
                st.markdown(report)
                docx_data = generate_docx(report)
                if docx_data:
                    st.download_button("📩 Download Report", docx_data, "Audit.docx")
    else:
        st.warning("Please upload a CV.")
