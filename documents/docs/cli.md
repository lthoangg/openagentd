# CLI reference

The `openagentd` binary is the single entry point for running, managing, and inspecting the server.

## Start

```bash
openagentd                            # start in the background (production)
openagentd --dev                      # start in the foreground with hot-reload
```

**Flags**

| Flag | Default | Description |
|---|---|---|
| `--dev` | off | Foreground mode with uvicorn hot-reload and Vite HMR |
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `4082` prod / `8000` dev | API port |
| `--web-port` | `5173` | Vite dev server port (dev mode only) |

**Production mode** runs as a detached background process. The pre-built web UI is served by FastAPI on a single port (4082). Logs go to `~/.local/state/openagentd/logs/app/app.log`. The server auto-migrates the database on startup.

**Dev mode** runs uvicorn in the foreground on port 8000 (with `--reload`) and starts a Vite HMR server on port 5173. The API is at `http://localhost:8000` and the web UI is at `http://localhost:5173`.

If openagentd hasn't been initialised yet, `openagentd` (without `--dev`) automatically runs `openagentd init` before starting the server.

---

## init

```bash
openagentd init           # production setup (~/.config/openagentd/)
openagentd init --dev     # development setup (.openagentd/ in project root)
```

Interactive first-time setup wizard. Prompts for provider, model, and API key, then installs the default agent team and skills. Re-running `init` is safe — existing files are never overwritten.

See [Install — First run](install.md#first-run) for a full walkthrough.

---

## auth

```bash
openagentd auth copilot         # GitHub Copilot — device-flow OAuth
openagentd auth codex           # OpenAI Codex — PKCE OAuth (browser)
openagentd auth codex --device  # OpenAI Codex — headless device-code flow
openagentd auth --list          # list available OAuth providers
```

Authenticates with an OAuth-based provider. Only needed for providers that don't use an API key (GitHub Copilot, OpenAI Codex). Token is cached locally and reused on subsequent runs.

---

## stop

```bash
openagentd stop
```

Sends `SIGTERM` to the background server process. Waits up to 5 seconds for a clean shutdown, then sends `SIGKILL` if needed. Clears the PID file.

---

## status

```bash
openagentd status
```

Reports whether a background server is running, the PIDs, and the log file path.

---

## logs

```bash
openagentd logs           # tail last 50 lines and follow
openagentd logs -n 100    # tail last 100 lines and follow
```

Tails the server log file (equivalent to `tail -n <lines> -f`). Checks the production log location first, then falls back to the dev location.

---

## doctor

```bash
openagentd doctor
```

Runs a series of health checks and exits with code 1 if any fail:

| Check | Pass | Fail |
|---|---|---|
| Python version | ≥ 3.14 | < 3.14 |
| API key configured | Any provider key set | No key found |
| Provider/key match | Lead agent's provider has a matching key | Provider set but key missing |
| Database | `openagentd.db` exists | Not found (warning only — created on first run) |
| Alembic config | Bundled in package | Missing (reinstall) |
| Port 4082 | Available | In use |
| Web UI | Bundled `_web_dist/` present | Missing (warning only) |
| Agents directory | At least one `.md` in config dir | Missing (run `openagentd init`) |

Warnings (degraded but bootable) don't affect the exit code. Run this first when something looks wrong.

---

## update

```bash
openagentd update
```

Upgrades openagentd to the latest published version. Uses `uv tool upgrade` if uv is available, otherwise falls back to `pip install --upgrade`.

---

## version

```bash
openagentd version
openagentd --version
```

Prints the installed version and exits.

---

## Related

- [Install](install.md)
- [Configuration](configuration.md)
- [Troubleshooting](troubleshooting.md)
