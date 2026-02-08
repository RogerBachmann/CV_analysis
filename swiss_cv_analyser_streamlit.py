import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- Configuration ---
st.set_page_config(page_title="Swiss CV Analyser", page_icon="🇨🇭")

# --- API Connection ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    # We try THREE specific model strings in order of stability. 
    # If one works, we stop.
    working_model = None
    for model_name in ["gemini-1.5-flash", "gemini-flash-latest", "gemini-1.5-pro"]:
        try:
            test_model = genai.GenerativeModel(model_name)
            # Minimal 'ping' to see if it's alive
            test_model.generate_content("ping", generation_config={"max_output_tokens": 1})
            working_model = test_model
            break
        except:
            continue
            
    if not working_model:
        st.error("Google API rejected all model names (404). Check AI Studio for a new key.")
        st.stop()
except Exception as e:
    st.error(f"Setup Error: {e}")
    st.stop()

# --- Functions ---
def extract_pdf_text(file):
    if not file: return ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            return " ".join([page.extract_text() or "" for page in pdf.pages]).strip()
    except: return ""

def call_api(prompt, label="API Task"):
    try:
        response = working_model.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        return "Error: Empty response from AI."
    except Exception as e:
        if "429" in str(e):
            st.warning(f"Rate limited on {label}. Waiting 15s...")
            time.sleep(15)
            return working_model.generate_content(prompt).text.strip()
        st.error(f"{label} failed: {e}")
        return ""

def create_word_report(text):
    try:
        doc = DocxTemplate("template.docx")
        name = re.search(r"NAME_START:(.*?)NAME_END", text)
        candidate = name.group(1).strip() if name else "CANDIDATE"
        
        # Strip identifiers for the document body
        clean_text = re.sub(r"NAME_START:.*?NAME_END", "", text)
        clean_text = re.sub(r"CATEGORY:.*?\n", "", clean_text).replace("**", "")
        
        rt = RichText()
        rt.add(clean_text, font='Calibri', size=24)
        doc.render({'CANDIDATE_NAME': candidate.upper(), 'REPORT_CONTENT': rt})
        
        bio = io.BytesIO()
        doc.save(bio)
        return bio.getvalue()
    except Exception as e:
        st.error(f"Word Export Error: {e}")
        return None

# --- UI ---
st.title("🇨🇭 Swiss CV Analyser")

if st.sidebar.text_input("Password", type="password") != st.secrets["APP_PASSWORD"]:
    st.info("Enter password in sidebar to start.")
    st.stop()

cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_input = st.text_area("Paste JD Text")

if st.button("🚀 Analyze Now"):
    if not cv_file:
        st.warning("Upload a CV first.")
    else:
        with st.spinner("Processing..."):
            cv_raw = extract_pdf_text(cv_file)
            
            # Phase 1: Summary
            cv_summary = call_api(f"Summarize skills and experience: {cv_raw[:6000]}", "CV Analysis")
            time.sleep(5) # Prevent 429
            
            # Phase 2: Audit
            prompt = f"""
            You are a Swiss Life Sciences Recruiter.
            Analyze this CV: {cv_summary} 
            Against this JD: {jd_input[:4000]}
            
            Output MUST include:
            NAME_START: [Name] NAME_END
            CATEGORY: [READY, IMPROVE, or MAJOR]
            Then a full scorecard and audit.
            """
            final_report = call_api(prompt, "Final Audit")
            
            if final_report:
                st.markdown(final_report)
                file_data = create_word_report(final_report)
                if file_data:
                    st.download_button("📩 Download Word Report", file_data, "CV_Audit.docx")
