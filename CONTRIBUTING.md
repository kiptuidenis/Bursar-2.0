# Contributing to Bursar 2.0

Thank you for your interest in contributing to **Bursar 2.0**! Whether you are fixing bugs, improving documentation, adding new payment integrations, or enhancing security, your contributions are welcome and appreciated.

---

## Table of Contents
1. [Code of Conduct](#code-of-conduct)
2. [Development Environment Setup](#development-environment-setup)
3. [Branching & Commit Guidelines](#branching--commit-guidelines)
4. [Coding & Security Standards](#coding--security-standards)
5. [Running Tests](#running-tests)
6. [Submitting a Pull Request](#submitting-a-pull-request)
7. [Reporting Issues](#reporting-issues)

---

## Code of Conduct
We are committed to providing a welcoming, inclusive, and harassment-free environment for all contributors. Please be respectful, constructive, and collaborative in all project discussions, issue tickets, and code reviews.

---

## Development Environment Setup

### 1. Prerequisites
- **Python 3.10+** (Python 3.11+ recommended)
- **Node.js 18+** & **npm** (for Playwright E2E browser testing)
- **Git**

### 2. Fork and Clone the Repository
```bash
git clone https://github.com/kiptuidenis/Bursar-2.0.git
cd Bursar-2.0
```

### 3. Create a Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
# Install Python backend dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Node dependencies (for E2E browser testing)
npm install
npx playwright install --with-deps
```

### 5. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
For local development, you can use SQLite and simulation payment modes without needing live Safaricom or IntaSend API keys.

---

## Branching & Commit Guidelines

### Branch Naming Conventions
Always create a descriptive branch for your work:
- `feature/add-apple-pay-support`
- `bugfix/fix-scheduler-timezone-parsing`
- `security/patch-session-cookie-attributes`
- `docs/update-architecture-diagram`
- `test/add-idempotency-e2e-tests`

### Commit Message Standards
Write clear, imperative commit messages following the Conventional Commits specification:
```text
feat(scheduler): implement atomic retry on transient gateway network failure
fix(auth): enforce constant-time comparison on password reset tokens
docs(readme): add interactive cURL demo snippets and architecture flowchart
test(deposits): add race-condition test for simultaneous webhook callbacks
```

---

## Coding & Security Standards

### Python & Backend Guidelines
- **PEP 8 Compliance**: Follow standard Python naming and formatting conventions.
- **Type Annotations**: Provide explicit type hints for function signatures and return types.
- **Clean Architecture**: Keep business logic in `services/`, database operations in `db/manager.py`, and endpoint route handling in `api/routers/`.
- **Defensive Error Handling**: Never leak raw SQL or stack traces to clients in API responses. Return standardized HTTP error responses.
- **Idempotency & Concurrency**: Ensure all financial state changes (deposits, payouts, balance deductions) are guarded by atomic database operations or unique constraints to prevent double-spending and race conditions.
- **Security-First**:
  - Never log raw secrets, API keys, or full card/PIN details.
  - Store sensitive user secrets encrypted using the core encryption utilities.
  - Sanitize all user inputs and enforce rate limiting on public-facing endpoints.

---

## Running Tests

All pull requests must pass the complete test suite before merging.

### Run Python Unit & Integration Tests
```bash
# Run full pytest suite
python -m pytest

# Run specific test modules
python -m pytest tests/test_db.py
python -m pytest tests/test_scheduler.py
python -m pytest tests/test_idempotency.py
```

### Run Static Audits & Syntax Checks
```bash
python tests/check_js_syntax.py
```

### Run Playwright End-to-End Tests
```bash
npm run test:e2e
```

---

## Submitting a Pull Request

1. **Keep PRs Focused**: Keep pull requests focused on a single feature or bug fix.
2. **Include Tests**: Add unit or integration tests covering new features or bug fixes.
3. **Verify CI**: Ensure all tests and static audits pass locally.
4. **Open a PR**:
   - Open a pull request against the `main` branch.
   - Describe what changed and why.
   - Link any related issue numbers (e.g., `Resolves #42`).
   - Request a review from the maintainers.

---

## Reporting Issues

If you find a bug or have a feature proposal:
1. Search existing issues to ensure it hasn't already been reported.
2. Open a new issue with:
   - A clear and descriptive title.
   - Steps to reproduce the behavior.
   - Expected vs. actual behavior.
   - Relevant log snippets or screenshots (ensure no API keys or personal data are exposed).

---

*Thank you for helping make Bursar 2.0 more reliable, secure, and impactful!*
