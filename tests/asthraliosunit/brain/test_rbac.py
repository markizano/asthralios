#!/usr/bin/env python3
"""
Tests for RBACManager: role resolution, admin seeding, access logging, blocked flow.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from asthralios.brain.db import BrainDB
from asthralios.brain.rbac import RBACManager, UserIdentity, AccessContext


def make_config(
    admins: dict = None,
    default_role: str = 'user',
    blocked_message: str = None,
):
    cfg = MagicMock()
    rbac_section = {
        'admins': admins or {},
        'default_role': default_role,
    }
    if blocked_message:
        rbac_section['blocked_message'] = blocked_message
    cfg.rbac = rbac_section
    # Make getattr(config, 'rbac', {}) work
    cfg.__class__.__getattribute__ = lambda self, name: (
        rbac_section if name == 'rbac' else MagicMock()
    )
    return cfg


@pytest.fixture
def db(tmp_path):
    return BrainDB(str(tmp_path / 'test.db'))


@pytest.fixture
def config_no_admins():
    cfg = MagicMock()
    cfg.rbac = {'admins': {}, 'default_role': 'user'}
    return cfg


@pytest.fixture
def config_with_admin():
    cfg = MagicMock()
    cfg.rbac = {
        'admins': {'slack': 'U01ADMIN', 'discord': '999888777'},
        'default_role': 'user',
    }
    return cfg


@pytest.fixture
def rbac_no_admins(db, config_no_admins):
    return RBACManager(db, config_no_admins)


@pytest.fixture
def rbac_with_admin(db, config_with_admin):
    return RBACManager(db, config_with_admin)


class TestRBACManagerInit:

    def test_seeds_slack_admin(self, db, config_with_admin):
        RBACManager(db, config_with_admin)
        row = db._connect().execute(
            "SELECT role FROM users WHERE platform='slack' AND platform_user_id='U01ADMIN'"
        ).fetchone()
        assert row is not None
        assert row['role'] == 'admin'

    def test_seeds_discord_admin(self, db, config_with_admin):
        RBACManager(db, config_with_admin)
        row = db._connect().execute(
            "SELECT role FROM users WHERE platform='discord' AND platform_user_id='999888777'"
        ).fetchone()
        assert row is not None
        assert row['role'] == 'admin'

    def test_seeds_admin_list(self, db):
        cfg = MagicMock()
        cfg.rbac = {'admins': {'slack': ['U01ADMIN', 'U02ADMIN']}, 'default_role': 'user'}
        RBACManager(db, cfg)
        rows = db._connect().execute(
            "SELECT platform_user_id FROM users WHERE platform='slack' AND role='admin'"
        ).fetchall()
        ids = {r['platform_user_id'] for r in rows}
        assert 'U01ADMIN' in ids
        assert 'U02ADMIN' in ids

    def test_seeding_is_idempotent(self, db, config_with_admin):
        RBACManager(db, config_with_admin)
        RBACManager(db, config_with_admin)  # second call should not error or duplicate
        rows = db._connect().execute(
            "SELECT * FROM users WHERE platform='slack' AND platform_user_id='U01ADMIN'"
        ).fetchall()
        assert len(rows) == 1

    def test_admin_seed_force_overwrites_existing_role(self, db):
        # Pre-create user as 'blocked'
        db.upsert_user('slack', 'U01ADMIN', 'old name', 'blocked', force_role=True)
        cfg = MagicMock()
        cfg.rbac = {'admins': {'slack': 'U01ADMIN'}, 'default_role': 'user'}
        RBACManager(db, cfg)
        row = db._connect().execute(
            "SELECT role FROM users WHERE platform='slack' AND platform_user_id='U01ADMIN'"
        ).fetchone()
        assert row['role'] == 'admin'


class TestResolve:

    def test_new_user_gets_default_role(self, rbac_no_admins):
        identity = UserIdentity(platform='slack', platform_user_id='U99999', display_name='Alice')
        ctx = rbac_no_admins.resolve(identity, '#general', 'hello')
        assert isinstance(ctx, AccessContext)
        assert ctx.role == 'user'
        assert ctx.identity is identity
        assert ctx.channel == '#general'

    def test_known_admin_resolves_as_admin(self, rbac_with_admin):
        identity = UserIdentity(platform='slack', platform_user_id='U01ADMIN', display_name='Admin')
        ctx = rbac_with_admin.resolve(identity, '#brain', 'file this')
        assert ctx.role == 'admin'

    def test_updates_display_name_on_revisit(self, db, config_no_admins):
        rbac = RBACManager(db, config_no_admins)
        identity = UserIdentity(platform='slack', platform_user_id='U11111', display_name='Old Name')
        rbac.resolve(identity, '#general', 'hi')
        identity2 = UserIdentity(platform='slack', platform_user_id='U11111', display_name='New Name')
        rbac.resolve(identity2, '#general', 'hi again')
        row = db._connect().execute(
            "SELECT display_name FROM users WHERE platform_user_id='U11111'"
        ).fetchone()
        assert row['display_name'] == 'New Name'

    def test_blocked_user_resolved_correctly(self, db, config_no_admins):
        db.upsert_user('discord', 'D99999', 'Blocked User', 'blocked', force_role=True)
        rbac = RBACManager(db, config_no_admins)
        identity = UserIdentity(platform='discord', platform_user_id='D99999', display_name='Blocked User')
        ctx = rbac.resolve(identity, '#general', 'let me in')
        assert ctx.role == 'blocked'


class TestIsAllowed:

    def test_admin_allowed_everything(self, rbac_no_admins):
        identity = UserIdentity(platform='slack', platform_user_id='X', display_name='')
        ctx = AccessContext(identity=identity, role='admin', channel='#c', message='msg')
        assert rbac_no_admins.is_allowed(ctx, 'admin') is True
        assert rbac_no_admins.is_allowed(ctx, 'user') is True
        assert rbac_no_admins.is_allowed(ctx, 'blocked') is True

    def test_user_allowed_user_not_admin(self, rbac_no_admins):
        identity = UserIdentity(platform='slack', platform_user_id='X', display_name='')
        ctx = AccessContext(identity=identity, role='user', channel='#c', message='msg')
        assert rbac_no_admins.is_allowed(ctx, 'user') is True
        assert rbac_no_admins.is_allowed(ctx, 'admin') is False

    def test_blocked_denied_everything(self, rbac_no_admins):
        identity = UserIdentity(platform='slack', platform_user_id='X', display_name='')
        ctx = AccessContext(identity=identity, role='blocked', channel='#c', message='msg')
        assert rbac_no_admins.is_allowed(ctx, 'user') is False
        assert rbac_no_admins.is_allowed(ctx, 'admin') is False
        assert rbac_no_admins.is_allowed(ctx, 'blocked') is True


class TestLogAccess:

    def test_log_writes_to_db(self, db, rbac_no_admins):
        identity = UserIdentity(platform='slack', platform_user_id='U12345', display_name='Bob')
        ctx = AccessContext(identity=identity, role='user', channel='#general', message='hello there')
        rbac_no_admins.log_access(ctx, 'chat', 'ok', detail='channel=#general')
        rows = db.get_access_log(limit=5, platform_user_id='U12345')
        assert len(rows) == 1
        assert rows[0]['action'] == 'chat'
        assert rows[0]['outcome'] == 'ok'
        assert rows[0]['role_at_time'] == 'user'
        assert rows[0]['detail'] == 'channel=#general'

    def test_log_preview_truncated(self, db, rbac_no_admins):
        identity = UserIdentity(platform='slack', platform_user_id='U99999', display_name='')
        long_msg = 'a' * 300
        ctx = AccessContext(identity=identity, role='user', channel='#c', message=long_msg)
        rbac_no_admins.log_access(ctx, 'chat', 'ok')
        rows = db.get_access_log(limit=1, platform_user_id='U99999')
        assert len(rows[0]['message_preview']) <= 200

    def test_blocked_logs_every_attempt(self, db, rbac_no_admins):
        identity = UserIdentity(platform='discord', platform_user_id='D55555', display_name='Troll')
        ctx = AccessContext(identity=identity, role='blocked', channel='#general', message='let me in')
        rbac_no_admins.log_access(ctx, 'blocked', 'denied')
        rbac_no_admins.log_access(ctx, 'blocked', 'denied')
        rows = db.get_access_log(limit=10, platform_user_id='D55555')
        assert len(rows) == 2


class TestSetRole:

    def test_set_role_changes_user(self, db, rbac_with_admin):
        db.upsert_user('slack', 'U55555', 'Charlie', 'user')
        rbac_with_admin.set_role('slack', 'U55555', 'blocked')
        row = db._connect().execute(
            "SELECT role FROM users WHERE platform_user_id='U55555'"
        ).fetchone()
        assert row['role'] == 'blocked'

    def test_set_role_to_admin(self, db, rbac_no_admins):
        db.upsert_user('discord', 'D11111', 'Dana', 'user')
        rbac_no_admins.set_role('discord', 'D11111', 'admin')
        row = db._connect().execute(
            "SELECT role FROM users WHERE platform_user_id='D11111'"
        ).fetchone()
        assert row['role'] == 'admin'


class TestListUsers:

    def test_list_returns_all(self, db, rbac_no_admins):
        db.upsert_user('slack', 'U1', 'Alice', 'user')
        db.upsert_user('discord', 'D2', 'Bob', 'admin')
        rows = rbac_no_admins.list_users()
        ids = {r['platform_user_id'] for r in rows}
        assert 'U1' in ids
        assert 'D2' in ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
