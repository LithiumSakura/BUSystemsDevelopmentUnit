from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps
from flask import abort
from google.cloud import firestore

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")


# Databases setup

## SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///society.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

## Firestore
firestore_db = firestore.Client()

## SQL Models
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)

    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), default="member", nullable=False)
    committee_position = db.Column(db.String(50), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class Event(db.Model):
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(200), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

class RSVP(db.Model):
    __tablename__ = "rsvps"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), primary_key=True)
    status = db.Column(db.String(20), default="going", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# Creating roles
def get_current_user():
    email = session.get("user")
    if not email:
        return None
    return User.query.filter_by(email=email).first()

def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped

def committee_or_admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        if session.get("role") not in ["committee", "admin"]:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped

def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped

# For firestore DB
def log_action(action, user=None, extra=None):
    data = {
        "action": action,
        "timestamp": datetime.utcnow()
    }

    if user:
        data["user_email"] = user.email
        data["user_id"] = user.id
        data["role"] = user.role

    if extra:
        data.update(extra)

    firestore_db.collection("activity_logs").add(data)


# Routes

# Admin backdoors / routes
@app.route("/init-db")
def init_db():
    db.create_all()
    return "DB initialised! You can now register/login."

@app.route("/make-me-admin")
@login_required
def make_me_admin():
    user = get_current_user()
    user.role = "admin"
    db.session.commit()
    session["role"] = "admin"
    return "You are now admin."

@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    users = User.query.order_by(User.first_name.asc()).all()

    if request.method == "POST":
        user_id = int(request.form["user_id"])
        is_committee = request.form.get("is_committee") == "on"
        position = request.form.get("committee_position")
        user = User.query.get_or_404(user_id)
        if is_committee:
            user.role = "committee"
            user.committee_position = position
        else:
            user.role = "member"
            user.committee_position = None
        db.session.commit()
        log_action(
            "ROLE_UPDATED",
            user=get_current_user(),
            extra={
                "target_user_id": user.id,
                "target_email": user.email,
                "new_role": user.role,
                "committee_position": user.committee_position
            }
        )
        return redirect(url_for("admin_users"))
    return render_template("admin_users.html", users=users)

@app.route("/admin/logs")
@admin_required
def admin_logs():
    logs = (
        firestore_db.collection("activity_logs")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(50)
        .stream()
    )
    return render_template("admin_logs.html", logs=logs)


# General user routes
@app.route("/")
def home():
    user = get_current_user()
    return render_template("home.html", user=user)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form["first_name"].strip()
        last_name = request.form["last_name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        existing = User.query.filter_by(email=email).first()
        if existing:
            return "User already exists"
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=generate_password_hash(password),
            role="member"
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_email"] = user.email
            session["role"] = user.role
            log_action(
                "LOGIN",
                user=user
            )
            return redirect(url_for("home"))
        return "Invalid credentials"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_email", None)
    session.pop("role", None)
    return redirect(url_for("home"))

# Event routes
@app.route("/api/events")
def api_events():
    events = Event.query.order_by(Event.start_time.asc()).all()

    return {
        "events": [
            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "location": event.location,
                "start_time": event.start_time.isoformat(),
                "end_time": event.end_time.isoformat()
            }
            for event in events
        ]
    }

@app.route("/events")
def list_events():
    events = Event.query.order_by(Event.start_time.asc()).all()
    return render_template("event_list.html", events=events, user_email=session.get("user"), role=session.get("role"))

@app.route("/events/<int:event_id>")
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)
    user = get_current_user()
    existing_rsvp = None
    if user:
        existing_rsvp = RSVP.query.filter_by(user_id=user.id, event_id=event.id).first()
    return render_template(
        "event_detail.html",
        event=event,
        user_email=session.get("user"),
        role=session.get("role"),
        existing_rsvp=existing_rsvp
    )

# Society committee member view
@app.route("/admin/events/new", methods=["GET", "POST"])
@committee_or_admin_required
def admin_event_new():
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()
        # Self-reminder, format: "YYYY-MM-DDTHH:MM"
        start_time = datetime.fromisoformat(request.form["start_time"])
        end_time = datetime.fromisoformat(request.form["end_time"])
        creator = get_current_user()
        event = Event(
            title=title,
            description=description,
            location=location,
            start_time=start_time,
            end_time=end_time,
            created_by=creator.id
        )
        db.session.add(event)
        db.session.commit()
        return redirect(url_for("list_events"))
    return render_template("admin_event_form.html", mode="create")

@app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
@committee_or_admin_required
def admin_event_edit(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == "POST":
        event.title = request.form["title"].strip()
        event.description = request.form.get("description", "").strip()
        event.location = request.form.get("location", "").strip()
        event.start_time = datetime.fromisoformat(request.form["start_time"])
        event.end_time = datetime.fromisoformat(request.form["end_time"])
        db.session.commit()
        return redirect(url_for("event_detail", event_id=event.id))
    return render_template("admin_event_form.html", mode="edit", event=event)

@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
@committee_or_admin_required
def admin_event_delete(event_id):
    event = Event.query.get_or_404(event_id)
    RSVP.query.filter_by(event_id=event.id).delete()
    db.session.delete(event)
    db.session.commit()
    return redirect(url_for("list_events"))

# Event RSVP routes
@app.route("/events/<int:event_id>/rsvp", methods=["POST"])
@login_required
def toggle_rsvp(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    is_going = request.form.get("going") == "on"
    rsvp = RSVP.query.filter_by(user_id=user.id, event_id=event.id).first()
    if rsvp:
        rsvp.status = "going" if is_going else "cancelled"
    else:
        rsvp = RSVP(
            user_id=user.id,
            event_id=event.id,
            status="going" if is_going else "cancelled"
        )
        db.session.add(rsvp)
    db.session.commit()
    log_action(
        "RSVP_UPDATED",
        user=user,
        extra={
            "event_id": event.id,
            "event_title": event.title,
            "new_status": rsvp.status
        }
    )
    return redirect(url_for("event_detail", event_id=event.id))

@app.route("/my-rsvps")
@login_required
def my_rsvps():
    user = get_current_user()
    rows = (
        db.session.query(RSVP, Event)
        .join(Event, RSVP.event_id == Event.id)
        .filter(RSVP.user_id == user.id, RSVP.status == "going")
        .order_by(Event.start_time.asc())
        .all()
    )
    return render_template("my_rsvps.html", rows=rows, user_email=session.get("user"), role=session.get("role"))















if __name__ == "__main__":
    app.run(debug=True)