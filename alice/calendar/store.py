from __future__ import annotations
import json, re, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .models import CalendarEvent

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_RECURRENCE = {None, "daily", "weekly", "monthly"}

def _parse(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("start/end must be ISO-8601 timestamps") from exc
    if dt.tzinfo is None:
        raise ValueError("calendar timestamps must include a timezone")
    return dt.astimezone(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()

class CalendarStore:
    """Local persistent calendar. External calendars are intentionally not implied."""
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2])
        self.path = self.root / "alice_workspace" / "calendar" / "events.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = self._load()

    def _load(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError): return {}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.events, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, title, start, end, description="", location="", recurrence=None, reminders=None, event_id=None):
        if not str(title).strip(): raise ValueError("title is required")
        s, e = _parse(start), _parse(end)
        if e <= s: raise ValueError("end must be after start")
        if recurrence not in _RECURRENCE: raise ValueError("recurrence must be daily, weekly, monthly, or None")
        reminders = sorted({int(x) for x in (reminders or [])})
        if any(x < 0 for x in reminders): raise ValueError("reminders must be non-negative minutes")
        event_id = event_id or uuid.uuid4().hex[:12]
        if not _ID_RE.fullmatch(event_id): raise ValueError("invalid event_id")
        if event_id in self.events: raise FileExistsError(event_id)
        now = time.time()
        ev = CalendarEvent(event_id, str(title).strip(), _iso(s), _iso(e), str(description), str(location), recurrence, reminders, now, now)
        self.events[event_id] = ev.__dict__.copy(); self._save(); return self.get(event_id)

    def get(self, event_id):
        if event_id not in self.events: raise KeyError(event_id)
        return CalendarEvent(**self.events[event_id])

    def cancel(self, event_id):
        ev = self.get(event_id); ev.cancelled = True; ev.updated_at = time.time()
        self.events[event_id] = ev.__dict__.copy(); self._save(); return ev

    def delete(self, event_id):
        if event_id not in self.events: return False
        del self.events[event_id]; self._save(); return True

    def list(self, include_cancelled=False):
        items = [CalendarEvent(**x) for x in self.events.values() if include_cancelled or not x.get("cancelled")]
        return sorted(items, key=lambda x: x.start)

    def occurrences(self, start, end):
        """Return event occurrences overlapping [start,end), bounded to 10,000 iterations."""
        window_start, window_end = _parse(start), _parse(end)
        if window_end <= window_start: raise ValueError("end must be after start")
        result = []
        for ev in self.list():
            s, e = _parse(ev.start), _parse(ev.end)
            duration = e - s
            cur = s
            step_count = 0
            while cur < window_end and step_count < 10000:
                cur_end = cur + duration
                if cur_end > window_start and cur < window_end:
                    result.append((ev, _iso(cur), _iso(cur_end)))
                if ev.recurrence is None: break
                if ev.recurrence == "daily": cur += timedelta(days=1)
                elif ev.recurrence == "weekly": cur += timedelta(weeks=1)
                else:
                    month = cur.month + 1; year = cur.year + (month - 1)//12; month = (month - 1)%12 + 1
                    import calendar
                    day = min(cur.day, calendar.monthrange(year, month)[1])
                    cur = cur.replace(year=year, month=month, day=day)
                step_count += 1
        return sorted(result, key=lambda x: x[1])

    def conflicts(self, start, end, exclude_event_id=None):
        s, e = _parse(start), _parse(end)
        if e <= s: raise ValueError("end must be after start")
        # Include occurrences that start before the requested window but overlap it.
        # Look back by the longest existing event duration so the overlap cannot be missed.
        max_duration = timedelta(0)
        for raw in self.events.values():
            if raw.get("cancelled"): continue
            try:
                duration = _parse(raw["end"]) - _parse(raw["start"])
                if duration > max_duration: max_duration = duration
            except (KeyError, ValueError):
                continue
        scan_start = s - max_duration
        return [item for item in self.occurrences(_iso(scan_start), _iso(e))
                if item[0].event_id != exclude_event_id and _parse(item[1]) < e and _parse(item[2]) > s]
