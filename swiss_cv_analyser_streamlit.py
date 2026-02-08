import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- Setup ---
st.set_page_config(page_title="Swiss CV Analyser", page_icon="🇨🇭")

# 1. Direct Configuration (No loops, no fluff)
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.error(f"Config Error: {e}")
    st.stop()

# --- Functions ---
def extract_text(file):
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            return " ".join([p.extract_text() for p in pdf.pages if p.extract_text()])
    except:
        return ""

def call_gemini(prompt):
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        # If rate limited, wait and try exactly once more
        if "429" in str(e):
            time.sleep(12)
            return model.generate_content(prompt).text.strip()
        # Output the actual error to screen if it fails
        st.error(f"API Error: {e}")
        return ""

# --- UI ---
st.title("🇨🇭 Swiss CV Analyser")

if st.sidebar.text_input("Password", type="password") != st.secrets["APP_PASSWORD"]:
    st.stop()

cv_file = st.file_uploader("Upload CV", type=["pdf"])
jd_text = st.text_area("Paste JD")

if st.button("🚀 Run Analysis"):
    if cv_file:
        with st.spinner("Processing..."):
            # 1. Extraction
            cv_raw = extract_text(cv_file)
            if not cv_raw:
                st.error("Could not read PDF text.")
                st.stop()

            # 2. Step 1: Summary (Sequential)
            cv_info = call_gemini(f"Extract skills and facts: {cv_raw[:6000]}")
            if not cv_info: st.stop()
            
            time.sleep(3) # Small gap to prevent burst errors

            # 3. Step 2: Comparison
            report = call_gemini(f"""
                Senior Swiss Recruiter Mode. 
                CV: {cv_info}
                JD: {jd_text[:4000]}
                Format: NAME_START: [Name] NAME_END, CATEGORY: [READY/IMPROVE/MAJOR], then audit.
            """)

            if report:
                st.markdown(report)
                
                # Word Generation
                try:
                    doc = DocxTemplate("template.docx")
                    name_match = re.search(r"NAME_START:(.*?)NAME_END", report)
                    name = name_match.group(1).strip() if name_match else "CANDIDATE"
                    
                    rt = RichText()
                    rt.add(re.sub(r"NAME_START:.*?NAME_END", "", report).strip())
                    
                    doc.render({'CANDIDATE_NAME': name.upper(), 'REPORT_CONTENT': rt})
                    out = io.BytesIO()
                    doc.save(out)
                    st.download_button("📩 Download Word", out.getvalue(), "Audit.docx")
                except Exception as e:
                    st.error(f"Word Error: {e}")
    else:
        st.warning("Please upload a CV.")
