"""
RBAC — resolves user identity, manages roles, enforces access.

Roles (in ascending privilege order):
  blocked   — all commands rejected after one polite notice
  user      — general chat only; brain, digest, notify are denied
  admin     — full access to everything

Identity is keyed by (platform, platform_user_id). Both are strings.
platform values: 'slack' | 'discord'

platform_user_id values:
  Slack:   raw event['user'] — e.g. 'U01234ABC'
  Discord: str(message.author.id) — snowflake as string
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from asthralios.brain.db import BrainDB

Role = Literal['admin', 'user', 'blocked']
Platform = Literal['slack', 'discord']
Action = Literal['chat', 'brain_filed', 'brain_blocked', 'blocked',
                 'digest', 'notify', 'fix', 'clarification', 'admin_cmd']
Outcome = Literal['ok', 'denied', 'error', 'clarification_sent']


@dataclass
class UserIdentity:
    platform: Platform
    platform_user_id: str        # raw API ID — never a display name
    display_name: str = ''       # best-effort from platform; may be empty


@dataclass
class AccessContext:
    identity: UserIdentity
    role: Role
    channel: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RBACManager:
    """
    Resolves identity → role, enforces access, and logs every interaction.
    All methods are synchronous and safe to call from async handlers.
    """

    ROLE_ORDER = {'blocked': 0, 'user': 1, 'admin': 2}

    def __init__(self, db: 'BrainDB', config):
        self.db = db
        self.config = config
        self._seed_admins()

    def _seed_admins(self):
        """
        Ensure every admin ID from config is upserted with role='admin'.
        Safe to call repeatedly — upsert is idempotent.
        """
        rbac_cfg = getattr(self.config, 'rbac', {})
        admins = rbac_cfg.get('admins', {})
        for platform, ids in admins.items():
            if isinstance(ids, str):
                ids = [ids]
            for uid in ids:
                self.db.upsert_user(
                    platform=platform,
                    platform_user_id=uid,
                    display_name='(admin — configured)',
                    role='admin',
                    force_role=True,   # config always wins for admins
                )

    def resolve(self, identity: UserIdentity, channel: str, message: str) -> AccessContext:
        """
        Look up or create the user record. Returns an AccessContext with the
        resolved role. Updates last_seen and display_name on every call.
        """
        rbac_cfg = getattr(self.config, 'rbac', {})
        default_role: Role = rbac_cfg.get('default_role', 'user')

        role = self.db.get_or_create_user(
            platform=identity.platform,
            platform_user_id=identity.platform_user_id,
            display_name=identity.display_name,
            default_role=default_role,
        )
        return AccessContext(
            identity=identity,
            role=role,
            channel=channel,
            message=message,
        )

    def is_allowed(self, ctx: AccessContext, required_role: Role) -> bool:
        return self.ROLE_ORDER[ctx.role] >= self.ROLE_ORDER[required_role]

    def log_access(
        self,
        ctx: AccessContext,
        action: Action,
        outcome: Outcome,
        detail: Optional[str] = None,
    ):
        self.db.log_access(
            platform=ctx.identity.platform,
            platform_user_id=ctx.identity.platform_user_id,
            display_name=ctx.identity.display_name,
            role_at_time=ctx.role,
            channel=ctx.channel,
            message_preview=ctx.message[:200],
            action=action,
            outcome=outcome,
            detail=detail,
        )

    def set_role(self, platform: Platform, platform_user_id: str, role: Role):
        """Admin CLI — change a user's role."""
        self.db.set_user_role(platform, platform_user_id, role)

    def list_users(self) -> list:
        return self.db.list_users()
