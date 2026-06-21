import base64
import datetime
import pytest
from unittest.mock import AsyncMock
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography import x509
from cryptography.x509.oid import NameOID
from app.services.mpesa import MpesaClient

# Helper fixture to generate a valid DER certificate for testing encryption
@pytest.fixture
def test_certificate():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "KE"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Bursar Test"),
        x509.NameAttribute(NameOID.COMMON_NAME, "bursar-test.com"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        now - datetime.timedelta(days=1)
    ).not_valid_after(
        now + datetime.timedelta(days=10)
    ).sign(private_key, hashes.SHA256())
    
    cert_bytes = cert.public_bytes(serialization.Encoding.DER)
    return cert_bytes, private_key

def test_encrypt_password(test_certificate):
    cert_bytes, private_key = test_certificate
    client = MpesaClient(
        consumer_key="test_key",
        consumer_secret="test_secret",
        shortcode="600298",
        initiator_name="test_initiator",
        initiator_password="test_password",
        mode="sandbox"
    )
    
    encrypted_base64 = client.encrypt_password(cert_bytes)
    assert encrypted_base64 is not None
    
    # Decrypt and verify
    encrypted_bytes = base64.b64decode(encrypted_base64)
    decrypted_password = private_key.decrypt(
        encrypted_bytes,
        padding.PKCS1v15()
    )
    assert decrypted_password.decode("utf-8") == "test_password"

@pytest.mark.asyncio
async def test_simulation_payout():
    client = MpesaClient(
        consumer_key="",
        consumer_secret="",
        shortcode="600298",
        initiator_name="sim_initiator",
        initiator_password="sim_password",
        mode="simulation"
    )
    
    response = await client.send_b2c_payout(
        phone_number="254712345678",
        amount=500.0,
        result_url="https://example.com/result",
        timeout_url="https://example.com/timeout"
    )
    
    assert response["ResponseCode"] == "0"
    assert "sim_conv_" in response["ConversationID"]
    assert "sim_orig_" in response["OriginatorConversationID"]

@pytest.mark.asyncio
async def test_sandbox_auth_flow(mocker):
    # If respx isn't installed, we can mock httpx.AsyncClient using pytest-mock
    client = MpesaClient(
        consumer_key="test_key",
        consumer_secret="test_secret",
        shortcode="600298",
        initiator_name="test_initiator",
        initiator_password="test_password",
        mode="sandbox"
    )
    
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json = mocker.Mock(return_value={
        "access_token": "mocked_access_token_123",
        "expires_in": "3599"
    })
    
    # Mock httpx.AsyncClient.get
    mock_get = mocker.patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    mock_get.return_value = mock_response
    
    token = await client.get_access_token()
    assert token == "mocked_access_token_123"
    
    # Verify mock call arguments
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert "oauth/v1/generate" in args[0]
    assert "Authorization" in kwargs["headers"]
    
    # Verify basic auth format
    auth_header = kwargs["headers"]["Authorization"]
    assert auth_header.startswith("Basic ")

@pytest.mark.asyncio
async def test_sandbox_payout_api(mocker, test_certificate):
    cert_bytes, _ = test_certificate
    client = MpesaClient(
        consumer_key="test_key",
        consumer_secret="test_secret",
        shortcode="600298",
        initiator_name="test_initiator",
        initiator_password="test_password",
        mode="sandbox"
    )
    
    # Mock token generation & encryption
    mocker.patch.object(client, "get_access_token", return_value="token123")
    mocker.patch.object(client, "encrypt_password", return_value="encrypted_password_base64")
    
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json = mocker.Mock(return_value={
        "ConversationID": "conv_987",
        "OriginatorConversationID": "orig_987",
        "ResponseCode": "0",
        "ResponseDescription": "Accept the service request successfully."
    })
    
    mock_post = mocker.patch("httpx.AsyncClient.post", new_callable=AsyncMock)
    mock_post.return_value = mock_response
    
    res = await client.send_b2c_payout(
        phone_number="254712345678",
        amount=150.0,
        result_url="https://example.com/result",
        timeout_url="https://example.com/timeout",
        cert_bytes=cert_bytes
    )
    
    assert res["ResponseCode"] == "0"
    assert res["ConversationID"] == "conv_987"
    
    mock_post.assert_called_once()
    post_args, post_kwargs = mock_post.call_args
    assert "mpesa/b2c/v1/paymentrequest" in post_args[0]
    payload = post_kwargs["json"]
    assert payload["InitiatorName"] == "test_initiator"
    assert payload["SecurityCredential"] == "encrypted_password_base64"
    assert payload["CommandID"] == "BusinessPayment"
    assert payload["Amount"] == 150.0
    assert payload["PartyA"] == "600298"
    assert payload["PartyB"] == "254712345678"
    assert payload["QueueTimeOutURL"] == "https://example.com/timeout"
    assert payload["ResultURL"] == "https://example.com/result"
