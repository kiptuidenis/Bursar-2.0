# Step-by-Step Guide: Testing with IntaSend Sandbox

This guide outlines how to set up, configure, and verify your Safaricom M-Pesa STK Push and B2C payout flows using the **IntaSend Sandbox (Testnet)** before deploying live with real currency.

---

## 1. Obtain IntaSend Sandbox API Credentials

Before writing any configuration, you need test API keys from IntaSend:

1. Log in to your [IntaSend Dashboard](https://payment.intasend.com/).
2. In the top-right corner or menu, switch the environment toggle from **Live** to **Sandbox / Test Environment**.
3. Navigate to **API Keys** under Settings.
4. Copy the following values:
   - **Sandbox Secret Key** (starts with `ISSecretKey_sandbox_...`)
   - **Sandbox Publishable Key** (starts with `ISPubKey_sandbox_...`)

---

## 2. Configure Environment Variables (`.env`)

You must update the local environment variables of your self-hosted application to point to the test environment:

1. Open your `.env` file in the root of the **Bursar 2.0** project: [Bursar 2.0 .env](file:///f:/Bursar%202.0/.env).
2. Edit or add the following variables:
   ```env
   # Set the gateway mode globally to sandbox
   INTASEND_MODE=sandbox

   # Insert your Sandbox API keys copied from the IntaSend dashboard
   INTASEND_SECRET_KEY=ISSecretKey_sandbox_your_actual_test_secret_key
   INTASEND_PUBLISHABLE_KEY=ISPubKey_sandbox_your_actual_test_publishable_key
   ```
3. Restart your Bursar 2.0 server process to load the updated environment configuration.

Your application is now configured to make real API requests to the IntaSend Sandbox servers!

---

## 3. Run a Sandbox STK Push Test Deposit

Now that sandbox is enabled, you can simulate a real M-Pesa transaction:

1. On the dashboard, click **Deposit Funds**.
2. Enter an amount (e.g., `1000`) and click **Confirm Deposit**.
3. Since you are using the IntaSend Sandbox, **no real money will be charged**.
4. To simulate a successful payment prompt, use the IntaSend Sandbox test phone numbers and payment simulation tools on the IntaSend dashboard.
5. Verify that:
   - The M-Pesa STK Push popup overlay starts polling.
   - Once confirmed, your balance updates correctly on the dashboard, and the budget/deposits are locked.
   - The transaction logs record a successful verification event.

---

## 4. Switch to Production (Live Mode)

Once you have verified that the sandbox STK push and payouts function seamlessly:

1. Switch your IntaSend dashboard back to **Live Environment**.
2. Obtain your Live API Keys (starting with `ISSecretKey_live_...` and `ISPubKey_live_...`).
3. Update your `.env` file:
   ```env
   INTASEND_MODE=live
   INTASEND_SECRET_KEY=ISSecretKey_live_your_actual_production_secret_key
   INTASEND_PUBLISHABLE_KEY=ISPubKey_live_your_actual_production_publishable_key
   ```
4. Restart your application server.
