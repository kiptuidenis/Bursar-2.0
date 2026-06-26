import pytest
import sqlite3
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)

def test_unhandled_database_error_returns_json():
    # Patch authenticate_user to raise an OperationalError simulating a read-only DB write crash
    with patch("app.db.manager.DatabaseManager.authenticate_user") as mock_auth:
        mock_auth.side_effect = sqlite3.OperationalError("attempt to write a readonly database")
        
        login_payload = {
            "phone_number": "254712345678",
            "password": "mypassword123"
        }
        
        response = client.post("/api/auth/login", json=login_payload)
        
        # Verify it returns a 500 status code
        assert response.status_code == 500
        
        # Verify content type is application/json
        assert "application/json" in response.headers.get("content-type", "")
        
        # Verify the structure of the JSON response
        data = response.json()
        assert "detail" in data
        assert "Internal Server Error: attempt to write a readonly database" in data["detail"]

def test_generic_unhandled_exception_returns_json():
    # Patch authenticate_user to raise a generic Exception
    with patch("app.db.manager.DatabaseManager.authenticate_user") as mock_auth:
        mock_auth.side_effect = Exception("Something went terribly wrong")
        
        login_payload = {
            "phone_number": "254712345678",
            "password": "mypassword123"
        }
        
        response = client.post("/api/auth/login", json=login_payload)
        
        # Verify status and format
        assert response.status_code == 500
        assert "application/json" in response.headers.get("content-type", "")
        data = response.json()
        assert "detail" in data
        assert "Internal Server Error: Something went terribly wrong" in data["detail"]
