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
    st.error(f"Secret {e} missing.")
    st.stop()

# Using a more stable model string
model_instance = genai.GenerativeModel("gemini-1.5-flash-latest")

# --- Helper Functions ---

def clean_text(text):
    if not text: return ""
    # Remove non-printable characters and collapse whitespace
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            # Only take first 3 pages to save tokens/rate limit
            for page in pdf.pages[:3]:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception:
        return ""

def call_gemini(prompt, label="Task"):
    """Forceful sequential execution."""
    if not prompt.strip(): return ""
    
    # Add a tiny pre-emptive sleep to separate calls from other browser refreshes
    time.sleep(1)
    
    try:
        response = model_instance.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        if "429" in str(e):
            st.warning(f"⚠️ {label} hit a speed bump. Resting for 15s...")
            time.sleep(15)
            # Last ditch effort
            try:
                response = model_instance.generate_content(prompt)
                return response.text.strip()
            except:
                st.error("Google's Free Tier is too busy. Try again in 1 minute.")
        else:
            st.error(f"API Error ({label}): {e}")
    return ""

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # Metadata
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"
        
        # Clean Body
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body).replace("**", "").strip()
        
        rt = RichText()
        for line in clean_body.split('\n'):
            line = line.strip()
            if not line:
                rt.add('\n')
            elif line.startswith('###'):
                rt.add('\n' + line.lstrip('#').strip() + '\n', font='Calibri', size=28, color='1D457C')
            else:
                rt.add(line + '\n', font='Calibri', size=24, color='000000') # Fixed color to black

        doc.render({
            'CANDIDATE_NAME': candidate_name.upper(), 
            'REPORT_CONTENT': rt,
            'REC_READY': "✅" if category == "READY" else "⬜",
            'REC_IMPROVE': "✅" if category == "IMPROVE" else "⬜",
            'REC_MAJOR': "✅" if category == "MAJOR" else "⬜"
        })
        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return bio
    except Exception as e:
        st.error(f"Word Error: {e}")
        return None

def run_analysis(cv_text, jd_text):
    # REDUCED CHUNKS: Sending less text is the #1 way to stop 429 errors
    cv_input = cv_text[:4000]
    jd_input = jd_text[:3000]

    # Step 1
    st.write("🏃 Step 1/3: Reading CV...")
    cv_summary = call_gemini(f"List key facts/skills: {cv_input}", "CV-Summary")
    if not cv_summary: return ""
    
    # Step 2
    time.sleep(3) 
    st.write("🏃 Step 2/3: Reading JD...")
    jd_summary = call_gemini(f"List requirements: {jd_input}", "JD-Summary") if jd_text else "General"
    if not jd_summary: return ""
    
    # Step 3
    time.sleep(3)
    st.write("🏃 Step 3/3: Final Audit...")
    final_prompt = f"""
    Senior Swiss Recruiter Mode.
    NAME_START: [Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]
    ### 1. SCORECARD
    Score: [X]/100
    ### 2. AUDIT
    Review: ...
    CV: {cv_summary}
    JD: {jd_summary}
    """
    return call_gemini(final_prompt, "Final-Audit")

# --- UI ---
st.title("🇨🇭 Swiss CV Analyser")

pass_input = st.sidebar.text_input("Password", type="password")
if pass_input != APP_PASSWORD:
    st.stop()

cv_file = st.file_uploader("Upload CV", type=["pdf"])
jd_file = st.file_uploader("Upload JD", type=["pdf"])
jd_manual = st.text_area("Or Paste JD")

if st.button("🚀 Analyze Now"):
    if not cv_file:
        st.warning("Upload CV.")
    else:
        with st.spinner("Processing..."):
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            report = run_analysis(cv_raw, jd_raw)
            if report:
                st.markdown(report)
                word = create_word_report(report)
                if word:
                    st.download_button("📩 Download Word", word, "Audit.docx")
                    
