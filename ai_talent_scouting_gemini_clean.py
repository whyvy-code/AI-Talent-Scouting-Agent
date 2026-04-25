import json
import os
import re
from pathlib import Path

import streamlit as st

try:
    from google import genai
except ImportError:
    genai = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


JD_PATH_INPUT = r"C:\Users\Vikas Yadav\Downloads\JD - Manager - Sales Operations"
CANDIDATES_PATH = Path("data/candidates.json")
PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]
_WORKING_MODEL = None
FALLBACK_SKILLS = [
    "python",
    "sql",
    "excel",
    "salesforce",
    "tableau",
    "power bi",
    "crm",
    "communication",
    "leadership",
    "operations",
    "analytics",
    "forecasting",
]


def _normalize_model_name(name: str) -> str:
    return name.split("/", 1)[1] if name.startswith("models/") else name


def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    if genai is None:
        raise RuntimeError("Missing dependency: install google-genai.")
    return genai.Client(api_key=api_key)


def ask_gemini(prompt: str) -> str:
    global _WORKING_MODEL
    client = get_gemini_client()

    models_to_try = [_WORKING_MODEL] if _WORKING_MODEL else []
    models_to_try.extend(m for m in PREFERRED_MODELS if m != _WORKING_MODEL)

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            _WORKING_MODEL = model_name
            return (response.text or "").strip()
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        "No supported Gemini model found for this API key. "
        f"Tried: {', '.join(models_to_try)}. Last error: {last_error}"
    )


def run_startup_model_check() -> tuple[bool, str]:
    global _WORKING_MODEL
    try:
        client = get_gemini_client()
        available = []
        for model in client.models.list():
            model_name = _normalize_model_name(getattr(model, "name", ""))
            if model_name in PREFERRED_MODELS:
                available.append(model_name)

        if available:
            _WORKING_MODEL = available[0]
            return True, f"Gemini startup check passed. Preferred model: `{_WORKING_MODEL}`"

        return (
            False,
            "Gemini startup check failed: none of the preferred models are listed for this key. "
            "App will use non-LLM fallback when needed.",
        )
    except Exception as exc:
        return False, f"Gemini startup check failed: {exc}"


def extract_text_from_pdf(pdf_path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError("Missing dependency: install pypdf.")
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_text_from_uploaded_pdf(uploaded_file) -> str:
    if PdfReader is None:
        raise RuntimeError("Missing dependency: install pypdf.")
    reader = PdfReader(uploaded_file)
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_json(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty response.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Could not parse JSON from Gemini response.")
        return json.loads(text[start : end + 1])


def parse_jd(jd_text: str) -> dict:
    prompt = f"""
Extract structured hiring requirements from this job description.
Return ONLY valid JSON with keys:
skills (list), experience (number), role (string), keywords (list).

Job description:
{jd_text}
"""
    parsed = extract_json(ask_gemini(prompt))
    parsed.setdefault("skills", [])
    parsed.setdefault("experience", 0)
    parsed.setdefault("role", "Unknown")
    parsed.setdefault("keywords", [])
    return parsed


def parse_jd_rule_based(jd_text: str) -> dict:
    text = jd_text.lower()
    matched_skills = [skill.title() for skill in FALLBACK_SKILLS if skill in text]

    exp_match = re.search(r"(\d+)\s*\+?\s*(?:years|yrs)", text)
    experience = int(exp_match.group(1)) if exp_match else 0

    role_match = re.search(r"(manager|lead|analyst|executive|specialist|associate)", text)
    role = role_match.group(1).title() if role_match else "Unknown"

    words = re.findall(r"[a-zA-Z]{4,}", text)
    keywords = [w for w in sorted(set(words)) if w not in {"with", "from", "that", "this"}][:12]

    return {
        "skills": matched_skills,
        "experience": experience,
        "role": role,
        "keywords": keywords,
    }


def match_candidates(jd: dict, candidates: list[dict]) -> list[dict]:
    results = []
    jd_skills = set(s.lower() for s in jd.get("skills", []))
    jd_exp = jd.get("experience", 0) or 0
    for candidate in candidates:
        cand_skills = set(s.lower() for s in candidate.get("skills", []))
        overlap = jd_skills & cand_skills
        skill_overlap = len(overlap) / max(len(jd_skills), 1)
        cand_exp = candidate.get("experience", 0) or 0
        exp_score = min(cand_exp / jd_exp, 1) if jd_exp else 1
        match_score = 0.6 * skill_overlap + 0.4 * exp_score
        results.append(
            {
                **candidate,
                "match_score": round(match_score, 2),
                "explanation": f"Matched {len(overlap)} required skills",
            }
        )
    return results


def simulate_conversation(candidate: dict, jd: dict) -> str:
    prompt = f"""
You are this candidate:
{candidate}

Role details:
{jd}

Recruiter asks: Are you interested in this role?
Reply in 2 short lines.
"""
    return ask_gemini(prompt)


def simulate_conversation_rule_based(candidate: dict, jd: dict) -> str:
    cand_exp = candidate.get("experience", 0) or 0
    jd_exp = jd.get("experience", 0) or 0
    if cand_exp >= jd_exp:
        return "Yes, this role looks aligned with my background.\nI would like to discuss the next steps."
    return "I am interested, but I may need role flexibility.\nHappy to discuss expectations."


def compute_interest_score(convo: str) -> float:
    text = (convo or "").lower()
    if "yes" in text or "interested" in text:
        return 1.0
    if "not" in text or "no" in text:
        return 0.0
    return 0.5


def compute_final_scores(candidates: list[dict]) -> list[dict]:
    for c in candidates:
        interest = compute_interest_score(c.get("conversation", ""))
        c["interest_score"] = interest
        c["final_score"] = round(0.7 * c["match_score"] + 0.3 * interest, 2)
    return sorted(candidates, key=lambda x: x["final_score"], reverse=True)


def load_candidates() -> list[dict]:
    if CANDIDATES_PATH.exists():
        with CANDIDATES_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return [
        {
            "name": "Rahul Verma",
            "skills": ["Python", "SQL", "Machine Learning", "Power BI"],
            "experience": 3,
            "domain": "IT",
        },
        {
            "name": "Priya Nair",
            "skills": ["Python", "Excel", "Data Analysis", "Communication"],
            "experience": 2,
            "domain": "IT",
        },
        {
            "name": "Arjun Mehta",
            "skills": ["Salesforce", "CRM", "Negotiation", "Lead Generation"],
            "experience": 5,
            "domain": "Sales",
        },
        {
            "name": "Sneha Iyer",
            "skills": ["SQL", "Tableau", "Forecasting", "Operations"],
            "experience": 4,
            "domain": "IT",
        },
        {
            "name": "Karan Singh",
            "skills": ["B2B Sales", "Communication", "CRM", "Leadership"],
            "experience": 6,
            "domain": "Sales",
        },
        {
            "name": "Neha Kapoor",
            "skills": ["Power BI", "Excel", "Analytics", "Reporting"],
            "experience": 3,
            "domain": "IT",
        },
        {
            "name": "Rohit Sharma",
            "skills": ["Territory Sales", "Client Management", "Negotiation", "CRM"],
            "experience": 7,
            "domain": "Sales",
        },
        {
            "name": "Aditi Rao",
            "skills": ["Python", "SQL", "ETL", "Data Modeling"],
            "experience": 5,
            "domain": "IT",
        },
        {
            "name": "Manish Gupta",
            "skills": ["Sales Operations", "Forecasting", "Excel", "Salesforce"],
            "experience": 4,
            "domain": "Sales",
        },
        {
            "name": "Pooja Desai",
            "skills": ["Inside Sales", "Lead Qualification", "Communication", "CRM"],
            "experience": 3,
            "domain": "Sales",
        },
        {
            "name": "Vikram Joshi",
            "skills": ["Cloud", "Python", "DevOps", "Automation"],
            "experience": 6,
            "domain": "IT",
        },
        {
            "name": "Ritika Malhotra",
            "skills": ["Account Management", "Upselling", "CRM", "Presentation"],
            "experience": 5,
            "domain": "Sales",
        },
    ]


def run_pipeline(jd_text: str, llm_enabled: bool) -> tuple[dict, list[dict], bool, str]:
    fallback_used = False
    fallback_reason = ""
    if llm_enabled:
        try:
            structured_jd = parse_jd(jd_text)
        except Exception as exc:
            structured_jd = parse_jd_rule_based(jd_text)
            fallback_used = True
            fallback_reason = f"JD parsing fallback used: {exc}"
    else:
        structured_jd = parse_jd_rule_based(jd_text)
        fallback_used = True
        fallback_reason = "Gemini unavailable. Using deterministic fallback."

    matched = match_candidates(structured_jd, load_candidates())
    for c in matched:
        if llm_enabled:
            try:
                c["conversation"] = simulate_conversation(c, structured_jd)
            except Exception as exc:
                c["conversation"] = simulate_conversation_rule_based(c, structured_jd)
                fallback_used = True
                if not fallback_reason:
                    fallback_reason = f"Conversation fallback used: {exc}"
        else:
            c["conversation"] = simulate_conversation_rule_based(c, structured_jd)
    return structured_jd, compute_final_scores(matched), fallback_used, fallback_reason


st.title("AI Talent Scouting Agent (Gemini)")

if "startup_check_done" not in st.session_state:
    ok, message = run_startup_model_check()
    st.session_state["startup_check_done"] = True
    st.session_state["startup_check_ok"] = ok
    st.session_state["startup_check_message"] = message

if st.session_state.get("startup_check_ok"):
    st.success(st.session_state.get("startup_check_message", "Gemini startup check passed."))
else:
    st.warning(st.session_state.get("startup_check_message", "Gemini startup check failed."))

if not os.getenv("GEMINI_API_KEY"):
    st.warning("Set GEMINI_API_KEY before running candidate analysis.")

uploaded_jd_pdf = st.file_uploader("Upload Job Description PDF", type=["pdf"])
jd_text_input = st.text_area("Or paste Job Description manually (optional)")

if st.button("Find Candidates"):
    try:
        if uploaded_jd_pdf is not None:
            jd_text = extract_text_from_uploaded_pdf(uploaded_jd_pdf)
            if not jd_text:
                st.error("JD PDF is empty or text extraction failed.")
                st.stop()
        else:
            jd_text = jd_text_input.strip()
            if not jd_text:
                st.error("Upload a JD PDF or paste the JD text.")
                st.stop()

        llm_enabled = bool(os.getenv("GEMINI_API_KEY")) and bool(st.session_state.get("startup_check_ok"))
        with st.spinner("Processing JD and ranking candidates..."):
            parsed_jd, results, fallback_used, fallback_reason = run_pipeline(jd_text, llm_enabled=llm_enabled)
        if fallback_used:
            st.warning(
                "Running in non-LLM fallback mode for part of processing. "
                "Results are deterministic and demo-safe."
            )
            if fallback_reason:
                st.caption(fallback_reason)
        st.subheader("Parsed JD")
        st.json(parsed_jd)
        st.subheader("Ranked Candidates")
        st.caption(f"Candidates evaluated: {len(results)}")
        if not results:
            st.warning("No candidates available. Add entries to data/candidates.json.")
        for c in results:
            st.write(f"### {c['name']}")
            st.write(f"Match: {c['match_score']}")
            st.write(f"Interest: {c['interest_score']}")
            st.write(f"Final: {c['final_score']}")
            st.write(f"Why: {c['explanation']}")
            st.write(f"Chat: {c['conversation']}")
    except Exception as exc:
        st.error(f"Failed to process candidates: {exc}")
