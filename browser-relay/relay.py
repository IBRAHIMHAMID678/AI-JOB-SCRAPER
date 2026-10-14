"""Local forward proxy for Chromium: browser -> 127.0.0.1:18924 -> (Python) -> egress proxy -> target.
Chromium's own CONNECT requests were rejected by the egress proxy; Python's sockets work fine,
so this relay terminates the browser's CONNECT locally and tunnels bytes through a Python-held upstream."""
import asyncio, os, socket
from urllib.parse import urlparse

u = urlparse(os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY"))
UPSTREAM = (u.hostname, u.port)

async def pipe(r, w):
    try:
        while True:
            data = await r.read(65536)
            if not data: break
            w.write(data); await w.drain()
    except Exception: pass
    finally:
        try: w.close()
        except Exception: pass

async def handle(reader, writer):
    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except Exception:
        writer.close(); return
    line = head.split(b"\r\n", 1)[0].decode(errors="replace")
    parts = line.split()
    if len(parts) < 2 or parts[0].upper() != "CONNECT":
        writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n"); await writer.drain(); writer.close(); return
    target = parts[1]
    host, _, port = target.partition(":")
    try:
        up_r, up_w = await asyncio.open_connection(*UPSTREAM)
        up_w.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        await up_w.drain()
        resp = await up_r.readuntil(b"\r\n\r\n")
        if b"200" not in resp.split(b"\r\n")[0]:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n"); await writer.drain()
            writer.close(); up_w.close(); return
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n"); await writer.drain()
        await asyncio.gather(pipe(reader, up_w), pipe(up_r, writer))
    except Exception:
        try: writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n"); await writer.drain()
        except Exception: pass
        writer.close()

async def main():
    srv = await asyncio.start_server(handle, "127.0.0.1", 18924)
    print("relay up on 127.0.0.1:18924", flush=True)
    async with srv: await srv.serve_forever()

asyncio.run(main())
