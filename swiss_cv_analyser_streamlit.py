import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- 1. Page Config (Must be the very first Streamlit command) ---
st.set_page_config(page_title="Swiss Life Sciences CV Analyser", page_icon="🇨🇭", layout="wide")

# --- 2. Safe Secret Loading ---
def load_secrets():
    try:
        return st.secrets["GEMINI_API_KEY"], st.secrets["APP_PASSWORD"]
    except Exception:
        st.error("Missing secrets! Please add GEMINI_API_KEY and APP_PASSWORD to your Streamlit secrets.")
        st.stop()

GEMINI_API_KEY, APP_PASSWORD = load_secrets()
genai.configure(api_key=GEMINI_API_KEY)

# --- 3. Model Logic (Moved out of global cache to prevent hang) ---
def get_model():
    """Returns a model. If specific 2026 names fail, it falls back to a known stable string."""
    try:
        # Priority for 2026: Gemini 2.5 or 3.0
        return genai.GenerativeModel("gemini-2.5-flash")
    except:
        return genai.GenerativeModel("gemini-pro") # Final legacy fallback

# --- 4. Helper Functions ---
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

def call_gemini(model, prompt):
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error: {str(e)}"

# --- 5. UI Logic ---
st.title("🇨🇭 Swiss CV & Job Fit Analyser")

# Sidebar Authentication
with st.sidebar:
    st.header("Admin Access")
    pass_input = st.text_input("Password", type="password")
    
if pass_input != APP_PASSWORD:
    st.info("Please enter the password in the sidebar to begin.")
    st.stop()

# File Uploaders
cv_file = st.file_uploader("Upload CV (PDF)", type=["pdf"])
jd_file = st.file_uploader("Upload JD (PDF)", type=["pdf"])
jd_manual = st.text_area("Or paste JD text", height=100)

if st.button("🚀 Run Analysis"):
    if not cv_file:
        st.warning("Please upload a CV.")
    else:
        with st.spinner("Initializing AI and Analyzing..."):
            # Initialize model ONLY when button is clicked
            active_model = get_model()
            
            cv_raw = extract_pdf_text(cv_file)
            jd_raw = extract_pdf_text(jd_file) if jd_file else jd_manual
            
            if not cv_raw:
                st.error("Could not read CV content.")
            else:
                # Direct simple prompt to test connection
                report = call_gemini(active_model, f"Analyze this CV against the JD. CV: {cv_raw[:4000]} JD: {jd_raw[:2000]}")
                
                st.divider()
                st.markdown(report)
