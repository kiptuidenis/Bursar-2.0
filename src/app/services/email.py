import logging
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

from app.core import config

logger = logging.getLogger(__name__)

# Test mode mock email store for unit test assertions
last_sent_otp_emails: Dict[str, Dict[str, Any]] = {}

def format_otp_email_html(otp_code: str, purpose: str) -> str:
    """Format branded, responsive HTML email template for 6-digit OTP verification."""
    purpose_title = "Two-Factor Verification Code"
    if purpose == "signup_2fa":
        purpose_title = "Welcome to Bursar 2.0 - Verify Your Email"
    elif purpose == "payout_stepup":
        purpose_title = "Payout Step-Up Authorization Code"
    elif purpose == "phone_update":
        purpose_title = "Update Payout Phone Authorization Code"
    elif purpose == "wallet_withdrawal":
        purpose_title = "Authorize Cash Withdrawal"
    elif purpose == "password_change":
        purpose_title = "Authorize Password Change"
    elif purpose == "account_deactivation":
        purpose_title = "Authorize Account Deactivation"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{purpose_title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 0; }}
        .container {{ max-width: 540px; margin: 40px auto; background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; font-size: 16px; line-height: 1.5; }}
        .header {{ background-color: #0284c7; padding: 24px; text-align: center; }}
        .header h1 {{ color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
        .content {{ padding: 32px 24px; text-align: center; }}
        .otp-box {{ background-color: #0f172a; border: 2px dashed #0284c7; border-radius: 8px; padding: 18px; margin: 24px 0; display: inline-block; width: 80%; }}
        .otp-code {{ font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #38bdf8; margin: 0; font-family: 'Courier New', Courier, monospace; }}
        .footer {{ padding: 20px 24px; background-color: #0f172a; border-top: 1px solid #334155; text-align: center; font-size: 13px; color: #94a3b8; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Bursar 2.0 Security</h1>
        </div>
        <div class="content">
            <h2 style="color: #f8fafc; margin-top: 0;">{purpose_title}</h2>
            <p style="color: #cbd5e1;">Your 6-digit verification code is below. This code will expire in <strong>5 minutes</strong>.</p>
            <div class="otp-box">
                <p class="otp-code">{otp_code}</p>
            </div>
            <p style="color: #94a3b8; font-size: 14px;">If you did not request this verification code, please ignore this email or contact support immediately.</p>
        </div>
        <div class="footer">
            <p>&copy; {config.APP_NAME} | Bursar Financial Systems. Sent from {config.SES_SENDER_EMAIL} | Support: {config.SUPPORT_EMAIL}</p>
        </div>
    </div>
</body>
</html>"""

def format_otp_email_text(otp_code: str, purpose: str) -> str:
    """Format fallback plaintext email for 6-digit OTP verification."""
    return f"""Bursar 2.0 Verification Code

Your 6-digit OTP verification code is: {otp_code}

This code expires in 5 minutes.
If you did not request this verification code, please ignore this email.

Bursar Financial Systems (Support: {config.SUPPORT_EMAIL})"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

def send_via_smtp(recipient_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send transactional email via standard SMTP relay (e.g. Zoho ZeptoMail)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((config.APP_NAME, config.SES_SENDER_EMAIL))
    msg["To"] = recipient_email

    part1 = MIMEText(text_body, "plain", "utf-8")
    part2 = MIMEText(html_body, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        if config.SMTP_USE_SSL or config.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
            if config.SMTP_USE_TLS:
                server.starttls()

        if config.SMTP_USER and config.SMTP_PASSWORD:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)

        server.sendmail(config.SES_SENDER_EMAIL, [recipient_email], msg.as_string())
        server.quit()
        logger.info(f"Transactional email sent successfully to '{recipient_email}' via SMTP ({config.SMTP_HOST}).")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to '{recipient_email}' via SMTP ({config.SMTP_HOST}): {str(e)}")
        return False

def send_via_ses(recipient_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send transactional email via AWS SES SDK."""
    try:
        ses_client = boto3.client(
            "ses",
            region_name=config.AWS_REGION,
            aws_access_key_id=config.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY or None
        )
        
        response = ses_client.send_email(
            Source=config.SES_SENDER_EMAIL,
            Destination={
                "ToAddresses": [recipient_email]
            },
            Message={
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8"
                },
                "Body": {
                    "Html": {
                        "Data": html_body,
                        "Charset": "UTF-8"
                    },
                    "Text": {
                        "Data": text_body,
                        "Charset": "UTF-8"
                    }
                }
            }
        )
        logger.info(f"AWS SES email sent successfully to '{recipient_email}'. MessageId: {response.get('MessageId')}")
        return True
    except ClientError as e:
        logger.error(f"Failed to send AWS SES email to '{recipient_email}': {e.response['Error']['Message']}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email to '{recipient_email}' via AWS SES: {str(e)}")
        return False

def send_otp_email(recipient_email: str, otp_code: str, purpose: str = "login_2fa") -> bool:
    """
    Send transactional 6-digit OTP verification email via Zoho ZeptoMail SMTP or AWS SES.
    Falls back to mock console/logger delivery in test mode or when credentials are not set.
    """
    recipient_clean = recipient_email.strip().lower()
    html_body = format_otp_email_html(otp_code, purpose)
    text_body = format_otp_email_text(otp_code, purpose)
    if purpose == "wallet_withdrawal":
        subject = f"[Bursar] 💸 Cash Withdrawal Verification Code: {otp_code}"
    elif purpose == "password_change":
        subject = f"[Bursar] 🔑 Password Change Verification Code: {otp_code}"
    elif purpose == "payout_stepup":
        subject = f"[Bursar] 🛡️ Authorization Code: {otp_code}"
    else:
        subject = f"Your Bursar 2.0 Verification Code: {otp_code}"

    # Always populate test store for test assertions
    last_sent_otp_emails[recipient_clean] = {
        "email": recipient_clean,
        "otp_code": otp_code,
        "purpose": purpose,
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body
    }

    if config.EMAIL_MOCK_MODE or config.IS_TEST_MODE:
        logger.info(f"[MOCK EMAIL] OTP '{otp_code}' sent to '{recipient_clean}' (Purpose: {purpose})")
        print(f"\n=======================================================\n[MOCK EMAIL] [OTP KEY] 2FA OTP Code: {otp_code} (Sent to: {recipient_clean})\n=======================================================\n", flush=True)
        return True

    # Use SMTP (Zoho ZeptoMail) if SMTP_PASSWORD is provided or provider is smtp
    if config.EMAIL_PROVIDER == "smtp" or config.SMTP_PASSWORD:
        return send_via_smtp(recipient_clean, subject, html_body, text_body)
    else:
        return send_via_ses(recipient_clean, subject, html_body, text_body)
