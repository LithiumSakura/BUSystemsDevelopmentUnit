from datetime import datetime, timedelta
from tests.helpers import create_user, login
from app import db, Event, RSVP

def test_form_rsvp_toggle(client, app):
    u = create_user(email="a@test.com")
    login(client, "a@test.com", "password123")

    e = Event(
        title="Event",
        description="",
        location="",
        start_time=datetime.utcnow() + timedelta(days=1),
        end_time=datetime.utcnow() + timedelta(days=1, hours=2),
        created_by=u.id
    )
    db.session.add(e)
    db.session.commit()

    res = client.post(f"/events/{e.id}/rsvp", data={"action": "going"}, follow_redirects=True)
    assert res.status_code == 200

    rsvp = RSVP.query.filter_by(user_id=u.id, event_id=e.id).first()
    assert rsvp is not None
    assert rsvp.status == "going"