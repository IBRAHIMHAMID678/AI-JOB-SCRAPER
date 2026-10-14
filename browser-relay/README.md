# browser-relay

Local forward proxy that lets headless Chromium reach the internet from this VM.

## What it is

`relay.py` listens on **127.0.0.1:18924** and acts as an HTTP CONNECT proxy for
Chromium: the browser sends `CONNECT host:443`, the relay answers `200
Connection Established` locally, then tunnels the raw bytes upstream through
a Python-held connection to the egress proxy (`$https_proxy`).

## Why it exists

The VM's egress is HTTPS-only through a filtered proxy. Chromium's own
`CONNECT` requests are rejected by that proxy (`ERR_TUNNEL_CONNECTION_FAILED`),
so headless Chromium cannot load any page directly. Plain Python sockets
tunnel through the same proxy without problems — so the relay terminates the
browser's CONNECT locally and forwards the byte stream via Python. Chromium
is launched with:

```
--proxy-server=http://127.0.0.1:18924 --ignore-certificate-errors --no-sandbox
```

Verified working with `example.com` and `dailyremote.com/remote-ai-engineer-jobs`.

## Lifecycle

`~/workspace/job_hunt/auto-scraper/verify_live.py` manages the relay:

- `ensure_relay()` probes `127.0.0.1:18924` with a TCP connect; if nothing is
  listening it spawns `python3 relay.py` as a child process (single handle,
  `start_new_session=True`) and waits up to ~5s for the port.
- Calling it repeatedly is safe — it never spawns duplicates.
- The relay is bound to **127.0.0.1 only**; it is not reachable from the
  network. Kill the spawned process (or the parent) to stop it.

## Files

- `relay.py` — the proxy itself (asyncio, stdlib only).
- `relay.log` — leftover log from an earlier manual run; safe to delete.

## Consumer

`verify_live.py` in `~/workspace/job_hunt/auto-scraper/` — renders apply
URLs in headless Chromium through this relay and classifies them as
`live_apply | dead | signin_wall | bot_wall | uncertain`. Wired into
`run.py` via the `--verify N` flag (off by default).
