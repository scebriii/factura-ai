# FacturaAI — AI-Powered Invoice Extraction API

A REST API that receives a PDF invoice, extracts structured data using OpenAI GPT-4o-mini, stores it in SQLite, and exposes a dashboard with KPIs, charts, search, and CSV export.

Built as a learning project: Python + FastAPI + OpenAI, zero frameworks on the frontend.

<video src="demo%20prueba.mp4" width="100%" controls></video>

---

## Features

- **PDF → JSON**: Upload any invoice PDF, get back structured data (supplier, tax ID, amount, date, line items)
- **Dashboard**: 4 KPIs + monthly spend bar chart + top suppliers donut chart
- **History table**: search, filter, delete, export to CSV (Excel-compatible)
- **API key auth**: all endpoints protected via `X-API-Key` header
- **Zero JS frameworks**: vanilla JS frontend served by the same FastAPI server

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| AI extraction | OpenAI GPT-4o-mini |
| PDF parsing | PyMuPDF (fitz) |
| Database | SQLite (built-in, no setup) |
| Frontend | Vanilla JS + Chart.js |
| Testing | pytest + FastAPI TestClient |

## Quick Start

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd factura-ai

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate          # macOS / Linux
venv\Scripts\activate             # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your OpenAI API key and a secret app key

# 5. Start the server
python -m scripts.main

# Open http://localhost:8000
```

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key — get one at platform.openai.com |
| `API_KEY_APP` | Secret key sent in `X-API-Key` header to authenticate requests |

## API Reference

All endpoints except `/salud` require the `X-API-Key` header.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/salud` | Health check — no auth required |
| `POST` | `/extraer-factura` | Upload a PDF, get extracted JSON |
| `GET` | `/facturas` | List all processed invoices |
| `DELETE` | `/facturas/{id}` | Delete an invoice by ID |
| `GET` | `/estadisticas` | KPIs and chart data for the dashboard |

Interactive docs available at `http://localhost:8000/docs` when the server is running.

### Example: Extract an invoice

```bash
curl -X POST http://localhost:8000/extraer-factura \
  -H "X-API-Key: your-app-key" \
  -F "archivo=@factura.pdf"
```

```json
{
  "exito": true,
  "id_factura": 42,
  "archivo_original": "factura.pdf",
  "datos": {
    "proveedor": "Acme SL",
    "cif_nif": "B12345678",
    "numero_factura": "F-2024-001",
    "fecha": "2024-01-15",
    "importe_total": 1452.0,
    "moneda": "EUR",
    "conceptos": ["Software license", "Support hours"]
  }
}
```

## Running Tests

```bash
pip install pytest httpx
pytest tests/ -v
```

## Deploy to Railway

1. Push this repo to GitHub
2. Create a new project at [railway.app](https://railway.app)
3. Connect your GitHub repo — Railway auto-detects the `Procfile`
4. Set environment variables: `OPENAI_API_KEY` and `API_KEY_APP`
5. Deploy

## Project Structure

```
├── scripts/
│   └── main.py          # FastAPI app — all endpoints, DB logic, OpenAI integration
├── frontend/
│   ├── index.html       # Single-page dashboard
│   ├── styles.css       # Design system (oklch color tokens, dark theme)
│   └── app.js           # Chart.js dashboard, drag-drop upload, table logic
├── tests/
│   └── test_api.py      # pytest tests — auth, CRUD, extraction, stats
├── .env.example         # Environment variable template
├── Procfile             # Railway / Render deployment config
└── requirements.txt     # Python dependencies
```
