"""
BrainWriter — writes ClassificationResult objects to Markdown files with YAML frontmatter.

File layout:
  {vault_path}/{category}/{YYYY-MM-DD}-{slug}.md

YAML frontmatter fields present on every file:
  classification, confidence, name, next_action, created, source, source_user, tags

Additional fields from payload are merged in.
"""
import os
import re
from pathlib import Path

import yaml  # pyyaml

from asthralios.brain import NOTE_CATEGORIES, schema
from asthralios import getLogger

log = getLogger(__name__)


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:60]

class BrainWriter:

    def __init__(self, vault_path: str):
        self.vault = Path(vault_path)
        # Ensure category subdirectories exist
        for cat in NOTE_CATEGORIES:
            cat_path = os.path.join(vault_path, cat)
            if not os.path.exists(cat_path):
                os.makedirs(cat_path, exists_ok=True)

    def write(
        self,
        result: schema.ClassificationResult,
        source_platform: str,
        source_user: str,
    ) -> str:
        """
        Write a classified entry. Returns the absolute path of the written file.
        """
        date_str = result.classified_at.strftime('%Y-%m-%d')
        slug = _slugify(result.name)
        filename = f'{date_str}-{slug}.md'
        filepath = os.path.join(self.vault, result.category, filename)

        # Handle filename collisions
        if os.path.exists(filepath):
            ts = result.classified_at.strftime('%H%M%S')
            filename = f'{date_str}-{ts}-{slug}.md'
            filepath = os.path.join(self.vault, result.category, filename)

        frontmatter = {
            'classification': result.category,
            'confidence': round(result.confidence, 3),
            'name': result.name,
            'next_action': result.next_action,
            'created': result.classified_at.isoformat(),
            'source': source_platform,
            'source_user': source_user,
            'tags': [result.category],
        }

        # Merge category-specific payload fields into frontmatter
        for k, v in result.payload.items():
            if k not in frontmatter and v is not None:
                frontmatter[k] = v

        body_lines = [f'# {result.name}', '']

        # Category-aware body section
        if result.category == 'musings':
            body_lines.append(result.payload.get('blob', result.raw_message))
        else:
            if result.payload.get('description'):
                body_lines.append(result.payload['description'])
                body_lines.append('')
            if result.next_action:
                body_lines.append(f'**Next action:** {result.next_action}')
                body_lines.append('')
            body_lines.append('## Original message')
            body_lines.append('')
            body_lines.append(f'> {result.raw_message}')

        fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        content = f'---\n{fm_str}---\n\n' + '\n'.join(body_lines) + '\n'

        open(filepath, 'w', encoding='utf-8').write(content)
        log.info(f'Brain: wrote {filepath}')
        return filepath
