"""Gate-monitor announcements: EA management + the key-guarded edge feed."""

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.models import DisplayMessage

URL = "/assistant/display-messages"
EDGE_URL = "/edge/display-messages"
EDGE = {"X-Edge-Key": settings.edge_api_key}


def _add(client, headers, text):
    r = client.post(URL, headers=headers, json={"text": text})
    assert r.status_code == 201, r.text
    return r.json()


def _texts(client, headers):
    return [m["text"] for m in client.get(URL, headers=headers).json()]


# ── Access control ───────────────────────────────────────────────────────────
def test_requires_login(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"text": "Hi"}).status_code == 401


@pytest.mark.parametrize("who", ["emp_headers", "sup_headers", "chief_headers"])
def test_only_assistants_can_manage(client, request, who):
    headers = request.getfixturevalue(who)
    assert client.get(URL, headers=headers).status_code == 403
    assert client.post(URL, headers=headers, json={"text": "Hi"}).status_code == 403


def test_non_assistant_cannot_edit_remove_or_reorder(client, ea_headers, sup_headers):
    msg = _add(client, ea_headers, "Board meeting at 3 PM")
    assert client.patch(f"{URL}/{msg['id']}", headers=sup_headers,
                        json={"text": "x"}).status_code == 403
    assert client.delete(f"{URL}/{msg['id']}", headers=sup_headers).status_code == 403
    assert client.put(f"{URL}/order", headers=sup_headers,
                      json={"ids": [msg["id"]]}).status_code == 403


# ── Add ──────────────────────────────────────────────────────────────────────
def test_board_starts_empty(client, ea_headers):
    assert client.get(URL, headers=ea_headers).json() == []


def test_add_appends_to_bottom(client, ea_headers):
    first = _add(client, ea_headers, "Board meeting at 3 PM")
    second = _add(client, ea_headers, "Fire drill on Friday")
    assert first["position"] < second["position"]
    assert _texts(client, ea_headers) == ["Board meeting at 3 PM", "Fire drill on Friday"]


def test_add_normalizes_whitespace_and_control_chars(client, ea_headers):
    msg = _add(client, ea_headers, "  Canteen\nclosed \t today\x00  ")
    assert msg["text"] == "Canteen closed today"


def test_add_keeps_hindi_text_intact(client, ea_headers):
    text = "सुरक्षा सर्वोपरि — क्षेत्र"
    assert _add(client, ea_headers, text)["text"] == text


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_add_rejects_empty(client, ea_headers, text):
    r = client.post(URL, headers=ea_headers, json={"text": text})
    assert r.status_code == 422


def test_add_enforces_length_limit(client, ea_headers):
    limit = settings.display_message_max_chars
    assert _add(client, ea_headers, "a" * limit)["text"] == "a" * limit
    r = client.post(URL, headers=ea_headers, json={"text": "a" * (limit + 1)})
    assert r.status_code == 422
    assert str(limit) in r.json()["detail"]


def test_add_enforces_count_limit(client, ea_headers):
    for i in range(settings.display_message_max_count):
        _add(client, ea_headers, f"Message {i}")
    r = client.post(URL, headers=ea_headers, json={"text": "One too many"})
    assert r.status_code == 409
    assert len(_texts(client, ea_headers)) == settings.display_message_max_count


def test_removed_messages_free_up_space(client, ea_headers):
    ids = [_add(client, ea_headers, f"Message {i}")["id"]
           for i in range(settings.display_message_max_count)]
    client.delete(f"{URL}/{ids[0]}", headers=ea_headers)
    assert _add(client, ea_headers, "Fits now")["text"] == "Fits now"


def test_message_text_is_stored_verbatim_not_as_html(client, ea_headers):
    # Rendering safety is the display's job; the API must not alter the text.
    msg = _add(client, ea_headers, "<b>Hello</b> & <script>x</script>")
    assert msg["text"] == "<b>Hello</b> & <script>x</script>"


# ── Edit ─────────────────────────────────────────────────────────────────────
def test_edit_changes_text_and_keeps_position(client, ea_headers):
    a = _add(client, ea_headers, "First")
    _add(client, ea_headers, "Second")
    r = client.patch(f"{URL}/{a['id']}", headers=ea_headers, json={"text": " First (updated) "})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "First (updated)"
    assert r.json()["position"] == a["position"]
    assert r.json()["updated_at"] is not None
    assert _texts(client, ea_headers) == ["First (updated)", "Second"]


def test_edit_validates_text(client, ea_headers):
    a = _add(client, ea_headers, "First")
    too_long = "a" * (settings.display_message_max_chars + 1)
    assert client.patch(f"{URL}/{a['id']}", headers=ea_headers,
                        json={"text": too_long}).status_code == 422
    assert client.patch(f"{URL}/{a['id']}", headers=ea_headers,
                        json={"text": "  "}).status_code == 422
    assert _texts(client, ea_headers) == ["First"]


def test_edit_missing_or_removed_message_is_404(client, ea_headers):
    assert client.patch(f"{URL}/9999", headers=ea_headers, json={"text": "x"}).status_code == 404
    a = _add(client, ea_headers, "Gone soon")
    client.delete(f"{URL}/{a['id']}", headers=ea_headers)
    assert client.patch(f"{URL}/{a['id']}", headers=ea_headers,
                        json={"text": "back?"}).status_code == 404


# ── Remove (soft delete) ─────────────────────────────────────────────────────
def test_remove_hides_message_but_keeps_audit_row(client, ea_headers, db_session):
    a = _add(client, ea_headers, "Temporary notice")
    _add(client, ea_headers, "Stays")
    r = client.delete(f"{URL}/{a['id']}", headers=ea_headers)
    assert r.status_code == 204
    assert _texts(client, ea_headers) == ["Stays"]

    db_session.expire_all()
    row = db_session.execute(
        select(DisplayMessage).where(DisplayMessage.id == a["id"])
    ).scalar_one()
    assert row.removed_at is not None
    assert row.removed_by is not None
    assert row.text == "Temporary notice"


def test_remove_twice_is_404(client, ea_headers):
    a = _add(client, ea_headers, "Once")
    assert client.delete(f"{URL}/{a['id']}", headers=ea_headers).status_code == 204
    assert client.delete(f"{URL}/{a['id']}", headers=ea_headers).status_code == 404


# ── Reorder ──────────────────────────────────────────────────────────────────
def test_reorder(client, ea_headers):
    a = _add(client, ea_headers, "A")
    b = _add(client, ea_headers, "B")
    c = _add(client, ea_headers, "C")
    r = client.put(f"{URL}/order", headers=ea_headers, json={"ids": [c["id"], a["id"], b["id"]]})
    assert r.status_code == 200, r.text
    assert [m["text"] for m in r.json()] == ["C", "A", "B"]
    assert [m["position"] for m in r.json()] == [0, 1, 2]
    assert _texts(client, ea_headers) == ["C", "A", "B"]


def test_add_after_reorder_goes_to_bottom(client, ea_headers):
    a = _add(client, ea_headers, "A")
    b = _add(client, ea_headers, "B")
    client.put(f"{URL}/order", headers=ea_headers, json={"ids": [b["id"], a["id"]]})
    _add(client, ea_headers, "C")
    assert _texts(client, ea_headers) == ["B", "A", "C"]


@pytest.mark.parametrize("make_ids", [
    lambda a, b, gone: [a],                 # missing one
    lambda a, b, gone: [a, b, 9999],         # unknown id
    lambda a, b, gone: [a, b, gone],         # includes a removed message
    lambda a, b, gone: [a, a, b],            # duplicate
])
def test_reorder_rejects_stale_or_invalid_lists(client, ea_headers, make_ids):
    a = _add(client, ea_headers, "A")["id"]
    b = _add(client, ea_headers, "B")["id"]
    gone = _add(client, ea_headers, "Gone")["id"]
    client.delete(f"{URL}/{gone}", headers=ea_headers)
    r = client.put(f"{URL}/order", headers=ea_headers, json={"ids": make_ids(a, b, gone)})
    assert r.status_code == 409
    assert _texts(client, ea_headers) == ["A", "B"]


# ── Edge feed for the gate monitors ──────────────────────────────────────────
def test_edge_feed_requires_edge_key(client, ea_headers):
    assert client.get(EDGE_URL).status_code == 401
    assert client.get(EDGE_URL, headers={"X-Edge-Key": "wrong"}).status_code == 401
    # A logged-in user's token is not a substitute for the edge key.
    assert client.get(EDGE_URL, headers=ea_headers).status_code == 401


def test_edge_feed_empty_board(client):
    r = client.get(EDGE_URL, headers=EDGE)
    assert r.status_code == 200
    assert r.json()["messages"] == []
    assert r.json()["version"]


def test_edge_feed_shows_active_messages_in_order(client, ea_headers):
    a = _add(client, ea_headers, "A")
    b = _add(client, ea_headers, "B")
    c = _add(client, ea_headers, "C")
    client.delete(f"{URL}/{b['id']}", headers=ea_headers)
    client.put(f"{URL}/order", headers=ea_headers, json={"ids": [c["id"], a["id"]]})
    body = client.get(EDGE_URL, headers=EDGE).json()
    assert body["messages"] == [{"id": c["id"], "text": "C"}, {"id": a["id"], "text": "A"}]


def test_edge_version_changes_only_when_board_changes(client, ea_headers):
    def version():
        return client.get(EDGE_URL, headers=EDGE).json()["version"]

    empty = version()
    a = _add(client, ea_headers, "A")
    after_add = version()
    assert after_add != empty
    assert version() == after_add                      # stable when nothing changed

    b = _add(client, ea_headers, "B")
    after_second = version()
    client.put(f"{URL}/order", headers=ea_headers, json={"ids": [b["id"], a["id"]]})
    after_reorder = version()
    assert after_reorder != after_second

    client.patch(f"{URL}/{a['id']}", headers=ea_headers, json={"text": "A edited"})
    after_edit = version()
    assert after_edit != after_reorder

    client.patch(f"{URL}/{a['id']}", headers=ea_headers, json={"text": "A edited"})
    assert version() == after_edit                     # no-op edit

    client.delete(f"{URL}/{b['id']}", headers=ea_headers)
    assert version() != after_edit
