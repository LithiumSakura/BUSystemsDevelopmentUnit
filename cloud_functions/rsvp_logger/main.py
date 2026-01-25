from google.cloud import firestore
from datetime import datetime
import json

db = firestore.Client()

def log_rsvp_change(request):
    """
    HTTP Cloud Function to log RSVP changes
    """
    if request.method != "POST":
        return ("Method Not Allowed", 405)

    data = request.get_json(silent=True)
    if not data:
        return ("Invalid JSON", 400)

    log_entry = {
        "action": "RSVP_UPDATED_FUNCTION",
        "user_email": data.get("user_email"),
        "event_id": data.get("event_id"),
        "new_status": data.get("new_status"),
        "timestamp": datetime.utcnow()
    }

    db.collection("activity_logs").add(log_entry)

    return json.dumps({"status": "logged"}), 200