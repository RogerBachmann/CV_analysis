import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
from docxtpl import DocxTemplate, RichText

# --- Setup ---
st.set_page_config(page_title="Swiss CV Analyser", layout="wide")

try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    st.error(f"Configuration Error: {e}")
    st.stop()

def extract_pdf_text(file):
    if not file: return ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            return " ".join([page.extract_text() or "" for page in pdf.pages])
    except: return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata parsing
        name = re.search(r"NAME_START:(.*?)NAME_END", report_text, re.S)
        candidate_name = name.group(1).strip() if name else "CANDIDATE"
        
        cat = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat.group(1) if cat else "IMPROVE"

        # Content Scrubbing (Remove all AI markdown symbols)
        body = re.sub(r"NAME_START:.*?NAME_END", "", report_text, flags=re.S)
        body = re.sub(r"CATEGORY:.*?\n", "", body)
        body = body.replace("**", "").replace("__", "").replace("# ", "").strip()

        # Build RichText - This is where we force Calibri and kill Bold
        rt = RichText()
        lines = body.split('\n')
        
        for line in lines:
            clean_line = line.strip()
            if not clean_line:
                # Add a blank line that maintains the "Not Bold" state
                rt.add('\n', font='Calibri', size=24, bold=False)
                continue
            
            # Check if it was meant to be a header (starts with ### in the raw text)
            if "###" in line:
                header_text = line.replace("###", "").strip()
                # Subheaders: Blue, 14pt (Size 28), Explicitly NOT bold
                rt.add(header_text, font='Calibri', size=28, color='2F5496', bold=False)
            else:
                # Body: Black, 12pt (Size 24), Explicitly NOT bold
                rt.add(clean_line, font='Calibri', size=24, color='000000', bold=False)
            
            rt.add('\n', font='Calibri', size=24, bold=False)

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

# --- UI ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

if st.sidebar.text_input("Password", type="password") == st.secrets["APP_PASSWORD"]:
    col1, col2 = st.columns(2)
    
    with col1:
        cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
    
    with col2:
        jd_file = st.file_uploader("Upload Job Description (PDF)", type=["pdf"])
        jd_manual = st.text_area("Or Paste JD text manually", height=100)

    if st.button("🚀 Run Analysis"):
        if not cv_file:
            st.warning("Please upload a CV.")
        else:
            with st.spinner("Analyzing..."):
                cv_raw = extract_pdf_text(cv_file)
                # Combine JD sources
                jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
                
                prompt = f"""
                Analyze this CV for the Swiss Life Sciences market against the JD.
                CV CONTENT: {cv_raw[:9000]}
                JD CONTENT: {jd_raw[:4000] if jd_raw else "General Life Sciences Standards"}

                Strict Format Requirements:
                NAME_START: [Candidate Name] NAME_END
                CATEGORY: [READY/IMPROVE/MAJOR]

                ### 1. SCORECARD
                ### 2. SWISS COMPLIANCE
                ### 3. TECHNICAL ALIGNMENT
                ### 4. PRIORITY ACTIONS

                Constraint: NO Bold (**), NO Italics. Use '###' for headers.
                """
                
                try:
                    res = model.generate_content(prompt)
                    if res and res.text:
                        st.divider()
                        st.markdown(res.text)
                        
                        doc_file = create_word_report(res.text)
                        if doc_file:
                            st.download_button("📩 Download Word Report", doc_file, "Swiss_Audit.docx")
                    else:
                        st.error("AI returned no content. Please try again.")
                except Exception as e:
                    st.error(f"AI Connection Error: {e}")
else:
    st.info("Authenticate in the sidebar to begin.")
