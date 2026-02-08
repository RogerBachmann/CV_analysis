import os
import pdfplumber
import google.generativeai as genai
from datetime import datetime
import re
from collections import Counter

# -------------------------
# API
# -------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# -------------------------
# PDF TEXT EXTRACTION
# -------------------------

def extract_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"
    return text

# -------------------------
# SWISS CV KEYWORD LAYERS
# -------------------------

CORE_TERMS = [
    "gmp","gcp","glp","quality assurance","regulatory affairs",
    "clinical operations","medical affairs","manufacturing",
    "validation","process improvement","compliance","audits"
]

SENIORITY_TERMS = [
    "director","head","senior","lead","principal","global",
    "strategic","budget responsibility","people management",
    "stakeholder management","cross functional"
]

DIGITAL_TERMS = [
    "sap","automation","digital transformation","data driven",
    "process optimisation","lean","six sigma","agile"
]

RESULT_TERMS = [
    "increased","reduced","optimised","delivered","achieved",
    "improved","launched","implemented","led"
]

ALL_STATIC_KEYWORDS = CORE_TERMS + SENIORITY_TERMS + DIGITAL_TERMS + RESULT_TERMS

# -------------------------
# JOB DESCRIPTION KEYWORDS
# -------------------------

def extract_jd_keywords(text, top_n=50):
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    freq = Counter(words)
    common = [w for w,_ in freq.most_common(top_n)]
    return common

# -------------------------
# KEYWORD ANALYSIS
# -------------------------

def keyword_analysis(cv_text, keywords):
    found = []
    missing = []

    lower = cv_text.lower()

    for k in keywords:
        if k in lower:
            found.append(k)
        else:
            missing.append(k)

    return found, missing

# -------------------------
# AI RECRUITER ANALYSIS
# -------------------------

def ai_cv_review(cv_text, jd_text=None):

    jd_section = f"\nTARGET ROLE DESCRIPTION:\n{jd_text}\n" if jd_text else ""

    prompt = f"""
You are a senior Swiss Life Sciences recruiter.

Analyse this CV according to Swiss pharma hiring standards.

Focus on:

1. ATS searchability
2. Keyword strength
3. Seniority clarity
4. Impact vs task listing
5. Leadership signalling
6. Market positioning for Switzerland
7. Alignment to target role if provided

Give:

- Clear strengths
- Critical weaknesses
- Missing strategic elements
- Concrete improvement actions

CV:
{cv_text}

{jd_section}
"""

    response = model.generate_content(prompt)
    return response.text

# -------------------------
# MAIN
# -------------------------

def run_analysis():

    cv_file = input("Enter CV PDF filename: ").strip()

    if not os.path.exists(cv_file):
        print("CV file not found")
        return

    jd_file = input("Enter Job Description PDF (or press Enter to skip): ").strip()

    cv_text = extract_text(cv_file)

    jd_text = None
    keywords = ALL_STATIC_KEYWORDS.copy()

    if jd_file:
        if os.path.exists(jd_file):
            jd_text = extract_text(jd_file)
            jd_keywords = extract_jd_keywords(jd_text)
            keywords.extend(jd_keywords)
        else:
            print("JD file not found. Continuing without JD.")

    found, missing = keyword_analysis(cv_text, keywords)

    ai_feedback = ai_cv_review(cv_text, jd_text)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"Swiss_CV_Analysis_{timestamp}.txt"

    with open(output_file, "w", encoding="utf-8") as f:

        f.write("SWISS CV ANALYSIS\n\n")

        f.write("KEYWORDS FOUND:\n")
        f.write(", ".join(found[:80]) + "\n\n")

        f.write("KEYWORDS MISSING:\n")
        f.write(", ".join(missing[:80]) + "\n\n")

        f.write("RECRUITER REVIEW:\n\n")
        f.write(ai_feedback)

    print(f"Analysis saved as {output_file}")

# -------------------------

if __name__ == "__main__":
    run_analysis()
