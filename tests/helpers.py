from app import db, User

def create_user(email="a@test.com", password_hash=None, role="member", first="A", last="User"):
    if password_hash is None:
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash("password123")

    u = User(
        first_name=first,
        last_name=last,
        email=email,
        password_hash=password_hash,
        role=role
    )
    db.session.add(u)
    db.session.commit()
    return u

def login(client, email="a@test.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)