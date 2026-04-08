"""
BrainVault — writes ClassificationResult objects to the Obsidian vault.

File layout per category:
  {vault_path}/{category}/{YYYY-MM-DD}-{slug}.md          (primary)
  {vault_path}/{category}/{YYYY-MM-DD-HHMMSS}-{slug}.md   (collision)

People entries also produce:
  {vault_path}/people/{base}.vcf

Category index files (one per category, at vault root):
  {vault_path}/MUSINGS.md
  {vault_path}/PEOPLE.md
  {vault_path}/PROJECTS.md
  {vault_path}/IDEAS.md
  {vault_path}/ADMIN.md
"""
import re
from pathlib import Path

import vobject
import yaml

from asthralios.brain import NOTE_CATEGORIES, schema
from asthralios import getLogger

log = getLogger(__name__)

INDEX_FILES = {cat: cat.upper() + '.md' for cat in NOTE_CATEGORIES}


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:60]


class BrainVault:

    def __init__(self, vault_path: str):
        self.vault = Path(vault_path)
        for cat in NOTE_CATEGORIES:
            (self.vault / cat).mkdir(parents=True, exist_ok=True)
        for index_file in INDEX_FILES.values():
            index_path = self.vault / index_file
            if not index_path.exists():
                index_path.write_text('', encoding='utf-8')

    def write(self, result: schema.ClassificationResult, source_platform: str, source_user: str) -> str:
        """File a classified entry and update the category index. Returns the primary file path."""
        date_str = result.classified_at.strftime('%Y-%m-%d')
        slug = _slugify(result.name)
        base = self._resolve_base(result.category, date_str, slug, result.classified_at)

        filed_path = self._write_content(result, base, source_platform, source_user)
        self._update_index(result, base)
        log.info(f'Brain: wrote {filed_path}')
        return filed_path

    # ── Private helpers ────────────────────────────────────────────────────────

    def _resolve_base(self, category: str, date_str: str, slug: str, classified_at) -> str:
        """Return a collision-free base filename (no extension)."""
        base = f'{date_str}-{slug}'
        if (self.vault / category / f'{base}.md').exists():
            ts = classified_at.strftime('%H%M%S')
            base = f'{date_str}-{ts}-{slug}'
        return base

    def _write_content(self, result: schema.ClassificationResult, base: str, source_platform: str, source_user: str) -> str:
        """Dispatch to the appropriate writer. Returns primary file path."""
        if result.category == 'people':
            self._write_vcf(result, base)
            return self._write_people_md(result, base, source_platform, source_user)
        return self._write_note(result, base, source_platform, source_user)

    def _write_note(self, result: schema.ClassificationResult, base: str, source_platform: str, source_user: str) -> str:
        """Write a standard Markdown note for non-people categories."""
        filepath = self.vault / result.category / f'{base}.md'

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
        for k, v in result.payload.items():
            if k not in frontmatter and v is not None:
                frontmatter[k] = v

        body_lines = [f'# {result.name}', '']
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
        filepath.write_text(f'---\n{fm_str}---\n\n' + '\n'.join(body_lines) + '\n', encoding='utf-8')
        return str(filepath)

    def _write_vcf(self, result: schema.ClassificationResult, base: str) -> str:
        """Write a vCard file for a People entry."""
        payload = result.payload
        full_name = payload.get('name', result.name)
        parts = full_name.rsplit(' ', 1)
        given = parts[0] if len(parts) == 2 else full_name
        family = parts[1] if len(parts) == 2 else ''

        card = vobject.vCard()
        card.add('fn').value = full_name
        n = card.add('n')
        n.value = vobject.vcard.Name(family=family, given=given)

        extra = payload.get('extra', {})
        if extra.get('title'):
            card.add('title').value = extra['title']
        if extra.get('org'):
            card.add('org').value = [extra['org']]
        if payload.get('phone'):
            tel = card.add('tel')
            tel.type_param = 'WORK,VOICE'
            tel.value = payload['phone']
        if payload.get('email'):
            email_obj = card.add('email')
            email_obj.type_param = 'WORK'
            email_obj.value = payload['email']

        filepath = self.vault / 'people' / f'{base}.vcf'
        filepath.write_text(card.serialize(), encoding='utf-8')
        return str(filepath)

    def _write_people_md(self, result: schema.ClassificationResult, base: str, source_platform: str, source_user: str) -> str:
        """Write a Markdown companion for a People entry."""
        payload = result.payload
        name = payload.get('name', result.name)

        frontmatter = {
            'classification': 'people',
            'confidence': round(result.confidence, 3),
            'name': name,
            'next_action': result.next_action,
            'created': result.classified_at.isoformat(),
            'source': source_platform,
            'source_user': source_user,
            'tags': ['people'],
            'vcf_file': f'{base}.vcf',
        }
        for k, v in payload.items():
            if k not in frontmatter and v is not None:
                frontmatter[k] = v

        body_lines = [f'# {name}', '', f'[Contact Card](./{base}.vcf)', '', result.raw_message]
        if result.next_action:
            body_lines += ['', f'**Next action:** {result.next_action}']

        fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        filepath = self.vault / 'people' / f'{base}.md'
        filepath.write_text(f'---\n{fm_str}---\n\n' + '\n'.join(body_lines) + '\n', encoding='utf-8')
        return str(filepath)

    def _update_index(self, result: schema.ClassificationResult, base: str) -> None:
        """Append one index line to the category index file, unless already present."""
        index_path = self.vault / INDEX_FILES[result.category]
        existing = index_path.read_text(encoding='utf-8')

        if base in existing:
            return

        payload = result.payload
        category = result.category

        if category == 'musings':
            summary = payload.get('summary') or result.name
            line = f'[[{base}|{result.name}]]: {summary}'
        elif category == 'people':
            name = payload.get('name', result.name)
            extra = payload.get('extra', {})
            title = extra.get('title', '')
            org = extra.get('org', '')
            descriptor = ' from '.join(part for part in (title, org) if part)
            line = f'[[{base}|{name}]] - {descriptor}' if descriptor else f'[[{base}|{name}]]'
        elif category == 'projects':
            priority = payload.get('priority', '')
            summary = payload.get('summary', '')
            parts = [f'{priority} priority' if priority else '', summary]
            descriptor = ' - '.join(p for p in parts if p)
            line = f'[[{base}|{result.name}]] - {descriptor}' if descriptor else f'[[{base}|{result.name}]]'
        elif category == 'ideas':
            premise = payload.get('premise', '')
            line = f'[[{base}|{result.name}]] - {premise}' if premise else f'[[{base}|{result.name}]]'
        elif category == 'admin':
            due = payload.get('due', '')
            line = f'[[{base}|{result.name}]] - due: {due}' if due else f'[[{base}|{result.name}]]'
        else:
            line = f'[[{base}|{result.name}]]'

        separator = '\n' if existing and not existing.endswith('\n') else ''
        index_path.write_text(existing + separator + line + '\n', encoding='utf-8')
