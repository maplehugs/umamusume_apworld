"""JP region -- everything that exists only because the JP client is not Global's.

Run as its OWN process (`./start-server.sh --region jp`, ASGI app
`app.jp.server:app`), never inside Global's `app.main`. The shared game-logic
modules cache master.mdb rows and Global data files at import time, so one
process serving both regions would silently hand JP a Global answer the first
time any cache was warm -- a separate process makes that impossible rather
than something to remember.

Direction of imports: this package may import shared code (state, accounts,
region, ...). Shared code must never import this package.

Layout:
    coneshell.py   the JP wire primitives (X25519 ECDH, SPN whitening, GCM)
    transport.py   open_request / seal_reply -- the JP twin of app/crypto.py
    keys.py        this server's X25519 keypair (generated on first run)
    arming.py      loopback side channel the Hachimi plugin arms itself from
    fixtures.py    captured JP replies, served where no handler exists
    handlers.py    the stateful endpoints on the login -> home path
    server.py      the FastAPI app: decode, dispatch, finish, seal

Provenance: ported from the JP handoff packet (jp_docs/JP_HANDOFF_2026-09-23),
whose transport is verified byte-exact against real Cygames traffic. Where a
comment says `WIRE`, the claim was observed on real traffic; the handoff's
own docs carry the evidence.
"""
