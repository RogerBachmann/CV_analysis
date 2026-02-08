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

        # Content Scrubbing
        body = re.sub(r"NAME_START:.*?NAME_END", "", report_text, flags=re.S)
        body = re.sub(r"CATEGORY:.*?\n", "", body)
        body = body.replace("**", "").replace("__", "").strip()

        # Build RichText - Force Calibri and No Bold on every segment
        rt = RichText()
        for line in body.split('\n'):
            clean_line = line.strip()
            if not clean_line:
                rt.add('\n', font='Calibri', size=24, bold=False)
                continue
            
            if clean_line.startswith('###') or clean_line.startswith('##'):
                # Subheaders: Blue, 14pt (28), No Bold
                rt.add(clean_line.lstrip('#').strip(), font='Calibri', size=28, color='2F5496', bold=False)
            else:
                # Body: Black, 12pt (24), No Bold
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
        st.error(f"Word Error: {e}")
        return None

# --- UI ---
st.title("🇨🇭 Swiss CV Analyser")

pw = st.sidebar.text_input("Password", type="password")
if pw == st.secrets["APP_PASSWORD"]:
    cv_file = st.file_uploader("Upload CV", type=["pdf"])
    jd_text = st.text_area("Job Description", height=150)

    if st.button("🚀 Analyze"):
        if not cv_file:
            st.warning("Upload a CV first.")
        else:
            with st.spinner("Analyzing..."):
                cv_raw = extract_pdf_text(cv_file)
                
                # Single prompt to guarantee output and format
                prompt = f"""
                Analyze this CV for the Swiss Life Sciences market against the JD.
                CV: {cv_raw[:9000]}
                JD: {jd_text[:4000]}

                Strict Format:
                NAME_START: [Name] NAME_END
                CATEGORY: [READY/IMPROVE/MAJOR]

                ### 1. SCORECARD
                [Score]/100
                ### 2. SWISS COMPLIANCE
                [Audit]
                ### 3. TECHNICAL FIT
                [Mapping]
                ### 4. ACTION PLAN
                - [Action]

                Rules: NO Bold (**), NO Italics. Use '###' for headers.
                """
                
                try:
                    res = model.generate_content(prompt)
                    if res and res.text:
                        st.markdown(res.text)
                        doc_file = create_word_report(res.text)
                        if doc_file:
                            st.download_button("📩 Download Report", doc_file, "Swiss_Audit.docx")
                    else:
                        st.error("AI returned no text. Try again.")
                except Exception as e:
                    st.error(f"AI Error: {e}")
