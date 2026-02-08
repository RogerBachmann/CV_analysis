import streamlit as st
import pdfplumber
import google.generativeai as genai
from textwrap import wrap
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
    st.error(f"Error: Secret {e} not found. Please check your .streamlit/secrets.toml file.")
    st.stop()

@st.cache_resource
def get_best_model():
    try:
        # Prioritize standard stable models
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        priority = ["models/gemini-1.5-flash", "models/gemini-1.5-flash-latest", "models/gemini-pro"]
        for p in priority:
            if p in available_models: return genai.GenerativeModel(p)
        return genai.GenerativeModel(available_models[0])
    except Exception:
        return genai.GenerativeModel("models/gemini-1.5-flash")

model_instance = get_best_model()

# --- Helper Functions ---

def clean_text(text):
    if not text: return ""
    # Remove non-printable characters
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    # Collapse multiple spaces
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content: text += content + " "
        return clean_text(text)
    except Exception: return ""

def call_gemini(prompt):
    if not prompt.strip(): return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e): # Rate limit handling
                time.sleep(4)
                continue
            return ""
    return ""

def create_word_report(report_text):
    """
    Generates a Word doc with strict formatting:
    - Headers: 13pt (Size 26), Color 2F5496, No Bold
    - Body: 12pt (Size 24), Color 000000, No Bold
    """
    try:
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction
        # We look for the metadata tags provided in the prompt
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text, re.DOTALL | re.IGNORECASE)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:\s*(READY|IMPROVE|MAJOR)", report_text, re.IGNORECASE)
        category = cat_match.group(1).upper() if cat_match else "IMPROVE"

        # 2. Body Cleaning
        # Remove the metadata tags so they don't show up in the document
        clean_body = re.sub(r"NAME_START:.*?NAME_END", "", report_text, flags=re.DOTALL)
        clean_body = re.sub(r"CATEGORY:.*", "", clean_body)
        
        # Strip bold markdown (**) and italic (*) to ensure plain text 
        clean_body = clean_body.replace("**", "").replace("* ", "• ") 

        # 3. Build RichText
        rt = RichText()
        
        # Split by newline to process headers vs body
        lines = [line.strip() for line in clean_body.split('\n')]
        
        for line in lines:
            if not line:
                # Add a blank line for spacing, using body size (24)
                rt.add('\n', size=24)
                continue
            
            # Identify Headers (The prompt uses ### or ##)
            if line.startswith('#'):
                # Clean the hash marks
                display_text = line.lstrip('#').strip()
                
                # Add Header: 13pt = Size 26, Color = 2F5496 (Blue)
                # We add \n before to ensure separation
                rt.add('\n' + display_text + '\n', font='Calibri', size=26, color='2F5496', bold=False)
            
            else:
                # Body Text: 12pt = Size 24, Color = 000000 (Black)
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
    # 1. Summarization step to handle token limits
    cv_summary = call_gemini(f"Extract key career facts, technical skills, and achievements (max 800 words): {cv_text[:15000]}")
    jd_summary = call_gemini(f"Extract core requirements and KPIs: {jd_text[:15000]}") if jd_text else "General Standard"

    # 2. Final Analysis Prompt
    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate this CV against the JD.
    
    METADATA INSTRUCTIONS (Required for parsing):
    1. Start the response EXACTLY with: NAME_START: [Candidate Name] NAME_END
    2. Then, on a new line: CATEGORY: [READY, IMPROVE, or MAJOR]
    
    FORMATTING INSTRUCTIONS:
    - Use '###' for section headers.
    - Do NOT use bold markdown (**). 
    - Do NOT use a main title (start directly with section 1).
    - Write in clear, professional paragraphs or bullet points using '•'.

    CONTENT STRUCTURE:
    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [Score]/100
    [Brief explanation]

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: [Objective observation]
    Audit: [Critique]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: [Objective observation]
    Audit: [Critique]

    ### 4. EVIDENCE OF IMPACT (KPIs)
    The Fact: [Objective observation]
    Audit: [Critique]

    ### 5. PRIORITY ACTION PLAN
    1. [Action 1]
    2. [Action 2]

    DATA:
    CV SUMMARY: {cv_summary}
    JD SUMMARY: {jd_summary}
    """
    return call_gemini(final_prompt)

# --- UI Interface ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

pass_input = st.sidebar.text_input("Enter Admin Password", type="password")

if pass_input == APP_PASSWORD:
    cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
    jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
    jd_manual = st.text_area("Or paste JD text manually", height=150)

    if st.button("🚀 Run Analysis"):
        if not cv_file:
            st.warning("Please upload a CV.")
        else:
            with st.spinner("Analyzing..."):
                # Reset file pointer if needed, but pdfplumber usually handles it
                cv_file.seek(0)
                if jd_file: jd_file.seek(0)

                cv_raw = extract_pdf_text(cv_file)
                jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
                
                if not cv_raw:
                    st.error("CV Extraction failed. The PDF might be an image scan.")
                else:
                    report = run_analysis(cv_raw, jd_raw)
                    
                    st.divider()
                    st.markdown("### Analysis Preview")
                    # Remove metadata for preview
                    preview_text = re.sub(r"NAME_START:.*?NAME_END", "", report, flags=re.DOTALL)
                    preview_text = re.sub(r"CATEGORY:.*", "", preview_text)
                    st.markdown(preview_text)
                    
                    word_file = create_word_report(report)
                    
                    if word_file:
                        st.download_button(
                            label="📩 Download Word Report",
                            data=word_file,
                            file_name=f"Swiss_CV_Audit.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
else:
    st.info("Please enter the password in the sidebar to access the tool.")
