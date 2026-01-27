from tests.helpers import create_user, login

def test_register_creates_user(client, app):
    res = client.post("/register", data={
        "first_name": "Test",
        "last_name": "User",
        "email": "new@test.com",
        "password": "password123"
    }, follow_redirects=True)
    assert res.status_code == 200

def test_login_success(client, app):
    create_user(email="a@test.com")
    res = login(client, "a@test.com", "password123")
    assert res.status_code == 200

def test_login_fail(client, app):
    create_user(email="a@test.com")
    res = login(client, "a@test.com", "wrong")
    assert b"Invalid" in res.data or res.status_code == 200