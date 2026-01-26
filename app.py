# -----------------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------------

import os
import uuid
from datetime import datetime
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, abort
from flask_sqlalchemy import SQLAlchemy
from google.api_core.exceptions import PermissionDenied
from google.cloud import firestore
from google.cloud import storage
from sqlalchemy.exc import OperationalError
from sqlalchemy import and_
from urllib.parse import urlparse
from uuid import uuid4
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from google.cloud import storage
except Exception:
    storage = None


# -----------------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------------

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

cloud_function_url = os.getenv("CLOUD_FUNCTION_URL")

# Local upload config
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# -----------------------------------------------------------------------------------
# Database setup (SQLAlchemy & Firestore)
# -----------------------------------------------------------------------------------

# SQLAlchemy
database_url = os.getenv("DATABASE_URL") or "sqlite:///society.db"
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Firestore (for activity logs)
firestore_db = firestore.Client()


# -----------------------------------------------------------------------------------
# SQL Models
# -----------------------------------------------------------------------------------

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
    image_url = db.Column(db.String(500), nullable=True)

class RSVP(db.Model):
    __tablename__ = "rsvps"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), primary_key=True)
    status = db.Column(db.String(20), default="going", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# -----------------------------------------------------------------------------------
# Functions (helpers, authentication, template contexts)
# -----------------------------------------------------------------------------------

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

@app.context_processor
def inject_user_context():
    user = None
    try:
        user = get_current_user()
    except OperationalError:
        user = None

    return {
        "current_user": user,
        "current_role": session.get("role"),
        "current_email": session.get("user"),
    }

def safe_referrer(default):
    ref = request.referrer
    if not ref:
        return default
    if urlparse(ref).netloc and urlparse(ref).netloc != request.host:
        return default
    return ref

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_dt_local(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


# -----------------------------------------------------------------------------------
# Logging / integrations
# -----------------------------------------------------------------------------------

def log_action(action, user=None, extra=None):
    if firestore_db is None:
        return

    data = {"action": action, "timestamp": datetime.utcnow()}

    if user:
        data["user"] = user.email
        data["user_id"] = user.id
        data["role"] = user.role

    if extra:
        data.update(extra)

    try:
        firestore_db.collection("activity_logs").add(data)
    except PermissionDenied as e:
        print("Firestore permission denied - logging skipped:", e)
    except Exception as e:
        print("Firestore logging failed - skipped:", e)

def call_rsvp_cloud_function(user, event, status):
    if not cloud_function_url:
        return

    payload = {
        "user_email": user.email,
        "event_id": event.id,
        "new_status": status
    }

    try:
        requests.post(cloud_function_url, json=payload, timeout=3)
    except Exception as e:
        print("Cloud Function call failed:", e)


# -----------------------------------------------------------------------------------
# Image upload
# -----------------------------------------------------------------------------------

def upload_event_image(image_file):
    if not image_file or not image_file.filename:
        return None

    if not allowed_file(image_file.filename):
        abort(400, description="Invalid image type. Use PNG/JPG/WebP.")

    bucket_name = os.getenv("BUCKET_NAME")

    if bucket_name:        
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        ext = image_file.filename.rsplit(".", 1)[1].lower()
        blob_name = f"event-images/{uuid.uuid4().hex}.{ext}"
        blob = bucket.blob(blob_name)

        blob.upload_from_file(image_file.stream, content_type=image_file.mimetype)
        return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

    # Fallback for local development
    ext = image_file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    image_file.save(save_path)

    return url_for("static", filename=f"uploads/{filename}")


# -----------------------------------------------------------------------------------
# Routes: Admin
# -----------------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------------
# Routes: Authentication & Home
# -----------------------------------------------------------------------------------

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
            session["user"] = user.email
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
    session.pop("user", None)
    session.pop("role", None)

    return redirect(url_for("home"))

@app.route("/")
def home():
    try:
        user = get_current_user()
    except OperationalError:
        user = None
    return render_template("home.html", user=user)


# -----------------------------------------------------------------------------------
# Routes: Events & My RSVPs (public/member view)
# -----------------------------------------------------------------------------------

@app.route("/events")
def list_events():
    events = Event.query.order_by(Event.start_time.asc()).all()
    return render_template("events_list.html", events=events)

@app.route("/events/<int:event_id>")
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)
    user = get_current_user()

    existing_rsvp = None
    if user:
        existing_rsvp = RSVP.query.filter_by(user_id=user.id, event_id=event.id).first()

    back_url = safe_referrer(url_for("list_events"))

    return render_template("event_detail.html", event=event, existing_rsvp=existing_rsvp, back_url=back_url)


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

    return render_template("my_rsvps.html", rows=rows)


# -----------------------------------------------------------------------------------
# Routes: Events (committee/admin view)
# -----------------------------------------------------------------------------------

@app.route("/admin/events/new", methods=["GET", "POST"])
@committee_or_admin_required
def admin_event_new():
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()
        start_time = parse_dt_local(request.form["start_time"])
        end_time = parse_dt_local(request.form["end_time"])
        creator = get_current_user()
        image_file = request.files.get("image")
        image_url = upload_event_image(image_file) if image_file and image_file.filename else None

        event = Event(
            title=title,
            description=description,
            location=location,
            start_time=start_time,
            end_time=end_time,
            created_by=creator.id,
            image_url=image_url
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

        image_file = request.files.get("image")
        if image_file and image_file.filename:
            event.image_url = upload_event_image(image_file)

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


# -----------------------------------------------------------------------------------
# Routes: RSVP actions (all view)
# -----------------------------------------------------------------------------------

@app.route("/events/<int:event_id>/rsvp", methods=["POST"])
@login_required
def toggle_rsvp(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)

    action = request.form.get("action")
    is_going = (action == "going")

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
    call_rsvp_cloud_function(user, event, rsvp.status)
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


# -----------------------------------------------------------------------------------
# Routes: RSVP actions (committee/admin view)
# -----------------------------------------------------------------------------------

@app.route("/events/<int:event_id>/rsvps")
@committee_or_admin_required
def event_rsvps(event_id):
    event = Event.query.get_or_404(event_id)

    rows = (
        db.session.query(User, RSVP)
        .join(RSVP, RSVP.user_id == User.id)
        .filter(RSVP.event_id == event.id, RSVP.status == "going")
        .order_by(User.first_name.asc(), User.last_name.asc())
        .all()
    )

    return render_template("event_rsvps.html", event=event, rows=rows)


# -----------------------------------------------------------------------------------
# Routes: REST APIs
# -----------------------------------------------------------------------------------

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

@app.route("/api/events/<int:event_id>/rsvp", methods=["POST"])
@login_required
def api_toggle_rsvp(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)

    body = request.get_json(silent=True) or {}
    is_going = bool(body.get("going", False))

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
    call_rsvp_cloud_function(user, event, rsvp.status)

    return {
        "message": "RSVP updated",
        "event_id": event.id,
        "status": rsvp.status
    }, 200


# -----------------------------------------------------------------------------------
# Routes: Main
# -----------------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)