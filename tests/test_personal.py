from __future__ import annotations

from pathlib import Path

import pytest

from skills.personal import PersonalStore, parse_icalendar


def test_tasks_persist_and_complete(tmp_path: Path):
    path = tmp_path / "personal.db"
    store = PersonalStore(path)
    task = store.create_task("Review Mark-31", "Check the latest milestone", "2026-08-26")
    assert store.list_tasks()[0].task_id == task.task_id
    assert store.complete_task(task.task_id) is True
    assert store.list_tasks() == []
    assert PersonalStore(path).list_tasks(include_completed=True)[0].completed is True


def test_icalendar_parser_is_bounded_and_unescapes_values():
    text = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260826T100000Z
SUMMARY:Project\\, review
END:VEVENT
BEGIN:VEVENT
SUMMARY:Missing start
END:VEVENT
END:VCALENDAR"""
    events = parse_icalendar(text)
    assert len(events) == 1
    assert events[0].summary == "Project, review"
    assert events[0].start == "20260826T100000Z"


def test_email_drafts_are_local_and_never_sent(tmp_path: Path):
    store = PersonalStore(tmp_path / "personal.db")
    draft = store.create_email_draft("person@example.com", "Hello", "Draft body")
    assert store.list_email_drafts()[0].draft_id == draft.draft_id
    assert store.list_email_drafts()[0].body == "Draft body"
    with pytest.raises(ValueError, match="required"):
        store.create_email_draft("", "Hello", "Body")
