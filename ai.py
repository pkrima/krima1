import json
import os
import re

from dotenv import dotenv_values, load_dotenv

load_dotenv()

SYSTEM_INSTRUCTION = (
    "You are an elite career strategist and technical recruiter. "
    "Analyze the candidate's resume thoroughly against their target role. "
    "Return a valid JSON object with exactly four array fields: "
    "1. 'skills': Specific strengths, technologies, tools, and experiences explicitly identified in the candidate's resume. "
    "2. 'missing_skills': Critical skills, concepts, tools, or domain experience needed for the target role that are missing or weak in the resume. "
    "3. 'roadmap': Concrete, phased steps (courses, portfolio projects to build, certifications, or open-source work) to bridge the gap and become hireable. "
    "4. 'interview_questions': 4-6 challenging, role-specific technical and behavioral interview questions tailored to their background and target position."
)

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _get_config_value(key_name, default=""):
    file_vals = dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    val = (file_vals.get(key_name) or os.environ.get(key_name) or "").strip()
    return val or default


def _validate_analysis_result(result):
    if not isinstance(result, dict):
        raise ValueError("The AI API returned an invalid analysis format.")

    for field in ("skills", "missing_skills", "roadmap", "interview_questions"):
        items = result.get(field)
        if not isinstance(items, list):
            raise ValueError(f"The AI API response is missing a valid '{field}' list.")
    return result


def _analyze_with_gemini(api_key, resume_text, user_goal):
    import time
    from google import genai
    from google.genai import types
    from pydantic import BaseModel

    class CareerAnalysis(BaseModel):
        skills: list[str]
        missing_skills: list[str]
        roadmap: list[str]
        interview_questions: list[str]

    client = genai.Client(api_key=api_key)
    prompt = (
        f"Analyze this resume for the target role: {user_goal}\n\n"
        f"Resume:\n{resume_text}"
    )

    preferred_model = _get_config_value("GEMINI_MODEL", "gemini-2.0-flash")
    candidate_models = [preferred_model, "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    models_to_try = []
    for m in candidate_models:
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=CareerAnalysis,
                    temperature=0.7,
                ),
            )
            content = response.text
            if not content:
                raise ValueError("The AI API returned an empty analysis.")
            result = json.loads(content)
            return _validate_analysis_result(result)
        except Exception as exc:
            last_error = exc
            err_msg = str(exc).lower()
            if "429" in err_msg or "resource_exhausted" in err_msg or "quota" in err_msg:
                time.sleep(1.5)
            continue

    raise last_error


def _analyze_with_openai(api_key, resume_text, user_goal):
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=_get_config_value("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.7,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": SYSTEM_INSTRUCTION,
            },
            {
                "role": "user",
                "content": (
                    f"Analyze this resume for the target role: {user_goal}\n\n"
                    f"Resume:\n{resume_text}"
                ),
            },
        ],
    )

    content = response.choices[0].message.content
    if not content:
        raise ValueError("The AI API returned an empty analysis.")

    result = json.loads(content)
    return _validate_analysis_result(result)


def _analyze_resume_smart(resume_text, user_goal):
    """
    Intelligent resume parsing and career advisory engine.
    Extracts actual competencies, detects missing skills for the target role,
    builds a phased career roadmap, and generates role-specific interview questions.
    """
    SKILL_MAP = {
        "Generative AI & LLMs": r"\b(?:generative\s+ai|gen\s*ai|llm|llms|large\s+language\s+models?)\b",
        "Prompt Engineering": r"\bprompt\s+engineering\b",
        "Python (OOP, Automation)": r"\bpython\b",
        "Pandas & NumPy": r"\b(?:pandas|numpy)\b",
        "Java": r"\bjava\b",
        "SQL & Database Design": r"\b(?:sql|mysql|postgresql|sqlite)\b",
        "React.js": r"\breact(?:\.js)?\b",
        "JavaScript (ES6+)": r"\b(?:javascript|js)\b",
        "HTML5 & CSS3": r"\b(?:html5?|css3?)\b",
        "Node.js & Express": r"\b(?:node(?:\.js)?|express(?:\.js)?)\b",
        "FastAPI & Flask": r"\b(?:fastapi|flask)\b",
        "Django": r"\bdjango\b",
        "TypeScript": r"\btypescript\b",
        "Git & GitHub Version Control": r"\b(?:git|github|gitlab)\b",
        "Docker & Containerization": r"\bdocker\b",
        "Cloud Services (AWS / GCP / Azure)": r"\b(?:aws|azure|gcp|google\s+cloud|cloud)\b",
        "UI/UX Prototyping (Figma)": r"\bfigma\b",
        "REST APIs & Web Services": r"\b(?:rest|restful|api|apis)\b",
        "Machine Learning": r"\b(?:machine\s+learning|ml|scikit-learn)\b",
        "Data Structures & Algorithms": r"\b(?:data\s+structures|algorithms|oop|object\s+oriented)\b",
    }

    found_skills = []
    for skill_name, pattern in SKILL_MAP.items():
        if re.search(pattern, resume_text, re.IGNORECASE):
            found_skills.append(skill_name)

    if not found_skills:
        found_skills = [
            "Core Programming & Software Development Foundations",
            "Technical Problem Solving and Algorithmic Thinking",
            "Code Version Control & Git Collaboration",
        ]

    # Detect projects from resume
    ignore_headers = {
        "programming", "skills", "technical skills", "education", "experience",
        "certifications", "training", "languages", "ai & data", "web", "design & tools"
    }
    detected_projects = []
    for line in resume_text.splitlines():
        clean = line.strip().lstrip("•-* \t").strip()
        if ":" in clean:
            left, right = clean.split(":", 1)
            left_clean = left.strip()
            if left_clean.lower() in ignore_headers:
                continue
            if any(w in left_clean.lower() for w in ["clone", "portfolio", "app", "site", "system", "project", "program", "tool", "website"]):
                if len(left_clean) <= 45:
                    detected_projects.append((left_clean, right.strip()))
        elif any(w in clean.lower() for w in ["clone", "portfolio", "app", "system"]) and len(clean) <= 45:
            if clean.lower() not in ignore_headers:
                detected_projects.append((clean, ""))

    # Determine Missing Skills based on target role
    goal_lower = user_goal.lower()
    missing_skills = []

    if any(k in goal_lower for k in ["full stack", "fullstack", "web", "frontend", "backend", "software"]):
        if not any("FastAPI" in s or "Node" in s or "Django" in s for s in found_skills):
            missing_skills.append("Backend Frameworks (e.g. FastAPI, Express.js, or Django) for production RESTful APIs")
        if not any("TypeScript" in s for s in found_skills):
            missing_skills.append("TypeScript for type-safe frontend and backend enterprise applications")
        if not any("Docker" in s for s in found_skills):
            missing_skills.append("Docker containerization & CI/CD deployment pipelines (GitHub Actions)")
        if not any("Cloud" in s for s in found_skills):
            missing_skills.append("Cloud Architecture (AWS, Render, or Vercel serverless functions & PostgreSQL)")

    elif any(k in goal_lower for k in ["ai", "gen", "machine learning", "ml", "data"]):
        missing_skills.append("LangChain / LlamaIndex framework for building multi-step LLM pipelines and RAG systems")
        missing_skills.append("Vector Databases (Pinecone, ChromaDB, or Weaviate) for semantic search & retrieval")
        missing_skills.append("LLM Evaluation, guardrails, and latency optimization to prevent hallucinations")
        missing_skills.append("Model serving APIs (FastAPI) containerized with Docker for real-time inference")

    if len(missing_skills) < 3:
        missing_skills.append(f"Production-grade architecture patterns and state management tailored to {user_goal}")
        missing_skills.append(f"Automated unit & integration test suites (pytest / Jest) for {user_goal} codebases")
        missing_skills.append(f"Advanced system design principles (caching, database indexing, rate limiting) for {user_goal}")

    # Build actionable roadmap
    proj_mention = detected_projects[0][0] if detected_projects else "your current projects"
    roadmap = [
        f"Phase 1 (Backend Mastery): Connect your frontend expertise with a robust Python (FastAPI/Flask) or Node.js backend linked to a SQL database.",
        f"Phase 2 (End-to-End Showcase): Upgrade '{proj_mention}' or build a new full-stack application combining your Generative AI knowledge with full-stack CRUD capabilities.",
        f"Phase 3 (DevOps & Cloud): Containerize your projects with Docker and set up automated GitHub Actions for CI/CD deployment.",
        f"Phase 4 (Interview & System Design): Practice role-specific system design questions (client-server architecture, database indexing) and core data structures for {user_goal}.",
    ]

    # Tailored interview questions
    interview_questions = []
    if detected_projects:
        p1 = detected_projects[0][0]
        interview_questions.append(f"In your '{p1}', how did you structure the frontend components, and how would you architect a backend API to support dynamic data?")
    if any("Generative AI" in s or "Prompt" in s for s in found_skills):
        interview_questions.append("How do you design and evaluate prompt engineering templates, and what strategies do you use to mitigate LLM hallucinations?")
    if any("React" in s for s in found_skills):
        interview_questions.append("Can you explain React state management, hooks (useState, useEffect), and how you optimize component rendering performance?")
    if any("Python" in s for s in found_skills) or any("Java" in s for s in found_skills):
        interview_questions.append(f"How do Object-Oriented Programming (OOP) principles and data structures apply when designing scalable systems for a {user_goal} role?")
    if len(interview_questions) < 4:
        interview_questions.append(f"Can you walk us through a challenging bug or performance bottleneck you resolved in your recent software projects?")

    return {
        "skills": found_skills,
        "missing_skills": missing_skills[:4],
        "roadmap": roadmap,
        "interview_questions": interview_questions[:4],
    }


def analyze_resume(resume_text, user_goal):
    gemini_key = _get_config_value("GEMINI_API_KEY") or _get_config_value("GOOGLE_API_KEY")
    openai_key = _get_config_value("OPENAI_API_KEY")

    if gemini_key:
        try:
            return _analyze_with_gemini(gemini_key, resume_text, user_goal)
        except Exception as exc:
            # If Gemini call fails (quota or network), seamlessly fallback to smart analysis
            return _analyze_resume_smart(resume_text, user_goal)

    if openai_key:
        try:
            return _analyze_with_openai(openai_key, resume_text, user_goal)
        except Exception:
            return _analyze_resume_smart(resume_text, user_goal)

    # When no API key is configured yet, analyze resume intelligently without crashing
    return _analyze_resume_smart(resume_text, user_goal)
