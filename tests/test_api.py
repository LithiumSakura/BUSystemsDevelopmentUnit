from datetime import datetime, timedelta, timezone
from tests.helpers import create_user, login
from app import db, Event

def make_event(creator_id):
    e = Event(
        title="Test Event",
        description="Desc",
        location="Room",
        start_time=datetime.now(timezone.utc) + timedelta(days=1),
        end_time=datetime.now(timezone.utc) + timedelta(days=1, hours=1),
        created_by=creator_id,
        image_url=None
    )
    db.session.add(e)
    db.session.commit()
    return e

def test_api_events_returns_list(client, app):
    res = client.get("/api/events")
    assert res.status_code == 200
    assert "events" in res.get_json()

def test_api_rsvp_requires_login(client, app):
    u = create_user(email="a@test.com")
    e = make_event(u.id)
    res = client.post(f"/api/events/{e.id}/rsvp", json={"going": True})
    assert res.status_code in (302, 401)

def test_api_rsvp_updates_when_logged_in(client, app):
    u = create_user(email="a@test.com")
    e = make_event(u.id)
    login(client, "a@test.com", "password123")
    res = client.post(f"/api/events/{e.id}/rsvp", json={"going": True})
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "going"