
import json
import os
import time
import logging
from pathlib import Path

import requests
import streamlit as st
from docx import Document
from dotenv import load_dotenv
from pypdf import PdfReader

from logger_config import get_logger


# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", "http://localhost:11434"
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL", "llama3.2:3b"
)

# Connection timeout: 5 seconds.
# Read timeout: 300 seconds.
REQUEST_TIMEOUT = (5, 300)

REPORT_SECTIONS = [
    ("strengths", "Strengths"),
    ("gaps", "Gaps"),
    ("missing_or_weak_skills", "Missing or Weak Skills"),
    ("improvement_suggestions", "Improvement Suggestions"),
    ("overall_summary", "Overall Summary"),
]


# --------------------------------------------------
# 2. OLLAMA API HELPER WITH TIMING AND ERROR LOGGING
# --------------------------------------------------

def call_ollama(prompt, system_prompt, stage):
    """Send a request to Ollama and trace its execution."""

    url = f"{OLLAMA_BASE_URL}/api/chat"
    start_time = time.perf_counter()

    logger.info("[%s] Request started", stage)
    logger.info("[%s] Model: %s", stage, OLLAMA_MODEL)
    logger.info("[%s] Prompt length: %d characters", stage, len(prompt))
    logger.info("[%s] Endpoint: %s/api/chat", stage, OLLAMA_BASE_URL)

    try:
        logger.info("[%s] Sending HTTP request to Ollama", stage)

        response = requests.post(
            url,
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0,
                },
            },
            timeout=REQUEST_TIMEOUT,
        )

        elapsed = time.perf_counter() - start_time

        logger.info(
            "[%s] HTTP response received in %.2f seconds; status=%s",
            stage,
            elapsed,
            response.status_code,
        )

        response.raise_for_status()

        data = response.json()

        message = data.get("message", {})
        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                f"{stage}: Ollama returned an empty or invalid message."
            )

        # Ollama may provide performance metrics in its response.
        logger.info(
            "[%s] Model generation completed; total request time: %.2f seconds",
            stage,
            time.perf_counter() - start_time,
        )

        if "total_duration" in data:
            logger.info(
                "[%s] Ollama total duration: %.2f seconds",
                stage,
                data["total_duration"] / 1_000_000_000,
            )

        if "load_duration" in data:
            logger.info(
                "[%s] Model load duration: %.2f seconds",
                stage,
                data["load_duration"] / 1_000_000_000,
            )

        if "prompt_eval_count" in data:
            logger.info(
                "[%s] Prompt tokens processed: %s",
                stage,
                data["prompt_eval_count"],
            )

        if "eval_count" in data:
            logger.info(
                "[%s] Response tokens generated: %s",
                stage,
                data["eval_count"],
            )

        if data.get("eval_duration"):
            tokens_per_second = (
                data["eval_count"] * 1_000_000_000
                / data["eval_duration"]
            ) if data.get("eval_count") is not None else None

            if tokens_per_second is not None:
                logger.info(
                    "[%s] Generation speed: %.2f tokens/second",
                    stage,
                    tokens_per_second,
                )

        logger.info("[%s] Request finished successfully", stage)

        return content

    except requests.exceptions.Timeout:
        logger.exception(
            "[%s] TIMEOUT after %.2f seconds",
            stage,
            time.perf_counter() - start_time,
        )
        raise

    except requests.exceptions.ConnectionError:
        logger.exception(
            "[%s] CONNECTION FAILED after %.2f seconds",
            stage,
            time.perf_counter() - start_time,
        )
        raise

    except requests.exceptions.HTTPError:
        logger.exception(
            "[%s] HTTP ERROR after %.2f seconds",
            stage,
            time.perf_counter() - start_time,
        )
        raise

    except requests.exceptions.RequestException:
        logger.exception(
            "[%s] REQUEST FAILED after %.2f seconds",
            stage,
            time.perf_counter() - start_time,
        )
        raise

    except (ValueError, json.JSONDecodeError):
        logger.exception("[%s] Invalid response from Ollama", stage)
        raise

    except Exception:
        logger.exception("[%s] Unexpected API error", stage)
        raise


# --------------------------------------------------
# 3. RESUME TEXT EXTRACTION
# --------------------------------------------------

def extract_resume_text(uploaded_file):
    """Extract text from a PDF or DOCX resume."""

    start_time = time.perf_counter()
    file_name = uploaded_file.name.lower()

    logger.info("[EXTRACTION] Started for file: %s", uploaded_file.name)

    try:
        if file_name.endswith(".pdf"):
            logger.info("[EXTRACTION] Reading PDF pages")

            reader = PdfReader(uploaded_file)
            pages = []

            for page_number, page in enumerate(reader.pages, start=1):
                logger.info(
                    "[EXTRACTION] Extracting PDF page %d of %d",
                    page_number,
                    len(reader.pages),
                )

                pages.append(page.extract_text() or "")

            text = "\n".join(pages).strip()

        elif file_name.endswith(".docx"):
            logger.info("[EXTRACTION] Reading DOCX paragraphs")

            document = Document(uploaded_file)
            paragraphs = [
                paragraph.text
                for paragraph in document.paragraphs
            ]

            text = "\n".join(paragraphs).strip()

        else:
            logger.warning("[EXTRACTION] Unsupported file type")
            return ""

        logger.info(
            "[EXTRACTION] Completed in %.2f seconds; extracted %d characters",
            time.perf_counter() - start_time,
            len(text),
        )

        if not text:
            logger.warning(
                "[EXTRACTION] No text found; the PDF may be scanned"
            )

        return text

    except Exception:
        logger.exception("[EXTRACTION] Failed to extract resume text")
        raise


# --------------------------------------------------
# 4. FIRST LLM CALL: STRUCTURED ANALYSIS
# --------------------------------------------------

def analyze_resume(resume_text, job_description):
    """Compare resume and JD and return structured JSON."""

    logger.info("[ANALYSIS] Preparing structured analysis prompt")

    prompt = f"""
You are an expert ATS resume analyzer and technical recruiter.

Compare the candidate's resume with the job description.

RULES:
- Use only information explicitly present in the resume and job description.
- Never invent skills, experience, qualifications, certifications,
  employers, job titles, dates, or achievements.
- A skill matches only when explicitly mentioned in both.
- missing_skills means explicitly required skills not mentioned in the resume.
- Do not include preferred skills in missing_skills.
- Keep items short, specific, and non-duplicative.
- If there is no information, return an empty list.
- Return only valid JSON, without Markdown.

Return exactly this structure:
{{
    "candidate_skills": [],
    "candidate_experience": [],
    "candidate_qualifications": [],
    "required_skills": [],
    "preferred_skills": [],
    "matching_skills": [],
    "missing_skills": [],
    "gaps": []
}}

Definitions:
candidate_skills: Skills explicitly mentioned in the resume.
candidate_experience: Relevant experience, internships, projects, or practical
experience explicitly mentioned in the resume.
candidate_qualifications: Degrees, certifications, education, or qualifications
explicitly mentioned in the resume.
required_skills: Skills explicitly required by the job description.
preferred_skills: Skills described as preferred, optional, or nice-to-have.
matching_skills: Skills explicitly mentioned in both documents.
missing_skills: Required skills not mentioned in the resume.
gaps: Important differences between the resume and job description.
Do not simply repeat every missing skill.

RESUME:
--------------------
{resume_text}
--------------------

JOB DESCRIPTION:
--------------------
{job_description}
--------------------

Return only JSON.
"""

    response_text = call_ollama(
        prompt,
        "You are an expert ATS resume analyzer.",
        "ANALYSIS",
    )

    logger.info("[ANALYSIS] Parsing structured JSON")

    try:
        result = json.loads(response_text)

    except json.JSONDecodeError as error:
        logger.exception("[ANALYSIS] Invalid JSON returned by model")
        raise ValueError(
            "Ollama did not return valid JSON for the resume analysis."
        ) from error

    if not isinstance(result, dict):
        raise ValueError("Analysis response must be a JSON object.")

    expected_keys = [
        "candidate_skills",
        "candidate_experience",
        "candidate_qualifications",
        "required_skills",
        "preferred_skills",
        "matching_skills",
        "missing_skills",
        "gaps",
    ]

    for key in expected_keys:
        if not isinstance(result.get(key), list):
            raise ValueError(
                f"Analysis JSON has a missing or invalid '{key}' field."
            )

    logger.info("[ANALYSIS] Structured analysis completed successfully")

    return result


# --------------------------------------------------
# 5. SECOND LLM CALL: FINAL REPORT
# --------------------------------------------------

def generate_final_report(structured_analysis):
    """Convert structured analysis into a readable report."""

    logger.info("[REPORT] Preparing final report prompt")

    prompt = f"""
You are an expert resume reviewer and career advisor.

Convert the supplied structured analysis into concise, honest, useful feedback.

RULES:
- Use only information contained in the supplied JSON.
- Never invent information.
- Do not add skills, technologies, experience, qualifications,
  responsibilities, achievements, or requirements not present in the JSON.
- Return only valid JSON, without Markdown code fences.

Return exactly this structure:
{{
    "strengths": "",
    "gaps": "",
    "missing_or_weak_skills": "",
    "improvement_suggestions": "",
    "overall_summary": ""
}}

OUTPUT RULES:

strengths:
Write a Markdown bullet list covering identified skills, experience,
qualifications, projects, or other strengths.

gaps:
Write a Markdown bullet list covering experience, qualifications,
responsibilities, or requirements not sufficiently demonstrated.

missing_or_weak_skills:
Write a Markdown bullet list of identified missing or weak technical skills,
tools, technologies, frameworks, languages, and platforms.
Do not repeat information from gaps.

improvement_suggestions:
Give practical suggestions based only on identified gaps and missing skills.

overall_summary:
Write one short paragraph about the candidate's fit based only on the JSON.

Use evidence-based wording. Do not claim to know what the candidate
actually knows beyond what the documents demonstrate.

Do not use these phrases:
- lacks
- lacking
- no experience
- no exposure
- does not know
- does not have

Do not provide a numeric score or percentage.

If a section has nothing useful to report, write:
"- Nothing further was identified from the provided information."

STRUCTURED ANALYSIS:
--------------------
{json.dumps(structured_analysis, indent=2)}
--------------------

Return only JSON.
"""

    response_text = call_ollama(
        prompt,
        "You are an expert resume reviewer and career advisor.",
        "REPORT",
    )

    logger.info("[REPORT] Parsing final report JSON")

    try:
        report = json.loads(response_text)

    except json.JSONDecodeError as error:
        logger.exception("[REPORT] Invalid JSON returned by model")
        raise ValueError(
            "Ollama did not return valid JSON for the final report."
        ) from error

    if not isinstance(report, dict):
        raise ValueError("Final report response must be a JSON object.")

    for key, _ in REPORT_SECTIONS:
        value = report.get(key)

        if isinstance(value, list):
            value = "\n".join(
                "- " + str(point) for point in value
            )

        if not isinstance(value, str) or not value.strip():
            value = "- Nothing further was identified from the provided information."

        report[key] = value

    logger.info("[REPORT] Final report generated successfully")

    return report


# --------------------------------------------------
# 6. DOWNLOAD REPORT
# --------------------------------------------------

def create_downloadable_report(final_report):
    """Build the Markdown report for download."""

    logger.info("[DOWNLOAD] Preparing Markdown report")

    lines = ["# Resume Analysis"]

    for key, heading in REPORT_SECTIONS:
        lines.append("## " + heading)
        lines.append(final_report[key])

    result = "\n\n".join(lines)

    logger.info(
        "[DOWNLOAD] Markdown report prepared; %d characters",
        len(result),
    )

    return result


# --------------------------------------------------
# 7. STREAMLIT APPLICATION
# --------------------------------------------------

def main():
    logger.info("[APP] Streamlit application started")

    st.set_page_config(page_title="AI Resume Analyzer")
    st.title("AI Resume Analyzer")

    st.write(
        "Upload your resume and paste a Job Description to identify "
        "strengths, gaps, and improvement opportunities."
    )

    uploaded_file = st.file_uploader(
        "Upload your resume",
        type=["pdf", "docx"],
    )

    job_description = st.text_area(
        "Paste the Job Description",
        height=250,
    )

    if st.button("Analyze Resume"):
        run_start = time.perf_counter()

        logger.info("[APP] Analyze Resume button clicked")

        try:
            # Validate inputs
            if uploaded_file is None:
                logger.warning("[APP] Resume file was not uploaded")
                st.warning("Please upload your resume.")
                st.stop()

            if not job_description.strip():
                logger.warning("[APP] Job description is empty")
                st.warning("Please paste the Job Description.")
                st.stop()

            logger.info(
                "[APP] Input validation passed; file=%s; JD length=%d",
                uploaded_file.name,
                len(job_description),
            )

            # Step 1: Extract resume text
            with st.spinner("Extracting resume text..."):
                resume_text = extract_resume_text(uploaded_file)

            if not resume_text:
                logger.warning("[APP] Resume text extraction returned empty text")

                st.warning(
                    "No text could be read from this file. "
                    "Text-based PDFs and DOCX files are supported. "
                    "Scanned PDFs require OCR."
                )
                st.stop()

            # Steps 2 and 3: Call Ollama twice
            with st.spinner(
                "Analyzing resume with Ollama. This may take a few minutes..."
            ):
                logger.info("[APP] Starting analysis pipeline")

                structured_analysis = analyze_resume(
                    resume_text,
                    job_description,
                )

                logger.info(
                    "[APP] First LLM call completed; starting report generation"
                )

                final_report = generate_final_report(
                    structured_analysis,
                )

                logger.info("[APP] Both LLM calls completed successfully")

            st.session_state["final_report"] = final_report

            logger.info(
                "[APP] Entire analysis pipeline completed in %.2f seconds",
                time.perf_counter() - run_start,
            )

        except requests.exceptions.Timeout:
            logger.exception("[APP] Ollama request timed out")

            st.error(
                "Ollama took too long to respond. "
                "Check app.log to identify which request timed out."
            )
            st.stop()

        except requests.exceptions.ConnectionError:
            logger.exception("[APP] Cannot connect to Ollama")

            st.error(
                "Cannot connect to Ollama. Make sure Ollama is running "
                "and check OLLAMA_BASE_URL in your .env file."
            )
            st.stop()

        except Exception:
            logger.exception("[APP] Analysis pipeline failed")

            st.error(
                "The analysis failed. Open app.log for the detailed error."
            )
            st.stop()

    # Step 4: Display report
    if "final_report" in st.session_state:
        logger.info("[UI] Displaying analysis results")

        final_report = st.session_state["final_report"]

        st.divider()
        st.subheader("Analysis Results")

        for key, heading in REPORT_SECTIONS:
            logger.info("[UI] Displaying section: %s", key)
            st.markdown("### " + heading)
            st.markdown(final_report[key])

        download_content = create_downloadable_report(final_report)

        st.download_button(
            "Download Report",
            data=download_content,
            file_name="resume_analysis.md",
            mime="text/markdown",
        )

        logger.info("[UI] Report display completed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("[APP] Unhandled application error")
        raise