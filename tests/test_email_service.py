import pytest
from botocore.exceptions import ClientError
from app.services.email import (
    send_otp_email,
    format_otp_email_html,
    format_otp_email_text,
    last_sent_otp_emails
)
from app.core import config

def test_send_otp_email_mock_mode():
    """Verify email dispatch in test/mock mode populates test store and returns True."""
    email = "user@bursar.co.ke"
    otp_code = "123456"
    purpose = "login_2fa"
    
    success = send_otp_email(email, otp_code, purpose=purpose)
    assert success is True
    
    assert email in last_sent_otp_emails
    sent_data = last_sent_otp_emails[email]
    assert sent_data["otp_code"] == "123456"
    assert sent_data["email"] == email
    assert "123456" in sent_data["html_body"]
    assert "5 minutes" in sent_data["html_body"]

def test_email_template_formatting():
    """Verify HTML and plaintext template formatting contains required Bursar branding and purpose headers."""
    html_signup = format_otp_email_html("998877", "signup_2fa")
    assert "Welcome to Bursar 2.0 - Verify Your Email" in html_signup
    assert "998877" in html_signup
    assert "support@bursar.co.ke" in html_signup

    html_payout = format_otp_email_html("554433", "payout_stepup")
    assert "Payout Step-Up Authorization Code" in html_payout
    assert "554433" in html_payout

    text_body = format_otp_email_text("112233", "login_2fa")
    assert "112233" in text_body
    assert "expires in 5 minutes" in text_body

def test_send_otp_email_aws_ses_success(mocker):
    """Verify AWS SES email API dispatch when EMAIL_MOCK_MODE is disabled."""
    mocker.patch.object(config, "EMAIL_MOCK_MODE", False)
    mocker.patch.object(config, "IS_TEST_MODE", False)
    mocker.patch.object(config, "AWS_ACCESS_KEY_ID", "mock_key")
    mocker.patch.object(config, "AWS_SECRET_ACCESS_KEY", "mock_secret")

    mock_ses_client = mocker.MagicMock()
    mock_ses_client.send_email.return_value = {"MessageId": "msg-12345-abcde"}
    mocker.patch("boto3.client", return_value=mock_ses_client)

    email = "awsuser@bursar.co.ke"
    otp_code = "654321"
    
    success = send_otp_email(email, otp_code, purpose="login_2fa")
    assert success is True

    # Verify boto3.client called with ses
    mock_ses_client.send_email.assert_called_once()
    call_kwargs = mock_ses_client.send_email.call_args[1]
    assert call_kwargs["Source"] == "noreply@bursar.co.ke"
    assert call_kwargs["Destination"]["ToAddresses"] == [email]
    assert "654321" in call_kwargs["Message"]["Subject"]["Data"]

def test_send_otp_email_aws_ses_client_error(mocker):
    """Verify ClientError from AWS SES returns False gracefully and logs error."""
    mocker.patch.object(config, "EMAIL_MOCK_MODE", False)
    mocker.patch.object(config, "IS_TEST_MODE", False)

    mock_ses_client = mocker.MagicMock()
    mock_ses_client.send_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email address not verified in SES sandbox"}},
        "SendEmail"
    )
    mocker.patch("boto3.client", return_value=mock_ses_client)

    email = "unverified@bursar.co.ke"
    success = send_otp_email(email, "111222")
    assert success is False
