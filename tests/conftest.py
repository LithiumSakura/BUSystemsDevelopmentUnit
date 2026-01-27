import pytest
from app import app as flask_app, db

@pytest.fixture()
def app(monkeypatch):
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret",
    )

    monkeypatch.setattr("app.firestore_db", None)
    monkeypatch.setattr("app.call_rsvp_cloud_function", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.log_action", lambda *args, **kwargs: None)

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.drop_all()

@pytest.fixture()
def client(app):
    return app.test_client()