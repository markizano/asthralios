'''
Command line interface for Asthralios.
This is the main entrypoint for the application.
'''

from dotenv import load_dotenv
load_dotenv()

import kizano
import asthralios

import os, sys
import argparse
from signal import signal, SIGINT


def digest_action(config):
    """Run daily or weekly digest and optionally deliver to Slack/Discord."""
    from asthralios.brain.digest import run_digest
    from asthralios.brain import BrainDB
    from asthralios.brain.rbac import RBACManager

    digest_type = 'daily' if config.get('daily') else 'weekly'
    text = run_digest(config, digest_type)
    print(text)

    # Log CLI digest action to access_log for audit trail
    db = BrainDB(config.brain.db_path)
    db.log_access(
        platform='system',
        platform_user_id='cli',
        display_name='cli',
        role_at_time='admin',
        channel='cli',
        message_preview=f'{digest_type} digest',
        action='digest',
        outcome='ok',
        detail=f'type={digest_type}',
    )

    if config.get('deliver_slack'):
        from asthralios.chat.my_slack import send_slack_message
        send_slack_message(config, config['deliver_slack'], text)
    if config.get('deliver_discord'):
        import asyncio
        from asthralios.chat.my_discord import send_discord_message
        asyncio.run(send_discord_message(config, config['deliver_discord'], text))
    return 0


def notify_action(config):
    """Send an arbitrary message to Slack or Discord."""
    from asthralios.brain import BrainDB

    target_channel = config.get('slack') or config.get('discord') or ''
    db = BrainDB(config.brain.db_path)
    db.log_access(
        platform='system',
        platform_user_id='cli',
        display_name='cli',
        role_at_time='admin',
        channel=target_channel,
        message_preview=(config.get('message') or '')[:200],
        action='notify',
        outcome='ok',
        detail=f'target={target_channel}',
    )

    if config.get('slack'):
        from asthralios.chat.my_slack import send_slack_message
        send_slack_message(config, config['slack'], config.get('message', ''))
    elif config.get('discord'):
        import asyncio
        from asthralios.chat.my_discord import send_discord_message
        asyncio.run(send_discord_message(config, config['discord'], config.get('message', '')))
    return 0


def users_action(config):
    """Manage RBAC users."""
    from asthralios.brain import BrainDB
    from asthralios.brain.rbac import RBACManager

    db   = BrainDB(config.brain.db_path)
    rbac = RBACManager(db, config)

    users_action_name = config.get('users_action')

    if users_action_name == 'list':
        rows = rbac.list_users()
        if not rows:
            print('No users recorded yet.')
        for r in rows:
            print(
                f"[{r['role']:8s}] {r['platform']:8s} {r['platform_user_id']:20s}  "
                f"{r['display_name'] or '(no name)':30s}  last: {r['last_seen'][:10]}"
            )

    elif users_action_name == 'set-role':
        rbac.set_role(config['platform'], config['user_id'], config['role'])
        print(f"Set {config['platform']}/{config['user_id']} \u2192 {config['role']}")

    elif users_action_name == 'log':
        rows = db.get_access_log(
            limit=config.get('limit') or 50,
            platform_user_id=config.get('user_id') or None,
        )
        for r in rows:
            print(
                f"{r['logged_at'][:19]}  [{r['role_at_time']:8s}]  "
                f"{r['platform']:8s}  {r['platform_user_id']:20s}  "
                f"{r['action']:15s}  {r['outcome']:20s}  "
                f"{(r['detail'] or '')[:40]}"
            )
    return 0


class Cli:

    ACTIONS = {
        'converse': asthralios.senses.conversate,
        'ingest': asthralios.senses.ingest,
        'chat': asthralios.chat.start_chat,
        'agent': asthralios.chat.start_agent,
        'sentinel': asthralios.sentinel.check_code_quality,
        'digest': digest_action,
        'notify': notify_action,
        'users': users_action,
    }

    def __init__(self):
        self.log = asthralios.logger.getLogger(__name__)
        signal(SIGINT, lambda code, frame: self.interrupt(code, frame))

    def interrupt(self, sig, frame):
        sys.stderr.write('Caught ^C interrupt, exiting...\n')
        sys.stderr.flush()
        sys.exit(sig)

    def getCmd(self):
        '''
        '''
        cfg = kizano.getConfig()
        opts = self.getOptions()
        # Command line takes precedence over config.
        for name, value in opts.items():
            cfg.config[name] = value
        self.log.info("Asthralios is waking up...")
        action = cfg.config.get('action', 'converse')
        cmd = Cli.ACTIONS[action]
        return (cmd, cfg.config)

    def getOptions(self) -> dict:
        '''
        Parse command line options using subparsers for each action.
        '''
        options = argparse.ArgumentParser(
            description="Asthralios - Markizano's Assistant",
            formatter_class=argparse.RawTextHelpFormatter
        )
        options.add_argument(
            '--log-level', metavar='log_level', type=str, default='INFO',
            help='Verbosity of the logger', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        )

        subparsers = options.add_subparsers(dest='action', metavar='command')

        # converse
        converse_parser = subparsers.add_parser('converse', help='Start a voice conversation.')
        converse_parser.add_argument('--language', type=str, default='en', help='Language to send to the model.')
        converse_parser.add_argument('--model', type=str, default='gpt-oss:20b', help='Model to use for the conversation.')
        converse_parser.add_argument('--model-provider', type=str, default='ollama', help='Model provider to use.')

        # ingest
        ingest_parser = subparsers.add_parser('ingest', help='Ingest documents into the knowledge base.')
        ingest_parser.add_argument('--path', type=str, default='.', help='Path to the documents to ingest.')

        # chat
        chat_parser = subparsers.add_parser('chat', help='Start a chat interface.')
        chat_parser.add_argument('--model', type=str, default='gpt-oss:20b', help='Model to use for the chat.')
        chat_parser.add_argument('--model-provider', type=str, default='ollama', help='Model provider to use.')

        # agent
        agent_parser = subparsers.add_parser('agent', help='Start the agentic workflow.')
        agent_parser.add_argument('--model', type=str, default='gpt-oss:20b', help='Model to use for the agent.')
        agent_parser.add_argument('--model-provider', type=str, default='ollama', help='Model provider to use.')

        # sentinel
        sentinel_parser = subparsers.add_parser('sentinel', help='Run code quality analysis.')
        sentinel_parser.add_argument('--path', type=str, default='.', help='Path to the codebase to check.')
        sentinel_parser.add_argument('--output', '-o', type=str, default='-', help="Where to write output.")
        sentinel_parser.add_argument('--model', type=str, default='gpt-oss:20b', help='Model to use for analysis.')
        sentinel_parser.add_argument('--model-provider', type=str, default='ollama', help='Model provider to use.')

        # digest
        digest_parser = subparsers.add_parser('digest', help='Generate daily or weekly brain digest.')
        digest_parser.add_argument('--daily', action='store_true', default=False, help='Generate daily digest.')
        digest_parser.add_argument('--weekly', action='store_true', default=False, help='Generate weekly digest.')
        digest_parser.add_argument('--deliver-slack', metavar='CHANNEL', type=str, default=None,
                                   help='Deliver digest to Slack channel.')
        digest_parser.add_argument('--deliver-discord', metavar='CHANNEL_ID', type=str, default=None,
                                   help='Deliver digest to Discord channel ID.')

        # notify
        notify_parser = subparsers.add_parser('notify', help='Send a message to Slack or Discord.')
        notify_parser.add_argument('--slack', metavar='CHANNEL', type=str, default=None,
                                   help='Send message to Slack channel.')
        notify_parser.add_argument('--discord', metavar='CHANNEL_ID', type=str, default=None,
                                   help='Send message to Discord channel ID.')
        notify_parser.add_argument('message', nargs='?', default=None, help='Message text.')

        # users
        users_parser = subparsers.add_parser('users', help='Manage RBAC users and access log.')
        users_sub = users_parser.add_subparsers(dest='users_action', metavar='subcommand')

        users_sub.add_parser('list', help='List all known users and their roles.')

        set_role_parser = users_sub.add_parser('set-role', help='Change a user\'s role.')
        set_role_parser.add_argument('--platform', required=True, choices=['slack', 'discord'],
                                     help='Platform (slack or discord).')
        set_role_parser.add_argument('--user-id', dest='user_id', required=True,
                                     help='Raw platform user ID (e.g. U01234ABC for Slack).')
        set_role_parser.add_argument('--role', required=True, choices=['admin', 'user', 'blocked'],
                                     help='Role to assign.')

        log_parser = users_sub.add_parser('log', help='Show access log entries.')
        log_parser.add_argument('--user-id', dest='user_id', type=str, default=None,
                                help='Filter by platform user ID.')
        log_parser.add_argument('--limit', type=int, default=50, help='Max entries to show.')

        opts = options.parse_args()

        if 'LOG_LEVEL' not in os.environ:
            os.environ['LOG_LEVEL'] = opts.log_level
            self.log.setLevel(opts.log_level)

        if not opts.action:
            self.log.error('No action specified!')
            options.print_help()
            raise SystemExit(8)

        return opts.__dict__
