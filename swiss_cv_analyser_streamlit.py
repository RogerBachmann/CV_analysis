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
    st.error(f"Error: Secret {e} not found in Streamlit Secrets.")
    st.stop()

# --- Model Setup ---
# Using the most reliable model string for the current Google AI SDK
@st.cache_resource
def get_model():
    # We use 'gemini-1.5-flash' - adding the prefix 'models/' can sometimes cause the 404
    # Safety settings set to BLOCK_NONE to prevent silent errors during analysis
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    return genai.GenerativeModel(model_name="gemini-1.5-flash", safety_settings=safety_settings)

model_instance = get_model()

# --- Helper Functions ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    if file is None: return ""
    text = ""
    try:
        file.seek(0)
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception as e:
        st.error(f"PDF Extraction Error: {e}")
        return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
            return "AI Error: The AI returned an empty response. Check safety filters."
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                time.sleep(10)
                continue
            # Return the specific error to the UI so we can see what's happening
            return f"AI Error: {err_msg}"
    return "AI Error: Failed after 3 retries."

def create_word_report(report_text):
    try:
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "IMPROVE"

        # 2. Body Cleaning (Stripping Bold markdown)
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text)
        clean_body = re.sub(r"CATEGORY:.*?\n", "", clean_body)
        clean_body = clean_body.replace("**", "").replace("__", "").strip()

        # 3. RichText Formatting
        rt = RichText()
        lines = clean_body.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                rt.add('\n', font='Calibri', size=24, bold=False)
                continue
            
            if line.startswith('###') or line.startswith('##'):
                display_text = line.lstrip('#').strip()
                # Subheader: Navy (1D457C), 14pt (Size 28)
                rt.add('\n' + display_text + '\n', font='Calibri', size=28, color='1D457C', bold=True)
            else:
                # Body Text: Black (000000), 12pt (Size 24), EXPLICITLY NOT BOLD
                rt.add(line + '\n', font='Calibri', size=24, color='000000', bold=False)

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

def run_analysis(cv_text, jd_text):
    # Prompt is designed for high consistency and reproducibility
    prompt = f"""
    You are a Senior Swiss Recruiter. Evaluate the CV against the JD. 
    Use a clinical, consistent approach for scoring: 
    Technical (40%), Seniority (20%), Swiss Compliance (20%), Impact/KPIs (20%).

    NAME_START: [Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR]

    INSTRUCTIONS: 
    - NO bold markdown (** or __). 
    - Use '###' for section headers.
    - Be concise and professional.

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100
    Breakdown: [Briefly explain the math per category]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: Swiss recruitment standards expect clear details on Nationality/Permit and Languages.
    Audit: [Compare against Swiss standard]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: Keywords are essential for passing automated ATS screenings in Life Sciences.
    Audit: [Skill match/gap analysis]

    ### 4. PRIORITY ACTION PLAN
    1. [Strategic Action]
    2. [High-Impact Task]

    CV DATA: {cv_text[:6500]}
    JD DATA: {jd_text[:3000] if jd_text else "General Swiss Life Sciences Industry Standard"}
    """
    return call_gemini(prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Enter Admin Password", type="password")
if pass_input != APP_PASSWORD:
    if pass_input: st.sidebar.error("Incorrect Password")
    st.info("Authenticate in the sidebar to begin.")
    st.stop()

st.sidebar.success("✅ Authenticated")

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Upload CV")
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"], key="cv_up")

with col2:
    st.subheader("2. Target Job")
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"], key="jd_up")
    jd_manual = st.text_area("Or paste JD text manually", height=100)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Analyzing..."):
            cv_raw = extract_pdf_text(cv_file)
            
            if jd_file:
                jd_raw = extract_pdf_text(jd_file)
            else:
                jd_raw = clean_text(jd_manual)
            
            if not cv_raw:
                st.error("Text extraction failed.")
            else:
                report = run_analysis(cv_raw, jd_raw)
                
                if "AI Error" not in report:
                    st.divider()
                    st.markdown(report)
                    
                    word_file = create_word_report(report)
                    if word_file:
                        st.download_button(
                            label="📩 Download Branded Word Report",
                            data=word_file,
                            file_name="Swiss_CV_Audit.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                else:
                    st.error(report)
