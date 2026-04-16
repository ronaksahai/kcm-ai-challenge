# KCM AI Suite

**Intelligent document processing tools for Corporate Tax professionals.**

KCM AI Suite is an installable desktop application designed for CA firms. It leverages Sarvam AI's advanced Indian language processing capabilities to automate document workflows.

---

## 🌐 Module 1: Document Translator

Translate scanned legal documents from **Gujarati**, **Hindi**, and **Marathi** to **English** — powered by Sarvam AI.

### Supported Document Types
- Sale deeds & Property documents
- Purchase agreements
- Accounting ledgers
- Interest certificates
- Authoritative / Government documents

### How It Works
1. **Upload** a scanned PDF document
2. **OCR** — Sarvam Vision extracts text while preserving layout
3. **Translate** — Sarvam Translate converts to English
4. **Download** — Get the translated document as PDF or RTF

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- A Sarvam AI API key ([Get one here](https://dashboard.sarvam.ai/))

### Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd kcm-ai-challenge

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
#    Open .env and replace the placeholder with your actual Sarvam AI API key
notepad .env
```

### Run the App

```bash
python -m app.main
```

The app will open in a native desktop window. If `pywebview` is not installed, it will fall back to your default browser.

---

## 📦 Building an Installer

To package the app as a standalone `.exe`:

```bash
pip install pyinstaller
pyinstaller --name "KCM AI Suite" --onefile --windowed --add-data "app/templates;app/templates" --add-data "app/static;app/static" --add-data ".env;." app/main.py
```

The executable will be in the `dist/` folder.

---

## 🏗️ Project Structure

```
kcm-ai-challenge/
├── app/
│   ├── main.py              # Entry point (pywebview + Flask)
│   ├── config.py             # Configuration & environment loading
│   ├── server.py             # Flask API routes & pipeline orchestration
│   ├── services/
│   │   ├── ocr_service.py    # Sarvam Document Intelligence integration
│   │   ├── translate_service.py  # Sarvam Translate with chunking
│   │   ├── pdf_service.py    # PDF splitting & generation (ReportLab)
│   │   └── rtf_service.py    # RTF generation
│   ├── templates/
│   │   └── index.html        # App UI
│   └── static/
│       ├── css/styles.css    # Dark-mode design system
│       └── js/app.js         # Frontend logic
├── .env                      # Sarvam API key (configure this!)
├── requirements.txt          # Python dependencies
└── README.md
```

---

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SARVAM_API_KEY` | Your Sarvam AI API subscription key | *(required)* |

Edit the `.env` file in the project root to set your API key.

---

## 📝 License

Internal use — KC Mehta Co. & LLP