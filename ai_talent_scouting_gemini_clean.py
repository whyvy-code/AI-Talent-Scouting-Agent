import json
import os
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

try:
    from google import genai
except ImportError:
    genai = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


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
    api_key = (st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")).strip()
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


def get_candidate_pool() -> list[dict]:
    base_candidates = load_candidates()
    live_candidates = st.session_state.get("live_candidates", [])
    return [*base_candidates, *live_candidates]


def build_live_conversation_text(chat_messages: list[dict]) -> str:
    lines = []
    for msg in chat_messages:
        role = msg.get("role", "agent").title()
        text = msg.get("text", "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def extract_jd_preferences(jd_text: str) -> dict:
    text = (jd_text or "").lower()
    remote_mode = None
    if "hybrid" in text:
        remote_mode = "Hybrid"
    elif "remote" in text:
        remote_mode = "Remote"
    elif "onsite" in text or "on-site" in text or "on site" in text:
        remote_mode = "Onsite"

    salary_min = None
    salary_max = None
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-to]+\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?)", text)
    if range_match:
        salary_min = float(range_match.group(1))
        salary_max = float(range_match.group(2))
    else:
        upto_match = re.search(r"(?:up to|upto|max(?:imum)?)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?)", text)
        min_match = re.search(r"(?:minimum|min)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?)", text)
        if upto_match:
            salary_max = float(upto_match.group(1))
        if min_match:
            salary_min = float(min_match.group(1))

    return {
        "remote_mode": remote_mode,
        "salary_min_lpa": salary_min,
        "salary_max_lpa": salary_max,
    }


def assess_genuine_interest_from_answers(jd_text: str, answers: dict) -> tuple[float, str]:
    prefs = extract_jd_preferences(jd_text)
    open_value = (answers.get("open_to_opportunities") or "").strip().lower()
    expected_salary = answers.get("expected_salary_lpa")
    remote_pref = answers.get("remote_preference")

    openness_score = {"yes": 1.0, "maybe": 0.6, "no": 0.1}.get(open_value, 0.5)

    salary_score = 0.7
    salary_min = prefs.get("salary_min_lpa")
    salary_max = prefs.get("salary_max_lpa")
    if expected_salary is not None and (salary_min is not None or salary_max is not None):
        sal = float(expected_salary)
        low = salary_min if salary_min is not None else float("-inf")
        high = salary_max if salary_max is not None else float("inf")
        if low <= sal <= high:
            salary_score = 1.0
        elif sal < low:
            salary_score = 0.6 if low > 0 and sal >= (0.8 * low) else 0.2
        else:
            salary_score = 0.6 if sal <= (1.2 * high) else 0.2

    remote_score = 0.7
    jd_remote = prefs.get("remote_mode")
    if jd_remote and remote_pref:
        if remote_pref == jd_remote:
            remote_score = 1.0
        elif {remote_pref, jd_remote} == {"Hybrid", "Remote"}:
            remote_score = 0.7
        elif {remote_pref, jd_remote} == {"Hybrid", "Onsite"}:
            remote_score = 0.6
        else:
            remote_score = 0.2

    interest_score = round(0.5 * openness_score + 0.3 * salary_score + 0.2 * remote_score, 2)
    note = (
        f"Interest factors -> openness: {openness_score:.2f}, "
        f"salary alignment: {salary_score:.2f}, remote alignment: {remote_score:.2f}."
    )
    return interest_score, note


def ensure_agent_questions(history: list[dict], answers: dict, candidate_name: str) -> None:
    if not history:
        history.append({"role": "agent", "text": f"Hi {candidate_name}, Q1: Open to opportunities?"})
        return
    if answers.get("open_to_opportunities") and not answers.get("expected_salary_lpa"):
        if not any("Q2: Expected salary?" in m.get("text", "") for m in history if m.get("role") == "agent"):
            history.append({"role": "agent", "text": "Q2: Expected salary? (LPA)"})
    if answers.get("expected_salary_lpa") is not None and not answers.get("remote_preference"):
        if not any("Q3: Remote preference?" in m.get("text", "") for m in history if m.get("role") == "agent"):
            history.append({"role": "agent", "text": "Q3: Remote preference?"})
    if answers.get("remote_preference"):
        if not any("Thanks for sharing your details." in m.get("text", "") for m in history if m.get("role") == "agent"):
            history.append(
                {
                    "role": "agent",
                    "text": "Thanks for sharing your details. I have completed the interest assessment.",
                }
            )


def compute_final_scores(candidates: list[dict], interest_overrides: dict | None = None) -> list[dict]:
    interest_overrides = interest_overrides or {}
    for c in candidates:
        if c.get("name") in interest_overrides:
            interest = interest_overrides[c["name"]]
        else:
            interest = compute_interest_score(c.get("conversation", ""))
        c["interest_score"] = interest
        c["final_score"] = round(0.7 * c["match_score"] + 0.3 * interest, 2)
    return sorted(candidates, key=lambda x: x["final_score"], reverse=True)


def run_pipeline(
    jd_text: str,
    llm_enabled: bool,
    candidates: list[dict],
    live_conversations: dict | None = None,
    live_interest_scores: dict | None = None,
) -> tuple[dict, list[dict], bool, str]:
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

    matched = match_candidates(structured_jd, candidates)
    live_conversations = live_conversations or {}
    live_interest_scores = live_interest_scores or {}

    for c in matched:
        if c.get("name") in live_conversations:
            c["conversation"] = live_conversations[c["name"]]
            continue
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
    return (
        structured_jd,
        compute_final_scores(matched, interest_overrides=live_interest_scores),
        fallback_used,
        fallback_reason,
    )


st.set_page_config(page_title="AI Talent Scouting Agent", layout="wide")
st.markdown(
    """
    <style>
      .block-container {
        max-width: 1600px;
        padding-top: 1.2rem;
        padding-bottom: 1.2rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("AI Talent Scouting Agent (Gemini)")

if "gemini_api_key" not in st.session_state:
    st.session_state["gemini_api_key"] = os.getenv("GEMINI_API_KEY", "").strip()
if "gemini_key_input" not in st.session_state:
    st.session_state["gemini_key_input"] = st.session_state["gemini_api_key"]
if "gemini_expander_open" not in st.session_state:
    st.session_state["gemini_expander_open"] = not bool(st.session_state.get("gemini_api_key"))

with st.expander("Gemini API Key", expanded=st.session_state.get("gemini_expander_open", False)):
    st.caption("Enter key to enable LLM mode. Leave empty to use fallback mode.")
    st.text_input(
        "GEMINI_API_KEY",
        type="password",
        key="gemini_key_input",
        placeholder="Paste your Gemini API key",
    )
    key_col1, key_col2 = st.columns(2)
    with key_col1:
        if st.button("Use Key", key="use_gemini_key"):
            st.session_state["gemini_api_key"] = st.session_state.get("gemini_key_input", "").strip()
            st.session_state["gemini_expander_open"] = False
            st.session_state["startup_check_done"] = False
            st.rerun()
    with key_col2:
        if st.button("Use Fallback Mode", key="clear_gemini_key"):
            st.session_state["gemini_api_key"] = ""
            st.session_state["gemini_expander_open"] = False
            st.session_state["startup_check_done"] = False
            st.rerun()

if "startup_check_done" not in st.session_state or not st.session_state.get("startup_check_done"):
    ok, message = run_startup_model_check()
    st.session_state["startup_check_done"] = True
    st.session_state["startup_check_ok"] = ok
    st.session_state["startup_check_message"] = message

if st.session_state.get("startup_check_ok"):
    st.success(st.session_state.get("startup_check_message", "Gemini startup check passed."))
else:
    st.warning(st.session_state.get("startup_check_message", "Gemini startup check failed."))

if not st.session_state.get("gemini_api_key"):
    st.warning("Gemini key not set in app. Running in fallback mode.")

if "live_candidates" not in st.session_state:
    st.session_state["live_candidates"] = []
if "candidate_chats" not in st.session_state:
    st.session_state["candidate_chats"] = {}
if "candidate_interest_scores" not in st.session_state:
    st.session_state["candidate_interest_scores"] = {}
if "candidate_interest_notes" not in st.session_state:
    st.session_state["candidate_interest_notes"] = {}
if "candidate_interviews" not in st.session_state:
    st.session_state["candidate_interviews"] = {}
if "scroll_to_interview_candidate" not in st.session_state:
    st.session_state["scroll_to_interview_candidate"] = ""
if "selected_live_candidate" not in st.session_state:
    st.session_state["selected_live_candidate"] = ""

left_col, divider_col, right_col = st.columns([1.15, 0.08, 1.15], gap="large")
current_jd_text = ""

with left_col:
    st.subheader("JD Search and Candidate Ranking")
    uploaded_jd_pdf = st.file_uploader("Upload Job Description PDF", type=["pdf"])
    jd_text_input = st.text_area("Or paste Job Description manually (optional)")
    current_jd_text = jd_text_input.strip()
    if not current_jd_text and uploaded_jd_pdf is not None:
        try:
            current_jd_text = extract_text_from_uploaded_pdf(uploaded_jd_pdf)
        except Exception:
            current_jd_text = ""

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

            live_conversations = {
                name: build_live_conversation_text(messages)
                for name, messages in st.session_state["candidate_chats"].items()
            }
            llm_enabled = bool(st.session_state.get("gemini_api_key")) and bool(st.session_state.get("startup_check_ok"))
            with st.spinner("Processing JD and ranking candidates..."):
                parsed_jd, results, fallback_used, fallback_reason = run_pipeline(
                    jd_text,
                    llm_enabled=llm_enabled,
                    candidates=get_candidate_pool(),
                    live_conversations=live_conversations,
                    live_interest_scores=st.session_state["candidate_interest_scores"],
                )
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

with divider_col:
    st.markdown(
        """
        <div
          style="
            height: 76vh;
            margin: 6vh auto;
            border-left: 2px solid #d6d6d6;
            width: 1px;
          "
        ></div>
        """,
        unsafe_allow_html=True,
    )

with right_col:
    st.subheader("Live Candidate Conversation Agent")
    with st.form("candidate_profile_form", clear_on_submit=True):
        candidate_name = st.text_input("Candidate Name")
        candidate_skills_text = st.text_input("Skills (comma separated)")
        candidate_experience = st.number_input("Experience (years)", min_value=0, max_value=50, value=0, step=1)
        candidate_domain = st.selectbox("Domain", options=["IT", "Sales"], index=0)
        add_candidate = st.form_submit_button("Submit Candidate Profile")

    if add_candidate:
        parsed_skills = [s.strip() for s in candidate_skills_text.split(",") if s.strip()]
        if not candidate_name.strip():
            st.error("Candidate name is required.")
        elif not parsed_skills:
            st.error("Please add at least one skill.")
        else:
            profile = {
                "name": candidate_name.strip(),
                "skills": parsed_skills,
                "experience": int(candidate_experience),
                "domain": candidate_domain.strip() or "General",
            }
            st.session_state["live_candidates"] = [
                c for c in st.session_state["live_candidates"] if c.get("name") != profile["name"]
            ]
            st.session_state["live_candidates"].append(profile)
            st.session_state["candidate_chats"].setdefault(profile["name"], [])
            st.session_state["candidate_interest_scores"].setdefault(profile["name"], 0.5)
            st.session_state["candidate_interest_notes"].setdefault(profile["name"], "Interest is currently unclear.")
            st.session_state["candidate_interviews"][profile["name"]] = {
                "open_to_opportunities": "",
                "expected_salary_lpa": None,
                "remote_preference": "",
            }
            st.session_state["scroll_to_interview_candidate"] = profile["name"]
            st.session_state["selected_live_candidate"] = profile["name"]
            st.success(f"Candidate profile added for {profile['name']}.")

    live_candidate_names = [c.get("name") for c in st.session_state["live_candidates"]]
    if not live_candidate_names:
        st.info("Submit candidate details to start live conversation.")
    else:
        if st.session_state.get("selected_live_candidate") not in live_candidate_names:
            st.session_state["selected_live_candidate"] = live_candidate_names[0]
        selected_idx = live_candidate_names.index(st.session_state["selected_live_candidate"])
        selected_candidate = st.selectbox("Select Candidate", live_candidate_names, index=selected_idx)
        st.session_state["selected_live_candidate"] = selected_candidate
        history = st.session_state["candidate_chats"].setdefault(selected_candidate, [])
        interview = st.session_state["candidate_interviews"].setdefault(
            selected_candidate,
            {"open_to_opportunities": "", "expected_salary_lpa": None, "remote_preference": ""},
        )
        ensure_agent_questions(history, interview, selected_candidate)

        st.markdown('<div id="live-interview-section"></div>', unsafe_allow_html=True)
        if st.session_state.get("scroll_to_interview_candidate") == selected_candidate:
            components.html(
                """
                <script>
                    const target = window.parent.document.getElementById("live-interview-section");
                    if (target) {
                        target.scrollIntoView({ behavior: "smooth", block: "start" });
                    }
                </script>
                """,
                height=0,
            )
            st.session_state["scroll_to_interview_candidate"] = ""

        st.caption("Live Interview")
        with st.container(border=True):
            for item in history:
                speaker = "Candidate" if item.get("role") == "candidate" else "Agent"
                st.markdown(f"**{speaker}:** {item.get('text', '')}")

        if not interview.get("open_to_opportunities"):
            q1 = st.radio(
                "Q1: Open to opportunities?",
                options=["Yes", "Maybe", "No"],
                horizontal=True,
                key=f"q1_{selected_candidate}",
            )
            if st.button("Submit Q1", key=f"submit_q1_{selected_candidate}"):
                interview["open_to_opportunities"] = q1.lower()
                history.append({"role": "candidate", "text": q1})
                ensure_agent_questions(history, interview, selected_candidate)
                st.rerun()
        elif interview.get("expected_salary_lpa") is None:
            q2 = st.number_input(
                "Q2: Expected salary? (LPA)",
                min_value=1.0,
                max_value=200.0,
                value=8.0,
                step=0.5,
                key=f"q2_{selected_candidate}",
            )
            if st.button("Submit Q2", key=f"submit_q2_{selected_candidate}"):
                interview["expected_salary_lpa"] = float(q2)
                history.append({"role": "candidate", "text": f"{q2} LPA"})
                ensure_agent_questions(history, interview, selected_candidate)
                st.rerun()
        elif not interview.get("remote_preference"):
            q3 = st.selectbox(
                "Q3: Remote preference?",
                options=["Remote", "Hybrid", "Onsite"],
                key=f"q3_{selected_candidate}",
            )
            if st.button("Submit Q3", key=f"submit_q3_{selected_candidate}"):
                interview["remote_preference"] = q3
                history.append({"role": "candidate", "text": q3})
                ensure_agent_questions(history, interview, selected_candidate)
                score, note = assess_genuine_interest_from_answers(current_jd_text, interview)
                st.session_state["candidate_interest_scores"][selected_candidate] = score
                st.session_state["candidate_interest_notes"][selected_candidate] = note
                st.rerun()
        else:
            st.success("Interview complete for this candidate.")

        current_score = st.session_state["candidate_interest_scores"].get(selected_candidate, 0.5)
        current_note = st.session_state["candidate_interest_notes"].get(selected_candidate, "Interest is currently unclear.")
        st.caption(f"Genuine Interest Score: {current_score}")
        st.caption(current_note)
