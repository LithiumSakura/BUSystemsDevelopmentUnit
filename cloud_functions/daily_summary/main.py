import os
from datetime import datetime, timezone, timedelta
from google.cloud import firestore

db = firestore.Client()

def _today_utc_date_str():
    return datetime.now(timezone.utc).date().isoformat()

def _parse_iso(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def daily_summary(request):
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=7)

    events = db.collection("events_mirror").stream()
    upcoming = []

    for doc in events:
        e = doc.to_dict()
        start = _parse_iso(e.get("start_time") or "")
        if not start:
            continue

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        if now <= start <= horizon:
            event_id = str(e.get("event_id"))
            stats = db.collection("event_stats").document(event_id).get()
            going = 0
            if stats.exists:
                going = int(stats.to_dict().get("going_count", 0))

            upcoming.append({
                "event_id": e.get("event_id"),
                "title": e.get("title"),
                "location": e.get("location"),
                "start_time": e.get("start_time"),
                "going_count": going,
            })

    upcoming.sort(key=lambda x: (-x["going_count"], x["start_time"] or ""))

    summary_doc = {
        "date": _today_utc_date_str(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upcoming_count": len(upcoming),
        "top_events": upcoming[:5],
        "window_days": 7,
    }

    db.collection("daily_summaries").document(summary_doc["date"]).set(summary_doc, merge=True)
    return ({"ok": True, "summary": summary_doc}, 200)