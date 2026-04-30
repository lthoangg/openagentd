"""GitHub Copilot device-flow OAuth login and credential storage.

Credentials live in ``{CACHE_DIR}/copilot_oauth.json``.

Called by ``app.cli.commands.auth`` central dispatcher::

    openagentd auth copilot
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, SecretStr

# -- Persistence --------------------------------------------------------------


def _default_oauth_file() -> Path:
    """Resolve the OAuth credentials path from settings.

    Lazy so the file location tracks ``OPENAGENTD_CACHE_DIR`` even when settings
    are swapped (tests, env overrides).
    """
    from app.core.config import settings

    return Path(settings.OPENAGENTD_CACHE_DIR) / "copilot_oauth.json"


class CopilotOAuth(BaseModel):
    """Persisted GitHub OAuth credentials for the Copilot provider."""

    github_token: SecretStr  # long-lived (gho_*/ghu_*/ghp_*/github_pat_*)

    @classmethod
    def load(cls, path: Path | None = None) -> CopilotOAuth | None:
        """Load from disk. Returns None if file missing or invalid."""
        p = path or _default_oauth_file()
        if not p.exists():
            return None
        try:
            return cls.model_validate_json(p.read_text())
        except Exception:
            return None

    def save(self, path: Path | None = None) -> None:
        """Write to disk, exposing secret for persistence."""
        p = path or _default_oauth_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        # Me must reveal secret for JSON file — model_dump_json hides it
        data = {"github_token": self.github_token.get_secret_value()}
        import json

        p.write_text(json.dumps(data, indent=2) + "\n")


# -- Device-flow constants ----------------------------------------------------

_CLIENT_ID = "Ov23li8tweQw6odWQebz"
_SCOPE = "read:user"
_DEVICE_CODE_URL = "https://github.com/login/device/code"
_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
_COPILOT_MODELS_URL = "https://api.githubcopilot.com/models"

_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "openagentd/1.0.0",
}


# -- Device-flow steps --------------------------------------------------------


def _request_device_code() -> dict:
    r = httpx.post(
        _DEVICE_CODE_URL,
        headers=_HEADERS,
        json={"client_id": _CLIENT_ID, "scope": _SCOPE},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def _poll_for_token(device_code: str, interval: int, expires_in: int) -> str:
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        r = httpx.post(
            _ACCESS_TOKEN_URL,
            headers=_HEADERS,
            json={
                "client_id": _CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()

        if "access_token" in data:
            return data["access_token"]

        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            interval += 5
            continue
        elif error == "expired_token":
            print("Device code expired. Run again.")
            sys.exit(1)
        elif error == "access_denied":
            print("User denied access.")
            sys.exit(1)
        else:
            print(f"Unexpected error: {error}")
            sys.exit(1)

    print("Timed out waiting for authorization.")
    sys.exit(1)


def _verify_copilot_access(token: str) -> bool:
    """Verify token by hitting GET /models."""
    try:
        r = httpx.get(
            _COPILOT_MODELS_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": _HEADERS["User-Agent"],
                "Accept": "application/json",
            },
            timeout=10.0,
        )
        if r.status_code == 200:
            data = r.json()
            models = data.get("data", [])
            enabled = [m for m in models if m.get("model_picker_enabled")]
            print(f"  Copilot OK — {len(enabled)} models available\n")
            for m in enabled:
                endpoints = m.get("supported_endpoints", [])
                ep_str = ", ".join(endpoints) if endpoints else "?"
                print(f"    {m['id']:30s}  [{ep_str}]")
            return True
        else:
            print(f"  Copilot verification failed: {r.status_code}")
            print(f"  Response: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"  Copilot verification error: {e}")
        return False


# -- Public login function ----------------------------------------------------


def login(oauth_path: Path | None = None) -> None:
    """Run the full GitHub Copilot device-flow login."""
    oauth_path = oauth_path or _default_oauth_file()

    print("=== GitHub Copilot Device Login ===\n")

    # Me check if already logged in
    existing = CopilotOAuth.load(oauth_path)
    if existing:
        print(f"Existing token found in {oauth_path}")
        print("Verifying...")
        if _verify_copilot_access(existing.github_token.get_secret_value()):
            print("\nExisting token still valid. No action needed.")
            print("To force re-login, delete the file and run again.")
            return
        print("\nExisting token invalid. Re-authenticating...\n")

    # Step 1: get device code
    print("Requesting device code...")
    data = _request_device_code()
    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data["verification_uri"]
    interval = data.get("interval", 5)
    expires_in = data.get("expires_in", 900)

    print(f"\n  Open:  {verification_uri}")
    print(f"  Code:  {user_code}\n")
    print("Waiting for authorization...\n")

    # Step 2: poll for token
    token = _poll_for_token(device_code, interval, expires_in)
    print(f"GitHub token acquired: {token[:8]}...{token[-4:]}\n")

    # Step 3: verify Copilot access
    print("Verifying Copilot access...")
    ok = _verify_copilot_access(token)
    if not ok:
        print("\nWARNING: Token obtained but Copilot access failed.")
        print("Make sure you have an active GitHub Copilot subscription.\n")
        print("Saving token anyway — you can retry later.\n")

    # Step 4: save
    oauth = CopilotOAuth(github_token=SecretStr(token))
    oauth.save(oauth_path)
    print(f"\nSaved to {oauth_path}")
    print("Use model: copilot:gpt-5.4-mini")
