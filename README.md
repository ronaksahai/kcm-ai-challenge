# KCM AI Suite

**Intelligent document processing tools for Corporate Tax professionals.**

KCM AI Suite is an intelligent web application designed for CA firms. It leverages Google Gemini's advanced processing capabilities to automate document translation, tax scrutiny, notice replies, and case law research.

---

## 🌐 Module 1: Document Translator

Translate scanned legal documents from **Gujarati**, **Hindi**, and **Marathi** to **English** — powered by Google Gemini.

### Supported Document Types
- Sale deeds & Property documents
- Purchase agreements
- Accounting ledgers
- Interest certificates
- Authoritative / Government documents

### How It Works
1. **Upload** a scanned PDF document
2. **Translate** — Google Gemini extracts text and translates it to English while preserving context
3. **Download** — Get the translated document as PDF or RTF

---

## 📊 Module 2: Order Scrutiny

Automate the analysis of Income Tax Intimation orders and computation sheets to generate a comprehensive discrepancy report.

### How It Works
1. **Upload** the password-protected Intimation PDF and the related Computation Sheet (Excel).
2. **Parse** — Securely extracts text from the Intimation order and tabular data from the computation sheet.
3. **Analyze** — Powered by Gemini AI, it compares the Intimation data with the Computation sheet line-by-line.
4. **Download** — Generates a beautifully formatted Excel report highlighting variances, matched amounts, and automated remarks for the discrepancy.

---

## ✍️ Module 3: Notice Reply Drafting

Automatically draft reply skeletons for Income Tax Department notices and generate checklists for clients.

### How It Works
1. **Upload** the Income Tax Notice PDF (e.g., u/s 142(1), 143(2)).
2. **Extract & Analyze** — Gemini AI extracts all the points, data requirements, and contextual information from the notice.
3. **Generate Reply** — Automatically creates a professionally formatted Word (`.docx`) skeleton reply addressing each point from the notice individually.
4. **Generate Checklist** — Generates an Excel (`.xlsx`) 'Details Required' sheet for the client.
5. **Email Draft** — Provides a ready-to-send email template to the client requesting the required documents.

---

## ⚖️ Module 4: Case Law Finder

Find precedents and case laws with matching facts for your tax scenario using deep AI analysis.

### How It Works
1. **Describe Scenario** — Enter your tax issue, dispute, or notice details.
2. **Search** — Automatically searches Indian Kanoon and Taxmann for relevant cases.
3. **Analyze** — Gemini AI reads the full case texts to find the most relevant facts.
4. **Report** — Provides a comprehensive summary of relevant case laws with clickable citation links.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- A Google Cloud Platform (GCP) Project with Vertex AI API enabled
- A GCP Service Account JSON key (or use Application Default Credentials)

### Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd kcm-ai-challenge

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate   # macOS/Linux (or venv\Scripts\activate on Windows)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your GCP settings
#    Open .env and set GCP_PROJECT_ID and GCP_LOCATION
nano .env
```

### Run Locally

```bash
python -m app.main
```

The app will start a local web server (using Flask/Gunicorn) and be available at `http://localhost:5767`.

### Deploy to Google Cloud Run

```bash
gcloud run deploy kcm-ai-suite \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 3 \
  --no-cpu-throttling \
  --session-affinity
```

---

## 🏗️ Project Structure

```
kcm-ai-challenge/
├── Dockerfile                # Production container configuration
├── .dockerignore             # Excluded files for Docker build
├── .gcloudignore             # Excluded files for Cloud Run deploy
├── app/
│   ├── main.py              # Entry point (Starts server)
│   ├── config.py            # Configuration & environment loading
│   ├── server.py            # Flask API routes & pipeline orchestration
│   ├── services/
│   │   ├── translate_service.py # Gemini Translate
│   │   ├── rtf_service.py       # RTF generation
│   │   ├── scrutiny_extract.py  # PDF and Excel extraction for Order Scrutiny
│   │   ├── scrutiny_excel.py    # Excel discrepancy report generation
│   │   ├── scrutiny_service.py  # Order Scrutiny AI analysis & orchestration
│   │   ├── notice_service.py    # Notice Reply AI analysis & orchestration
│   │   ├── notice_docx.py       # DOCX reply skeleton generation
│   │   ├── notice_excel.py      # Client Checklist Excel generation
│   │   └── caselaw_service.py   # Case Law Finder analysis & orchestration
│   ├── templates/
│   │   └── index.html        # App UI
│   └── static/
│       ├── css/styles.css    # Dark-mode design system
│       └── js/app.js         # Frontend logic
├── .env                      # API keys (configure this!)
├── requirements.txt          # Python dependencies
└── README.md
```

---

## ⚙️ Configuration

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | Your Google Cloud Project ID *(required for Vertex AI)* |
| `GCP_LOCATION` | Your Google Cloud location (e.g., `us-central1`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to your GCP service account JSON key |

Edit the `.env` file in the project root to set your configuration.

---

## 📝 License

Internal use — KC Mehta Co. & LLP