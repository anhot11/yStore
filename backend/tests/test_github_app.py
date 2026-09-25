from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from unittest.mock import MagicMock, patch
import pytest
import jwt

from app.github_app import (
    create_publisher_repo,
    exchange_oauth_code,
    generate_app_jwt,
    get_installation_access_token,
    register_repo_webhook,
)


@pytest.fixture
def rsa_private_key_pem():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")


def test_generate_app_jwt(rsa_private_key_pem):
    app_id = "123456"
    token = generate_app_jwt(app_id=app_id, private_key_pem=rsa_private_key_pem)
    assert token is not None

    # Decode without verification to inspect claims
    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["iss"] == app_id
    assert "exp" in decoded
    assert "iat" in decoded
    assert decoded["exp"] > decoded["iat"]


def test_get_installation_access_token(rsa_private_key_pem):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"token": "ghs_mockinstallationtoken123"}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        token = get_installation_access_token(
            installation_id="998877",
            app_id="123456",
            private_key_pem=rsa_private_key_pem,
        )
        assert token == "ghs_mockinstallationtoken123"
        mock_post.assert_called_once()
        assert "installations/998877/access_tokens" in mock_post.call_args[0][0]


def test_exchange_oauth_code():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "ghu_mockusertoken",
        "token_type": "bearer",
        "scope": "repo,write:repo_hook",
    }

    with patch("requests.post", return_value=mock_resp):
        res = exchange_oauth_code("code_xyz")
        assert res["access_token"] == "ghu_mockusertoken"


def test_register_repo_webhook():
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": 112233, "active": True}

    with patch("requests.post", return_value=mock_resp) as mock_post:
        res = register_repo_webhook("mock_token", "dev_user", "cool_game")
        assert res["id"] == 112233
        payload = mock_post.call_args[1]["json"]
        assert payload["events"] == ["release"]
        assert "webhooks/github" in payload["config"]["url"]


def test_create_publisher_repo():
    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {"login": "gamedev123"}

    mock_create_resp = MagicMock()
    mock_create_resp.status_code = 201
    mock_create_resp.json.return_value = {
        "name": "super-game",
        "html_url": "https://github.com/gamedev123/super-game",
    }

    mock_hook_resp = MagicMock()
    mock_hook_resp.status_code = 201
    mock_hook_resp.json.return_value = {"id": 5555}

    mock_put_resp = MagicMock()
    mock_put_resp.status_code = 201
    mock_put_resp.json.return_value = {}

    with patch("app.github_app.get_github_user", return_value={"login": "gamedev123"}):
        with patch("requests.post", side_effect=[mock_create_resp, mock_hook_resp]):
            with patch("requests.put", return_value=mock_put_resp):
                res = create_publisher_repo(
                    token="ghu_test",
                    repo_name="super-game",
                    title="Super Game",
                )
                assert res["owner"] == "gamedev123"
                assert res["repo_name"] == "super-game"
                assert "metadata/android/en-US/title.txt" in res["metadata_structure"]
                assert "metadata/android/en-US/images/icon.png" in res["metadata_structure"]
                assert res["webhook_id"] == 5555
