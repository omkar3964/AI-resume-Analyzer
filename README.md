# 🤖 AI Resume Analyzer

An AI-powered resume analysis tool built with **Python, Streamlit, and Ollama**. It compares a candidate's resume with a job description using a locally running LLM and generates a report with strengths, skill gaps, and improvement suggestions.

## ✨ Features

* Upload resumes in PDF and DOCX formats.
* Extract resume text automatically.
* Analyze resumes against job descriptions.
* Identify matching, missing, and weakly demonstrated skills.
* Generate strengths, gaps, and improvement suggestions.
* Download the final analysis report.
* Run AI inference locally using Ollama.

## 🛠️ Tech Stack

* **Python** — Application logic
* **Streamlit** — Web interface
* **Ollama** — Local LLM runtime
* **Llama 3.2 3B** — Language model
* **pypdf & python-docx** — Resume text extraction
* **Requests & python-dotenv** — API communication and configuration

## 🔄 Workflow

```text
Upload Resume + Job Description
              ↓
       Extract Resume Text
              ↓
      Analyze Using Ollama
              ↓
       Generate Final Report
              ↓
       Display and Download
```

The application uses two AI requests: one for structured resume analysis and another for generating the final report.

## ⚙️ Installation and Setup

### 1. Prerequisites

Install [Python](https://www.python.org/downloads/) and [Ollama](https://ollama.com/download).

### 2. Clone the repository

```bash
git clone https://github.com/omkar3964/AI-resume-Analyzer.git
cd AI-resume-Analyzer
```

### 3. Create a virtual environment

**Windows PowerShell**

```powershell
python -m venv myenv
.\myenv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv myenv
source myenv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

Ensure `requirements.txt` includes all packages imported by the application, including Streamlit, Requests, python-dotenv, pypdf, and python-docx.

### 5. Download the AI model

```bash
ollama pull llama3.2:3b
```

Ensure Ollama is running locally.

### 6. Configure `.env`

Create a `.env` file in the project root:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

Do not upload this file to GitHub.

### 7. Run the application

```bash
streamlit run app.py
```

Open the URL displayed in your terminal, usually `http://localhost:8501`.

## 🖥️ How to Use

1. Upload your resume in PDF or DOCX format.
2. Paste the target job description.
3. Click **Analyze Resume**.
4. Wait for the analysis to complete.
5. Review and download your report.

## 📊 Final Output

The generated report contains:

* **Strengths:** Relevant skills, projects, and qualifications.
* **Gaps:** Job requirements not clearly demonstrated in the resume.
* **Missing or Weak Skills:** Skills that need stronger evidence.
* **Improvement Suggestions:** Practical recommendations for improving the resume.
* **Overall Summary:** A concise assessment of resume alignment with the job description.

## 🔐 Privacy

The default configuration runs the model locally through Ollama without requiring a hosted AI API key. Avoid uploading resumes, private reports, `.env` files, or sensitive logs to public repositories.

**Note:** AI-generated results may be inaccurate. Review the report before using it for career decisions.

## 🚀 Future Enhancements

* OCR support for scanned resumes.
* PDF and DOCX report exports.
* Additional model options.
* Improved error handling and automated testing.

---

**Built with Python, Streamlit, and Ollama.**
