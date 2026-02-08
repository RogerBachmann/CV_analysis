import streamlit as st
import pdfplumber
import google.generativeai as genai
import re
import io
import time
from docxtpl import DocxTemplate, RichText

# --- Page Configuration ---
st.set_page_config(
    page_title="Swiss Life Sciences CV Analyser", 
    page_icon="🇨🇭", 
    layout="wide"
)

# --- API & Password Setup ---
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
    genai.configure(api_key=GEMINI_API_KEY)
except KeyError as e:
    st.error(f"Error: Secret {e} not found.")
    st.stop()

@st.cache_resource
def get_best_model():
    """Identifies and initializes the best available Gemini model."""
    try:
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        priority = [
            "models/gemini-1.5-flash", 
            "models/gemini-1.5-flash-latest", 
            "models/gemini-pro"
        ]
        for p in priority:
            if p in available_models:
                return genai.GenerativeModel(p)
        return genai.GenerativeModel(available_models[0])
    except Exception:
        return genai.GenerativeModel("models/gemini-1.5-flash")

model_instance = get_best_model()

# --- Helper Functions ---

def clean_text(text):
    """Removes control characters and normalizes whitespace."""
    if not text:
        return ""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_pdf_text(file):
    """Extracts and cleans text from an uploaded PDF file."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content:
                    text += content + " "
        return clean_text(text)
    except Exception:
        return ""

def call_gemini(prompt):
    """Handles API calls to Gemini with basic retry logic for rate limits."""
    if not prompt.strip():
        return ""
    for attempt in range(3):
        try:
            response = model_instance.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e):
                time.sleep(8)
                continue
            return ""
    return ""

def create_word_report(report_text):
    """Parses the AI response and renders it into a branded Word template."""
    try:
        doc = DocxTemplate("template.docx")
        
        # 1. Metadata Extraction
        name_match = re.search(r"NAME_START:(.*?)NAME_END", report_text)
        candidate_name = name_match.group(1).strip() if name_match else "CANDIDATE"
        
        cat_match = re.search(r"CATEGORY:(READY|IMPROVE|MAJOR)", report_text)
        category = cat_match.group(1) if cat_match else "
