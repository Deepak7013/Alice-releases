import tempfile
from datetime import datetime, timedelta, timezone
import pytest
from alice.calendar import CalendarStore

BASE = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
def iso(dt): return dt.isoformat()

def test_event_lifecycle_and_persistence():
    with tempfile.TemporaryDirectory() as d:
        c = CalendarStore(d)
        e = c.add("Dentist", iso(BASE), iso(BASE+timedelta(hours=1)), location="Clinic", reminders=[30])
        assert e.title == "Dentist" and e.reminders == [30]
        assert c.get(e.event_id).location == "Clinic"
        c2 = CalendarStore(d)
        assert c2.get(e.event_id).title == "Dentist"
        assert c2.cancel(e.event_id).cancelled is True
        assert c2.list() == [] and len(c2.list(include_cancelled=True)) == 1

def test_recurrence_and_conflicts():
    with tempfile.TemporaryDirectory() as d:
        c = CalendarStore(d)
        c.add("Gym", iso(BASE), iso(BASE+timedelta(hours=1)), recurrence="weekly")
        hits = c.occurrences(iso(BASE), iso(BASE+timedelta(days=22)))
        assert len(hits) == 4
        assert len(c.conflicts(iso(BASE+timedelta(minutes=30)), iso(BASE+timedelta(minutes=90)))) == 1

def test_validation():
    with tempfile.TemporaryDirectory() as d:
        c = CalendarStore(d)
        with pytest.raises(ValueError): c.add("", iso(BASE), iso(BASE+timedelta(hours=1)))
        with pytest.raises(ValueError): c.add("Bad", "2026-10-05T09:00:00", iso(BASE+timedelta(hours=1)))
        with pytest.raises(ValueError): c.add("Bad", iso(BASE), iso(BASE))
        with pytest.raises(ValueError): c.add("Bad", iso(BASE), iso(BASE+timedelta(hours=1)), recurrence="yearly")
        with pytest.raises(ValueError): c.add("Bad", iso(BASE), iso(BASE+timedelta(hours=1)), reminders=[-1])

def test_monthly_end_of_month_is_safe():
    with tempfile.TemporaryDirectory() as d:
        c = CalendarStore(d)
        jan31 = datetime(2026, 1, 31, 9, tzinfo=timezone.utc)
        c.add("Monthly", iso(jan31), iso(jan31+timedelta(hours=1)), recurrence="monthly")
        hits = c.occurrences(iso(jan31), iso(datetime(2026,5,1,tzinfo=timezone.utc)))
        assert [x[1][:10] for x in hits] == ["2026-01-31", "2026-02-28", "2026-03-28", "2026-04-28"]
