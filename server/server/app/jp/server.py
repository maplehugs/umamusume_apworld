"""The JP server process: `uvicorn app.jp.server:app` with UMA_REGION=jp.

Launch through `./start-server.sh --region jp`, which sets the region, the JP
certificate and the loopback address.

    JP wire (transport.py)  ->  shared pipeline (app/dispatch.py, Global's handlers)
                            ->  JP header rules (finish)  ->  JP seal

The handlers are Global's; the data under them is JP's own (region.data_dir():
server/data/jp, seeded by tools/build_jp_seeds.py; JP's master.mdb). No
captured reply is ever served: app/fixtures.py indexes none for JP, so an
endpoint without a handler gets a bare success envelope and a warning naming it.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response

from .. import region
from ..admin_lifecycle import lifespan, panel_redirect

if region.PROCESS_REGION != "jp":
    raise RuntimeError("app.jp.server needs UMA_REGION=jp (use ./start-server.sh --region jp)")

# Same policy as Global's main.py: console at UMA_LOG_LEVEL, file always DEBUG.
_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "server_jp.log", maxBytes=20_000_000, backupCount=3, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s"))
logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler(), _file_handler])
logging.getLogger().handlers[0].setLevel(os.environ.get("UMA_LOG_LEVEL", "INFO").upper())
log = logging.getLogger("uma-server")

from .. import dispatch as pipeline  # noqa: E402  (after logging, like main.py)
from .. import scenarios  # noqa: E402
from ..result_codes import refuse  # noqa: E402
from . import arming, endpoints, features, keys, schema, story_ids, transport  # noqa: E402

pipeline.HANDLERS.update(endpoints.HANDLERS)
pipeline.HANDLERS.update(features.HANDLERS)
pipeline.REQUEST_GUARDS.append(features.trainer_skill.before)

# Career endpoint families this server has a scenario for, from the registry.
_SERVED_FAMILIES = {"single_mode"} | {s.endpoint_prefix for s in scenarios.all_scenarios()}


def _refuse_unserved_scenario(payload: dict) -> dict:
    return refuse()


def _guard_scenario_family(endpoint: str) -> None:
    """A career family with no scenario here (JP's Onsen, Ramen, ... -- scenarios
    5-14) must REFUSE, never succeed empty: a fake success makes the client
    believe a career exists and layers that scenario's UI over the next one
    (Global's _UNSUPPORTED_STARTS comment records the live softlock)."""
    family = endpoint.split("/", 1)[0]
    if (family.startswith("single_mode_") and family not in _SERVED_FAMILIES
            and endpoint not in pipeline.HANDLERS):
        log.warning("JP %s: scenario family %s is not served -- refusing", endpoint, family)
        pipeline.HANDLERS[endpoint] = _refuse_unserved_scenario


def flatten_request_common(payload: dict) -> dict:
    """JP's client nests a career request's fields one level down, in a map
    named for the call (`WIRE` 2.31.0: single_mode_start_request_common.
    start_chara, single_mode_check_event_request_common.event_id, ...,
    select_succession_request_common); Global's client, which the shared
    handlers were written for, sends the same fields at the top level. Lift
    them, never over a top-level field of the same name."""
    for key, inner in list(payload.items()):
        if key.endswith("_request_common") and isinstance(inner, dict):
            for k, v in inner.items():
                payload.setdefault(k, v)
    return payload


app = FastAPI(title="Umamusume private server (JP)", lifespan=lifespan)
app.get("/", include_in_schema=False)(panel_redirect)
from .. import custom_support, custom_support_http
app.include_router(custom_support_http.router)
arming.start()


def finish(resp: dict, endpoint: str, payload: dict | None = None) -> dict:
    """JP's per-reply rules the shared pipeline does not know about: JP's
    support-card rule applied to whatever the handler granted
    (features/support_cards.py), the reply completed to the real JP shape
    (schema.py), events under their full story id (story_ids.py), and
    server_list only where the real server sends it."""
    handled = endpoint in pipeline.HANDLERS or pipeline.registry.get(endpoint) is not None
    resp = features.support_cards.apply(endpoint, payload, resp)
    if (resp.get("data_headers") or {}).get("result_code", 1) == 1:
        features.succession.mark_unrecorded(resp.get("data"))
        features.profile_slots.fill(endpoint, resp)
        resp = schema.conform(endpoint, resp, handled)
        story_ids.apply(resp)
    dh = resp.setdefault("data_headers", {})
    if endpoint in endpoints.SERVER_LIST_ENDPOINTS:
        dh["server_list"] = endpoints.SERVER_LIST
    else:
        dh.pop("server_list", None)
    return resp


def _played_branch(endpoint: str, payload: dict) -> int | None:
    """The story branch of the event a career check_event is committing, read
    off the event still on screen BEFORE the handler replaces it. JP's reply
    names it (`WIRE` 2.31.0: select_index_info_array on every real
    check_event reply, [{branch_number: 1, select_index: <branch>}])."""
    if not endpoint.endswith("/check_event") or not endpoint.startswith("single_mode"):
        return None
    from .. import state as state_store
    from ..handlers import single_mode_team
    full_state = state_store.get_state(payload.get("viewer_id")) or {}
    branch = single_mode_team._served_branch(full_state, payload.get("event_id"),
                                             payload.get("choice_number"))
    return int(branch or 1)


def handle(endpoint: str, payload: dict, sid) -> dict:
    """One JP request through the shared pipeline: the JP request form in, the
    JP reply form out. dispatch() below and the in-process tools share it."""
    payload = flatten_request_common(payload)
    _guard_scenario_family(endpoint)
    if not custom_support.preflight(endpoint, payload):
        return finish(pipeline.handle_decoded(endpoint, payload, sid), endpoint, payload)
    branch = _played_branch(endpoint, payload)
    noted = features.skill_upgrade.before(endpoint, payload)
    noted_sp = features.succession.before(endpoint, payload)
    resp = finish(pipeline.handle_decoded(endpoint, payload, sid), endpoint, payload)
    features.skill_upgrade.after(endpoint, payload, resp, noted)
    features.succession.after(endpoint, payload, resp, noted_sp)
    features.const_walking.after(endpoint, payload, resp)
    features.plushie.after(endpoint, payload, resp)
    features.passes.after(endpoint, payload, resp)
    features.auto_play.after(endpoint, payload, resp)
    features.skill_filter.after(endpoint, payload, resp)
    features.exhibition.after(endpoint, payload, resp)
    features.archive.after(endpoint, payload, resp)
    features.trainer_skill.after(endpoint, payload, resp)
    data = resp.get("data")
    if branch is not None and isinstance(data, dict):
        data["select_index_info_array"] = [{"branch_number": 1, "select_index": branch}]
    return resp


@app.post("/{endpoint_path:path}")
async def dispatch(endpoint_path: str, request: Request) -> Response:
    endpoint = endpoint_path.strip("/")
    if endpoint.startswith("umamusume/"):
        endpoint = endpoint[len("umamusume/"):]
    raw = await request.body()
    headers = dict(request.headers)

    try:
        decoded = transport.open_request(raw, headers, keys.private_scalar(), arming.SESSIONS)
    except transport.WrongKey as exc:
        log.error("JP %s: %s -- is the Hachimi plugin loaded and armed?", endpoint, exc)
        return Response(status_code=400)
    except transport.BadRequest as exc:
        log.error("JP %s: %s", endpoint, exc)
        return Response(status_code=400)

    endpoints.remember_session(decoded)
    token = endpoints.CURRENT_REQUEST.set(decoded)
    try:
        payload = decoded.payload if isinstance(decoded.payload, dict) else {}
        with custom_support.request_context(headers, payload):
            resp = custom_support.project(handle(endpoint, payload, decoded.sid))
    finally:
        endpoints.CURRENT_REQUEST.reset(token)

    wire = transport.seal_reply(resp, decoded)
    body, extra_headers = transport.encode_http_body(wire, headers.get("accept-encoding", ""))
    # `WIRE` the real server's reply headers (TLS proxy in front of Cygames).
    return Response(content=body, media_type="application/x-msgpack; charset=utf-8",
                    headers={"Cache-Control": "max-age=0, no-cache, no-store",
                             "Pragma": "no-cache", **extra_headers})
