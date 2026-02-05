def run_analysis(cv_text, jd_text):
    """Chunks the text and runs the final recruitment analysis with consistency anchors."""
    progress = st.progress(0, text="Swiss Recruiter AI is gathering data...")
    
    cv_summary = call_gemini(f"List key facts: Name, Total years exp, Education, Top 5 Tech Skills, Language levels (GER/ENG/FR), Nationality/Permit: {cv_text[:8000]}")
    progress.progress(0.4)
    
    jd_summary = call_gemini(f"List Top 5 Hard Skills, Minimum Education, and 3 Primary KPIs: {jd_text[:8000]}") if jd_text else "General Life Sciences Industry Standard"
    progress.progress(0.7)

    # The Consistency Anchor Prompt
    final_prompt = f"""
    You are a Senior Swiss Life Sciences Recruiter. Evaluate the CV against the JD. 
    You must be highly consistent. Use the following SCORING RUBRIC to calculate the Overall Fit:
    - Technical Match (40%): How many of the 5 hard skills are present?
    - Experience Level (20%): Does the seniority match?
    - Swiss Compliance (20%): Are permit, language, and photo standard?
    - Impact/KPIs (20%): Are there numbers and results?

    REQUIRED METADATA:
    NAME_START: [Candidate Full Name] NAME_END
    CATEGORY: [READY, IMPROVE, or MAJOR] 

    ### 1. CV PERFORMANCE SCORECARD
    Overall Job-Fit Score: [X]/100 (Explain the math: e.g., Technical 35/40 + Swiss 10/20...)

    ### 2. SWISS COMPLIANCE & FORMATTING
    The Fact: 85% of Swiss HR expect clear mention of Nationality/Work Permit status.
    Audit: [Compare CV against Swiss standards for Photo, Permit, and Personal Data]

    ### 3. TECHNICAL & KEYWORD ALIGNMENT
    The Fact: ATS rejection rates in Life Sciences hit 75% if mandatory keywords are missing.
    Audit: [Direct comparison of CV skills vs JD requirements]

    ### 4. EVIDENCE OF IMPACT (KPIs)
    The Fact: Quantitative metrics increase interview conversion by 40%.
    Audit: [Analysis of bullet points—suggest specific metrics]

    ### 5. PRIORITY ACTION PLAN
    1. [Task]
    2. [Task]

    CV DATA: {cv_summary}
    JD DATA: {jd_summary}
    """
    
    result = call_gemini(final_prompt)
    progress.empty()
    return result
