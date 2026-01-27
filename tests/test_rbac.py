from tests.helpers import create_user, login

def test_admin_page_blocks_member(client, app):
    create_user(email="m@test.com", role="member")
    login(client, "m@test.com", "password123")
    res = client.get("/admin/users")
    assert res.status_code == 403

def test_admin_page_allows_admin(client, app):
    create_user(email="admin@test.com", role="admin")
    login(client, "admin@test.com", "password123")
    res = client.get("/admin/users")
    assert res.status_code == 200