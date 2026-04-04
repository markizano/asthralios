"""
Digest generation and delivery.

CLI entry points call `run_digest(config, 'daily'|'weekly')`.
`run_digest` builds the context, calls the LLM, and delivers to the configured
platform(s) via the proactive send mechanism.
"""

from datetime import date

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from asthralios import getLogger
from asthralios.brain.db import BrainDB
from asthralios.brain.prompts import (
    DAILY_DIGEST_SYSTEM, DAILY_DIGEST_USER,
    WEEKLY_DIGEST_SYSTEM, WEEKLY_DIGEST_USER,
)

log = getLogger(__name__)


def _rows_to_text(rows) -> str:
    if not rows:
        return '(none)'
    lines = []
    for r in rows:
        line = f'- {r["name"] or "(unnamed)"}'
        if r['confidence']:
            line += f' [{r["category"]}]'
        lines.append(line)
    return '\n'.join(lines)


def generate_daily(db: BrainDB, llm) -> str:
    projects = db.get_active_projects()
    people   = db.get_pending_people()
    admin    = db.get_open_admin()
    total    = len(projects) + len(people) + len(admin)

    user_msg = DAILY_DIGEST_USER.format(
        date=date.today().strftime('%A, %B %d %Y'),
        projects=_rows_to_text(projects),
        people=_rows_to_text(people),
        admin=_rows_to_text(admin),
    )
    resp = llm.invoke([
        SystemMessage(content=DAILY_DIGEST_SYSTEM),
        HumanMessage(content=user_msg),
    ])
    db.log_digest('daily', total)
    return resp.content.strip()


def generate_weekly(db: BrainDB, llm) -> str:
    inbox_rows = db.get_past_week()
    projects   = db.get_active_projects()

    inbox_text    = _rows_to_text(inbox_rows)
    projects_text = _rows_to_text(projects)

    user_msg = WEEKLY_DIGEST_USER.format(
        date=date.today().strftime('%A, %B %d %Y'),
        inbox_log=inbox_text,
        projects=projects_text,
    )
    resp = llm.invoke([
        SystemMessage(content=WEEKLY_DIGEST_SYSTEM),
        HumanMessage(content=user_msg),
    ])
    db.log_digest('weekly', len(inbox_rows))
    return resp.content.strip()


def run_digest(config, digest_type: str) -> str:
    """
    Entry point for CLI. Returns the digest text (and caller can deliver it).
    digest_type: 'daily' or 'weekly'
    """
    db_path  = config.brain.db_path
    model    = config.brain.get('model', config.get('model', 'gpt-oss:20b'))
    provider = config.brain.get('provider', 'ollama')

    db  = BrainDB(db_path)
    llm = init_chat_model(model=model, model_provider=provider)

    if digest_type == 'daily':
        return generate_daily(db, llm)
    elif digest_type == 'weekly':
        return generate_weekly(db, llm)
    else:
        raise ValueError(f'Unknown digest_type: {digest_type}')
