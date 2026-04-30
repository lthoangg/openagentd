"""OpenAI Codex OAuth login — PKCE browser flow and device-code headless flow.

Credentials live in ``{CACHE_DIR}/codex_oauth.json``.

Called by ``app.cli.commands.auth`` central dispatcher::

    openagentd auth codex           # opens browser (PKCE)
    openagentd auth codex --device  # headless device-code flow

Ported from opencode's codex.ts plugin (anomalyco/opencode).
"""

from __future__ import annotations

import json
import secrets
import sys
import time
import urllib.parse
import webbrowser
from base64 import urlsafe_b64encode
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any

import httpx
from pydantic import BaseModel, SecretStr

# -- Constants ----------------------------------------------------------------

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
ISSUER = "https://auth.openai.com"
OAUTH_PORT = 1455
_USER_AGENT = "openagentd/1.0.0"

# -- Persistence --------------------------------------------------------------


def _default_oauth_file() -> Path:
    from app.core.config import settings

    return Path(settings.OPENAGENTD_CACHE_DIR) / "codex_oauth.json"


class CodexOAuth(BaseModel):
    """Persisted OpenAI Codex OAuth credentials."""

    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: float  # unix timestamp
    account_id: str | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> CodexOAuth | None:
        p = path or _default_oauth_file()
        if not p.exists():
            return None
        try:
            return cls.model_validate_json(p.read_text())
        except Exception:
            return None

    def save(self, path: Path | None = None) -> None:
        p = path or _default_oauth_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "access_token": self.access_token.get_secret_value(),
            "refresh_token": self.refresh_token.get_secret_value(),
            "expires_at": self.expires_at,
            "account_id": self.account_id,
        }
        p.write_text(json.dumps(data, indent=2) + "\n")

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 60  # 60s buffer

    def refresh(self, path: Path | None = None) -> CodexOAuth:
        """Exchange refresh_token for a new access_token and persist it."""
        tokens = _refresh_access_token(self.refresh_token.get_secret_value())
        new = CodexOAuth(
            access_token=SecretStr(tokens["access_token"]),
            refresh_token=SecretStr(
                tokens.get("refresh_token") or self.refresh_token.get_secret_value()
            ),
            expires_at=time.time() + tokens.get("expires_in", 3600),
            account_id=_extract_account_id(tokens) or self.account_id,
        )
        new.save(path)
        return new


# -- PKCE helpers -------------------------------------------------------------


def _generate_verifier() -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(chars[b % len(chars)] for b in secrets.token_bytes(43))


def _challenge(verifier: str) -> str:
    digest = sha256(verifier.encode()).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode()


def _state() -> str:
    return urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def _authorize_url(redirect_uri: str, verifier: str, state: str) -> str:
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email offline_access",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "state": state,
            "originator": "openagentd",
        }
    )
    return f"{ISSUER}/oauth/authorize?{params}"


# -- Token exchange -----------------------------------------------------------


def _exchange_code(code: str, redirect_uri: str, verifier: str) -> dict[str, Any]:
    r = httpx.post(
        f"{ISSUER}/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        content=urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": CLIENT_ID,
                "code_verifier": verifier,
            }
        ).encode(),
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def _refresh_access_token(refresh_token: str) -> dict[str, Any]:
    r = httpx.post(
        f"{ISSUER}/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        content=urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            }
        ).encode(),
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def _extract_account_id(tokens: dict[str, Any]) -> str | None:
    import base64

    for key in ("id_token", "access_token"):
        token = tokens.get(key)
        if not token:
            continue
        parts = token.split(".")
        if len(parts) != 3:
            continue
        try:
            padding = 4 - len(parts[1]) % 4
            payload = json.loads(
                base64.urlsafe_b64decode(parts[1] + "=" * padding).decode()
            )
            account_id = (
                payload.get("chatgpt_account_id")
                or (payload.get("https://api.openai.com/auth") or {}).get(
                    "chatgpt_account_id"
                )
                or (payload.get("organizations") or [{}])[0].get("id")
            )
            if account_id:
                return account_id
        except Exception:
            continue
    return None


# -- PKCE browser flow --------------------------------------------------------


def _pkce_login(oauth_path: Path | None = None) -> None:
    """Full PKCE browser-based login flow."""
    oauth_path = oauth_path or _default_oauth_file()
    redirect_uri = f"http://localhost:{OAUTH_PORT}/auth/callback"
    verifier = _generate_verifier()
    state = _state()
    auth_url = _authorize_url(redirect_uri, verifier, state)

    result: dict[str, Any] = {}
    done = Event()

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # suppress server logs
            pass

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)

            if parsed.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
                return

            if qs.get("error"):
                result["error"] = qs["error"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Authorization failed</h1><p>You can close this window.</p>"
                )
                done.set()
                return

            code = (qs.get("code") or [None])[0]
            got_state = (qs.get("state") or [None])[0]
            if not code or got_state != state:
                result["error"] = "invalid_state_or_missing_code"
                self.send_response(400)
                self.end_headers()
                done.set()
                return

            result["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h1>Authorization successful</h1><p>You can close this window and return to the terminal.</p>"
                b"<script>setTimeout(()=>window.close(),2000)</script>"
            )
            done.set()

    server = HTTPServer(("localhost", OAUTH_PORT), _Handler)
    Thread(target=server.serve_forever, daemon=True).start()

    print("\n  Opening browser for authorization...")
    print(f"  If it does not open, visit:\n    {auth_url}\n")
    webbrowser.open(auth_url)

    if not done.wait(timeout=300):
        server.shutdown()
        print("Timed out waiting for browser authorization.")
        sys.exit(1)

    server.shutdown()

    if result.get("error"):
        print(f"Authorization failed: {result['error']}")
        sys.exit(1)

    tokens = _exchange_code(result["code"], redirect_uri, verifier)
    _save_tokens(tokens, oauth_path)


# -- Device-code headless flow ------------------------------------------------


def _device_login(oauth_path: Path | None = None) -> None:
    """Headless device-code flow (no browser required on this machine)."""
    oauth_path = oauth_path or _default_oauth_file()

    r = httpx.post(
        f"{ISSUER}/api/accounts/deviceauth/usercode",
        headers={
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        },
        json={"client_id": CLIENT_ID},
        timeout=30.0,
    )
    r.raise_for_status()
    device_data = r.json()

    device_auth_id: str = device_data["device_auth_id"]
    user_code: str = device_data["user_code"]
    interval: int = max(int(device_data.get("interval", 5)), 1)

    print(f"\n  Open:  {ISSUER}/codex/device")
    print(f"  Code:  {user_code}\n")
    print("Polling for authorization...\n")

    while True:
        time.sleep(interval + 3)  # +3s safety margin
        poll = httpx.post(
            f"{ISSUER}/api/accounts/deviceauth/token",
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
            json={"device_auth_id": device_auth_id, "user_code": user_code},
            timeout=30.0,
        )

        if poll.status_code == 200:
            data = poll.json()
            # Exchange the authorization_code returned by device poll
            token_r = httpx.post(
                f"{ISSUER}/oauth/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                content=urllib.parse.urlencode(
                    {
                        "grant_type": "authorization_code",
                        "code": data["authorization_code"],
                        "redirect_uri": f"{ISSUER}/deviceauth/callback",
                        "client_id": CLIENT_ID,
                        "code_verifier": data["code_verifier"],
                    }
                ).encode(),
                timeout=30.0,
            )
            token_r.raise_for_status()
            _save_tokens(token_r.json(), oauth_path)
            return

        if poll.status_code not in (403, 404):
            print(f"Unexpected poll response: {poll.status_code}")
            sys.exit(1)
        # 403/404 → still pending, keep polling


def _save_tokens(tokens: dict[str, Any], oauth_path: Path) -> None:
    account_id = _extract_account_id(tokens)
    oauth = CodexOAuth(
        access_token=SecretStr(tokens["access_token"]),
        refresh_token=SecretStr(tokens["refresh_token"]),
        expires_at=time.time() + tokens.get("expires_in", 3600),
        account_id=account_id,
    )
    oauth.save(oauth_path)
    print(f"Saved to {oauth_path}")
    if account_id:
        print(f"Account: {account_id}")
    print("Use model: codex:gpt-5.4")


# -- Public login function ----------------------------------------------------


def login(oauth_path: Path | None = None, *, device: bool = False) -> None:
    """Run the OpenAI Codex OAuth login."""
    oauth_path = oauth_path or _default_oauth_file()

    print("=== OpenAI Codex OAuth Login ===\n")

    existing = CodexOAuth.load(oauth_path)
    if existing and not existing.is_expired():
        print(f"Valid token found in {oauth_path}")
        print("To force re-login, delete the file and run again.")
        return
    if existing and existing.is_expired():
        print("Token expired. Refreshing...")
        try:
            existing.refresh(oauth_path)
            print("Token refreshed successfully.")
            return
        except Exception as e:
            print(f"Refresh failed ({e}), re-authenticating...\n")

    if device:
        _device_login(oauth_path)
    else:
        _pkce_login(oauth_path)
