# Bursar 2.0 — Premium Personal Money Manager

Bursar 2.0 is a secure, automated micro-allowance scheduler designed to help users budget and manage daily allocations. The application schedules daily budget payouts to a Safaricom mobile number using Safaricom's Daraja B2C API and provides real-time visualization of wallet pacing.

---

## Key Features

- **Multi-Tenant Authentication**: Cryptographically signed cookie session auth (using PBKDF2 for password PIN hashing).
- **Automated Pacing Scheduler**: A background daemon that checks and executes budget distributions at user-specified daily times.
- **Safaricom M-Pesa Integration**: Supported via simulation, sandbox, and live Daraja B2C payout flows (double-spend protected).
- **Interactive Pacing Area Chart**: A premium Chart.js area graph that reconstructs 7-day wallet balance trends.
- **Glassmorphic Theme**: A modern CSS design utilizing Outfit/JetBrains Mono typography, vibrant glow backgrounds, and responsive visual cards.

---

## Directory Structure

```
bursar-2.0/
├── app/                  # Core FastAPI application package
│   ├── __init__.py       # Package initializer
│   ├── auth.py           # Cookie session auth layer
│   ├── db.py             # SQLite database layer (Double-Spend Protected)
│   ├── main.py           # API endpoints & lifespan context
│   ├── mpesa.py          # Safaricom Daraja API client
│   ├── scheduler.py      # Background daemon scheduler
│   └── static/           # Static frontend assets
│       ├── css/
│       │   └── style.css # Custom glassmorphism stylesheet
│       ├── js/
│       │   └── app.js    # Client-side routing, inputs, and chart loops
│       └── index.html    # Core dashboard interface
├── tests/                # Automated unit & integration tests
│   ├── test_auth.py      # HMAC session verification test suite
│   ├── test_db.py        # Database models & multi-tenant isolation tests
│   ├── test_main.py      # Endpoints, cookies, and CORS verification
│   ├── test_mpesa.py      # Client signing & payload encryption mock tests
│   └── test_scheduler.py # Scheduler logic & concurrency protection tests
├── .gitignore            # Version control exclusions
├── requirements.txt      # Python dependencies
└── README.md             # Project documentation
```

---

## Setup & Installation

### 1. Prerequisite Setup
Ensure Python 3.10+ is installed on your system.

### 2. Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Running the Development Server
Launch the Uvicorn ASGI server with hot-reloading:
```bash
python -m uvicorn app.main:app --reload --port 8000
```
Then navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

---

## Running Automated Tests

We verify all core layers (database, API endpoints, encryption, and daemon loops) using `pytest`. Run the following command from the root directory:
```bash
python -m pytest
```
All 24 test cases will execute and print the status summary.
