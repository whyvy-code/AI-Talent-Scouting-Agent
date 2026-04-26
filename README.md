# AI-Powered Talent Scouting and Engagement Agent

An AI recruitment assistant that parses a Job Description (JD), matches candidate profiles, engages candidates through a live conversation panel, and returns a ranked shortlist based on:

- Match Score
- Interest Score

This project is built for hackathon submission and includes both:

- Gemini-powered mode (LLM enabled)
- Deterministic fallback mode (non-LLM, demo-safe)

## Problem Statement Coverage

This prototype implements:

- JD parsing from uploaded PDF (or pasted text)
- Candidate discovery from built-in sample pool + live submitted candidate profiles
- Explainable matching with overlap logic
- Conversational outreach simulation for sample candidates
- AI-first resume interview face (3-5 dynamic questions driven by resume content)
- Automatic fallback face with guided Q1/Q2/Q3 interview when Gemini is unavailable/rate-limited
- Top-5 ranked shortlist output for faster recruiter review
- Ranked output with score breakdown

## Project Structure

- `ai_talent_scouting_gemini_clean.py` - Main Streamlit app
- `run_ai_talent_scouting_agent.bat` - One-click Windows launcher
- `requirements.txt` - Python dependencies
- `ARCHITECTURE.md` - Architecture diagram and logic details
- `samples/sample_jd.txt` - Example JD input
- `samples/sample_output.json` - Example ranked output
- `.gitignore` - Git ignore rules

## Tech Stack

- Python 3.10+
- Streamlit (UI)
- Gemini API via `google-genai` (optional)
- PyPDF (`pypdf`) for PDF text extraction

## Scoring Logic

- `skill_overlap = matched_skills / total_required_skills`
- `experience_fit = min(candidate_exp / required_exp, 1)`
- `match_score = 0.6 * skill_overlap + 0.4 * experience_fit`
- `interest_score`:
  - for live candidates in AI face: score from resume-aware dynamic interview answers
  - for live candidates in fallback face: guided interview answers matched to JD preferences
  - for sample candidates: simulated response sentiment
- `final_score = 0.7 * match_score + 0.3 * interest_score`
- ranking output is capped to top 5 candidates

## Setup and Run (Local, Windows)

### Option A: Run via hosted URL

Open:

`https://ai-talent-scouting-agent-bvzxjl3ztgvdc5cs3gdnnp.streamlit.app/`

### Option B: One-click local run

Double-click:

`run_ai_talent_scouting_agent.bat`

It will:

- install dependencies
- launch app and allow entering `GEMINI_API_KEY` in the UI
- launch app at `http://localhost:8501`
- in the `Gemini API Key` section, use `Use Key` (LLM mode) or `Use Fallback Mode`

### Option C: Manual local run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. (Optional) Set Gemini key via environment:

```powershell
$env:GEMINI_API_KEY="YOUR_KEY_HERE"
```

3. Start app:

```bash
streamlit run ai_talent_scouting_gemini_clean.py
```

4. Enter Gemini key in app (recommended):
   - Open the `Gemini API Key` section in UI
   - Paste key and click `Use Key`
   - Or click `Use Fallback Mode` to run without key

5. For Streamlit deployment:
   - Use in-app Gemini key input at launch, or configure `GEMINI_API_KEY` in app secrets/environment

## How to Use

1. Open app in browser.
2. Upload JD PDF (or paste JD text) in the **left panel**.
3. Use the **right panel** (candidate side):
   - **Face 1 (AI mode)**: upload resume PDF and click `Start AI Interview`.
   - AI asks 3-5 resume-specific questions one by one in chat.
   - Candidate answers each question; interest score is computed after interview completion.
4. If Gemini key is missing/invalid/rate-limited, app switches to **Face 2 (fallback mode)**:
   - submit profile fields (`name`, `skills`, `experience`, `domain`)
   - complete guided interview:
     - `Q1: Open to opportunities?`
     - `Q2: Expected salary? (LPA)`
     - `Q3: Remote preference?`
5. In fallback face, app auto-selects candidate and scrolls to interview section after profile submit.
6. Click `Find Candidates`.
7. Review:
   - parsed JD
   - ranked candidates
   - explanation and one-line chat summary
   - combined results from sample + live submitted candidates

## UI Layout

- Left panel: JD parsing and ranked candidate search
- Right panel: dual-face candidate interface
  - Face 1: AI resume-chat interview (Gemini)
  - Face 2: fallback guided interview form
- Wide layout with visual center divider for easier side-by-side usage

## Fallback Behavior (Important for Demo Reliability)

If Gemini is unavailable due to quota/rate limits:

- app automatically switches candidate panel to fallback face for interview capture
- app automatically switches to non-LLM fallback for JD parsing/simulated conversation
- ranking path limits conversation generation to top 5 matched candidates for faster response
- still produces deterministic shortlist and scores
- UI clearly shows fallback warning

## Sample Input and Output

- Sample JD: `samples/sample_jd.txt`
- Sample result: `samples/sample_output.json`

## Demo Video (3-5 min) Suggested Flow

1. Problem and objective (20 sec)
2. Upload JD PDF and run matching (90 sec)
3. Explain scoring and ranked shortlist (60 sec)
4. Show fallback mode reliability (45 sec)
5. Wrap-up and future scope (20 sec)

## Limitations

- Built-in sample candidate data is static (no external ATS integration yet)
- Live submitted candidates are session-based (not persisted across app restarts)
- AI interview quality depends on resume text extraction and Gemini availability
- Fallback live-interest scoring is rule-based and depends on JD signal quality
- Fallback parser is heuristic-based

## Future Improvements

- Resume ingestion and vector search
- Real candidate outreach channels (email/LinkedIn APIs)
- Better explainability dashboard
- Role-specific weighting configuration

## Submission Fields

Fill these before final submission:

- Git repository URL: `https://github.com/whyvy-code/AI-Talent-Scouting-Agent`
- GitHub username: `whyvy-code`
- Project documentation: `README.md` in repo
- Demo video link: `<add-video-link>`
- Project site URL: `http://localhost:8501` or `https://ai-talent-scouting-agent-bvzxjl3ztgvdc5cs3gdnnp.streamlit.app/`
