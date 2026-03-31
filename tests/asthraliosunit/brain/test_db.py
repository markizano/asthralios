#!/usr/bin/env python3
"""
Tests for BrainDB using an in-memory SQLite database.
"""

import pytest
from datetime import datetime, timezone

from asthralios.brain.db import BrainDB
from asthralios.brain.schema import InboxLogRecord


def make_record(**kwargs) -> InboxLogRecord:
    defaults = dict(
        received_at=datetime.now(timezone.utc),
        source_platform='slack',
        source_user='markizano',
        source_channel='sb-inbox',
        raw_message='test message',
        category='projects',
        name='Test project',
        confidence=0.9,
        filed_path='/tmp/brain/projects/2026-03-31-test.md',
        status='filed',
    )
    defaults.update(kwargs)
    return InboxLogRecord(**defaults)


@pytest.fixture
def db(tmp_path):
    """BrainDB backed by a temp file (not :memory: so Path can be used)."""
    return BrainDB(str(tmp_path / 'test.db'))


class TestBrainDB:

    def test_init_creates_tables(self, db):
        conn = db._connect()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert 'inbox_log' in tables
        assert 'digest_log' in tables

    def test_log_entry_returns_id(self, db):
        record = make_record()
        row_id = db.log_entry(record)
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_log_entry_multiple_increments(self, db):
        id1 = db.log_entry(make_record())
        id2 = db.log_entry(make_record())
        assert id2 > id1

    def test_get_entry(self, db):
        record = make_record(name='Retrieve me', category='ideas')
        row_id = db.log_entry(record)
        row = db.get_entry(row_id)
        assert row is not None
        assert row['name'] == 'Retrieve me'
        assert row['category'] == 'ideas'

    def test_get_entry_nonexistent(self, db):
        assert db.get_entry(9999) is None

    def test_update_status(self, db):
        row_id = db.log_entry(make_record(status='filed', category='admin'))
        db.update_status(row_id, 'fix_applied', fix_original_cat='admin')
        row = db.get_entry(row_id)
        assert row['status'] == 'fix_applied'
        assert row['fix_original_cat'] == 'admin'

    def test_update_filed_path(self, db):
        row_id = db.log_entry(make_record(filed_path=None))
        db.update_filed_path(row_id, '/new/path/file.md')
        row = db.get_entry(row_id)
        assert row['filed_path'] == '/new/path/file.md'

    def test_get_latest_for_user(self, db):
        db.log_entry(make_record(source_user='alice', status='filed', name='First'))
        db.log_entry(make_record(source_user='alice', status='filed', name='Second'))
        db.log_entry(make_record(source_user='bob', status='filed', name='Other'))

        row = db.get_latest_for_user('alice', ['filed'])
        assert row is not None
        assert row['name'] == 'Second'

    def test_get_latest_for_user_no_match(self, db):
        assert db.get_latest_for_user('nobody', ['filed']) is None

    def test_get_latest_for_user_status_filter(self, db):
        db.log_entry(make_record(source_user='alice', status='fix_applied', name='Old'))
        db.log_entry(make_record(source_user='alice', status='needs_review', name='Pending'))
        row = db.get_latest_for_user('alice', ['filed', 'needs_review'])
        assert row['name'] == 'Pending'

    def test_get_active_projects(self, db):
        db.log_entry(make_record(category='projects', status='filed', name='P1'))
        db.log_entry(make_record(category='projects', status='fix_applied', name='P2'))
        db.log_entry(make_record(category='ideas', status='filed', name='I1'))
        rows = db.get_active_projects()
        names = [r['name'] for r in rows]
        assert 'P1' in names
        assert 'P2' not in names
        assert 'I1' not in names

    def test_get_pending_people(self, db):
        db.log_entry(make_record(category='people', name='Alice'))
        db.log_entry(make_record(category='projects', name='Not a person'))
        rows = db.get_pending_people()
        assert all(r['category'] == 'people' for r in rows)
        assert any(r['name'] == 'Alice' for r in rows)

    def test_get_open_admin(self, db):
        db.log_entry(make_record(category='admin', status='filed', name='A1'))
        db.log_entry(make_record(category='admin', status='fix_applied', name='A2'))
        rows = db.get_open_admin()
        names = [r['name'] for r in rows]
        assert 'A1' in names
        assert 'A2' not in names

    def test_get_past_week_includes_recent(self, db):
        row_id = db.log_entry(make_record(name='Recent entry'))
        rows = db.get_past_week()
        assert any(r['id'] == row_id for r in rows)

    def test_log_digest(self, db):
        db.log_digest('daily', 5)
        row = db.get_last_digest('daily')
        assert row is not None
        assert row['message_count'] == 5
        assert row['digest_type'] == 'daily'

    def test_get_last_digest_none(self, db):
        assert db.get_last_digest('weekly') is None

    def test_log_needs_review(self, db):
        record = make_record(
            status='needs_review',
            category=None,
            name=None,
            clarification_question='Which category?',
        )
        row_id = db.log_entry(record)
        row = db.get_entry(row_id)
        assert row['status'] == 'needs_review'
        assert row['clarification_q'] == 'Which category?'
        assert row['category'] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
