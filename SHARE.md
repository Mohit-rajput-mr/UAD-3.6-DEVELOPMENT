# Sharing the review session

The server is built to be tunnelled: it binds `0.0.0.0`, keeps every edit in
SQLite, pushes changes live to all open viewers, and asks for a passcode first.

## 1. Start the server

```
URAR_ACCESS_CODE="choose-your-own-passcode" python run_server.py
```

It prints the passcode on startup. Omit `URAR_ACCESS_CODE` and it generates a
three-word one for you.

## 2. Open the tunnel

```
cloudflared tunnel --url http://localhost:8000
```

Cloudflare prints a `https://<random>.trycloudflare.com` URL. That is the link
to send colleagues, along with the passcode.

If `cloudflared` is not installed:

```
winget install --id Cloudflare.cloudflared
```

## What colleagues get

- The full URAR, every field editable in place.
- Their name, asked once, shown to everyone else editing.
- Live updates: a value someone else changes updates on your screen and
  flashes amber, without reloading.
- One shared record. Two people on different machines always see the same
  values, because the values live in the server's database, not the browser.
- **Download ZIP** builds the deliverable from the current shared state and
  re-runs schema, compliance and file-structure checks first.

## Notes

- Edits survive restarts. `POST /api/reset` discards them all and returns the
  report to what the engine generated.
- A free Cloudflare quick tunnel gets a new URL each run. For a stable address,
  use a named tunnel on your own domain.
- `URAR_OPEN=1` disables the passcode. Only for a trusted local network, never
  for a public tunnel.
