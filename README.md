# Bursar 2.0 — Automated Daily Budget Allowance for M-Pesa Users

> **Live App → [bursar.co.ke](https://bursar.co.ke)**

Bursar 2.0 is a personal money-management web application designed to help Kenyan M-Pesa users beat impulse spending by converting lump-sum income into controlled, automated daily allowances. Instead of keeping your entire monthly budget on M-Pesa where it is easy to overspend, you deposit it into Bursar — and Bursar sends it back to your M-Pesa in precise daily amounts, at the time you choose, every single day.

---

## The Problem Bursar Solves

Most people receive their salary, freelance payment, or business income as a lump sum at the start of the month. With the full amount sitting in M-Pesa and instantly accessible, it is very easy to overspend in the first two weeks and struggle for the rest of the month.

**Bursar's answer:** Lock your monthly budget inside the app. Every day, at a time you choose, Bursar automatically sends you exactly your pre-planned daily allowance — no more, no less — directly to your M-Pesa number via a real M-Pesa B2C payout.

---

## Who It's For

- **Salaried workers** who want their monthly income to last the full 30 days.
- **Students** on a fixed monthly allowance who need to stretch every shilling.
- **Freelancers** who receive irregular bulk payments and need self-imposed daily caps.
- **Anyone** who uses M-Pesa as their primary spending account and struggles with impulse spending.

---

## Key Features

### 💰 Automated Daily Payouts
A background scheduler daemon continuously monitors your configured payout time. When the clock strikes your chosen hour, Bursar automatically initiates a real M-Pesa B2C transfer of your exact daily budget amount to your registered Safaricom number — with no manual action required.

### 📊 Budget Planning by Category
Define your daily budget across spending categories (e.g., Food, Transport, Airtime). The sum of your categories becomes your locked daily allowance. Once set and deposited, categories cannot be changed mid-month — keeping you accountable to your own plan.

### 🔒 Enforced Budget Locks (Anti-Temptation Design)
Once you deposit funds and lock your budget, the balance is protected at the database level. Neither you nor the system can reduce it manually until the month ends. This is the core mechanism that makes Bursar effective — removing the temptation to dip into tomorrow's money.

### 📥 M-Pesa STK Push Deposits
Topping up your Bursar wallet is seamless. Enter an amount and Bursar sends an STK Push directly to your phone. Authorize it with your M-Pesa PIN and the funds are credited — no bank transfers or manual paybill entries needed.

### 🤖 AI Chat Assistant (Coming Soon)
An in-app AI assistant powered by Google Gemini answers questions about how Bursar works. It uses a BM25 Retrieval-Augmented Generation (RAG) engine backed by Bursar's own documentation — ensuring answers are grounded in verified facts, not hallucinations.

### 🛡️ Double-Spend Protection
The scheduler uses database-level unique constraints to guarantee each day's payout fires exactly once, even across multiple scheduler ticks or manual trigger attempts.

### 🔐 Security-First Authentication
- Passwords/PINs hashed with **PBKDF2-HMAC-SHA256** (100,000 iterations — NIST recommended standard).
- **HTTP-only cookie sessions** that are immune to JavaScript-based XSS theft.
- Sessions expire automatically after 24 hours of inactivity.
- **Google reCAPTCHA v3** on login and registration to block bot submissions.
- M-Pesa PIN is **never** seen or stored by Bursar — STK Push authorization happens directly on your phone.

### 📈 Interactive Pacing Dashboard
A live Chart.js area chart reconstructs your 7-day wallet balance trend so you can see at a glance whether your spending is on pace, ahead, or behind your monthly plan.

### 👤 User Profiles & Theming
Upload an avatar, add a bio, and switch between visual themes — a light, premium UI designed with glassmorphism, vibrant gradients, and Outfit/JetBrains Mono typography.

---

## Architecture Overview

```
bursar-2.0/
├── src/
│   └── app/                        # Core FastAPI application package
│       ├── main.py                 # Application entry point, lifespan, CORS, routing
│       ├── api/
│       │   ├── dependencies.py     # Shared DI: DB manager, session manager
│       │   ├── schemas.py          # Pydantic request/response schemas
│       │   └── routers/
│       │       ├── auth.py         # Register, login, logout endpoints
│       │       ├── budget.py       # Budget category CRUD
│       │       ├── deposits.py     # STK Push initiation & status polling
│       │       ├── payouts.py      # Manual payout trigger & payout history
│       │       ├── callbacks.py    # M-Pesa & IntaSend webhook handlers
│       │       ├── settings.py     # User settings (payout time, API keys, dates)
│       │       ├── profile.py      # User profile management & avatar upload
│       │       └── chat.py         # AI chat assistant endpoint
│       ├── core/
│       │   ├── config.py           # Environment variable loading & app config
│       │   └── security.py         # PBKDF2 hashing, session token signing
│       ├── db/
│       │   ├── models.py           # SQLAlchemy ORM models (User, Payout, Deposit …)
│       │   └── manager.py          # Database CRUD operations & lock enforcement
│       ├── services/
│       │   ├── scheduler.py        # Background payout daemon (60-second poll loop)
│       │   ├── payment_gateway.py  # Unified payment abstraction layer
│       │   ├── mpesa.py            # Safaricom Daraja B2C & STK Push client
│       │   ├── intasend.py         # IntaSend B2C & STK Push client
│       │   ├── ai.py               # Gemini API integration & RAG prompt builder
│       │   ├── rag.py              # BM25 retrieval-augmented generation engine
│       │   └── recaptcha.py        # Google reCAPTCHA v3 verification
│       └── static/
│           ├── index.html          # Landing page (register / login)
│           ├── dashboard.html      # Main authenticated dashboard
│           ├── css/style.css       # Glassmorphic stylesheet
│           ├── js/                 # Client-side routing, chart loops, API calls
│           └── docs/               # Markdown knowledge base for the RAG assistant
│               ├── about.md
│               ├── faq.md
│               ├── locks.md
│               ├── payouts.md
│               └── security.md
├── tests/                          # Automated unit & integration tests
│   ├── test_auth.py                # Session signing & HMAC verification
│   ├── test_db.py                  # Database models & multi-tenant isolation
│   ├── test_db_features.py         # Lock mechanics & edge-case coverage
│   ├── test_main.py                # API endpoints, cookies, CORS
│   ├── test_mpesa.py               # M-Pesa client signing & mock payloads
│   ├── test_intasend.py            # IntaSend client mock tests
│   ├── test_scheduler.py           # Scheduler logic & concurrency protection
│   ├── test_scheduler_polling.py   # Full polling-loop integration tests
│   ├── test_budget_deposit_validation.py
│   ├── test_payout_trigger_diagnostics.py
│   ├── test_chat.py                # AI chat endpoint tests
│   ├── test_profile.py             # Profile API tests
│   ├── test_recaptcha.py           # reCAPTCHA verification tests
│   ├── test_inactivity.py          # Session inactivity timeout tests
│   ├── test_unhandled_errors.py    # Global error handler tests
│   └── e2e/                        # Playwright end-to-end browser tests
├── .env.example                    # Environment variable template
├── playwright.config.js            # Playwright E2E test configuration
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## Payment Gateways

Bursar 2.0 supports two payment backends that can be toggled via environment configuration:

| Gateway | Deposits (STK Push) | Payouts (B2C) | Modes |
|---|---|---|---|
| **IntaSend** | ✅ | ✅ | `simulation`, `sandbox`, `live` |
| **Safaricom Daraja** | ✅ | ✅ | `simulation`, `sandbox`, `live` |

The active gateway is selected per-user via their account settings, giving flexibility for testing and production.

---

## Setup & Installation

### Prerequisites
- Python **3.10+**
- A Safaricom Daraja or IntaSend developer account (for sandbox/live modes)
- A Google Gemini API key (for the AI assistant)

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/bursar-2.0.git
cd bursar-2.0
```

### 2. Create and Activate a Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the example env file and fill in your credentials:
```bash
cp .env.example .env
```

Key variables to configure in `.env`:

```env
# App secret
SECRET_KEY=your_secure_random_secret_key

# Payment gateway (intasend or mpesa)
PAYMENT_PROVIDER=intasend
INTASEND_MODE=sandbox
INTASEND_SECRET_KEY=your_intasend_secret_key
INTASEND_PUBLISHABLE_KEY=your_intasend_publishable_key

# Google Gemini AI
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Google reCAPTCHA v3
RECAPTCHA_ENABLED=true
RECAPTCHA_SITE_KEY=your_recaptcha_site_key
RECAPTCHA_SECRET_KEY=your_recaptcha_secret_key
```

### 5. Run the Development Server
```bash
python -m uvicorn src.app.main:app --reload --port 8000
```

Navigate to **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## Running Automated Tests

Bursar 2.0 has an extensive test suite covering all core layers — database, authentication, scheduler, payment gateway, and API endpoints.

### Unit & Integration Tests (pytest)
```bash
python -m pytest
```

### End-to-End Browser Tests (Playwright)
```bash
npx playwright test
```

---

## How the Payout Scheduler Works

1. **On startup**, a `BackgroundScheduler` thread launches and polls every **60 seconds**.
2. Each tick fetches all active users and evaluates whether a payout is due:
   - Is the user's budget **locked**?
   - Is the current time **at or past** the user's configured `payout_time`?
   - Is today's date **within** the user's configured `start_date` / `end_date` window?
   - Has a payout for **today already been recorded**? (double-spend check)
3. If all conditions pass, the scheduler deducts the daily budget from the wallet balance, records a `PENDING` payout, and fires the B2C API call.
4. If the API call fails, the deducted balance is **refunded** to the wallet and the payout is marked `FAILED` for auditing.
5. A subsequent tick picks up any pending payouts to check their transaction status via the gateway's status API.


---

## Live Application

**[bursar.co.ke](https://bursar.co.ke)** — The production deployment of Bursar 2.0.

---

## License

This project is proprietary. All rights reserved.
