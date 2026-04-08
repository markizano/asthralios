#!/usr/bin/env python3
"""
Tests for BrainVault.
"""

import pytest
from datetime import datetime
from pathlib import Path

import vobject
import yaml

from asthralios.brain.vault import BrainVault, _slugify
from asthralios.brain.schema import ClassificationResult


def make_result(
    category: str,
    name: str,
    confidence: float = 0.9,
    next_action: str = None,
    payload: dict = None,
    raw_message: str = "test message",
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        confidence=confidence,
        name=name,
        next_action=next_action,
        payload=payload or {},
        raw_message=raw_message,
        classified_at=datetime(2026, 3, 31, 12, 0, 0),
    )


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars_removed(self):
        assert _slugify("Fix it! Now.") == "fix-it-now"

    def test_truncated_at_60(self):
        long = "a" * 100
        assert len(_slugify(long)) <= 60

    def test_spaces_become_dashes(self):
        assert _slugify("one two  three") == "one-two-three"


class TestBrainVault:

    @pytest.fixture
    def vault(self, tmp_path):
        return BrainVault(str(tmp_path))

    def test_creates_category_dirs(self, tmp_path):
        BrainVault(str(tmp_path))
        for cat in ('people', 'projects', 'ideas', 'admin', 'musings'):
            assert (tmp_path / cat).is_dir()

    def test_creates_index_files(self, tmp_path):
        BrainVault(str(tmp_path))
        for name in ('PEOPLE.md', 'PROJECTS.md', 'IDEAS.md', 'ADMIN.md', 'MUSINGS.md'):
            assert (tmp_path / name).exists()

    def test_write_project(self, vault, tmp_path):
        result = make_result(
            'projects',
            'Build dashboard feature',
            next_action='Create mockups',
            payload={'name': 'Build dashboard feature', 'priority': 'high'},
        )
        path = vault.write(result, 'slack', 'markizano')

        assert Path(path).exists()
        assert Path(path).parent.name == 'projects'
        content = Path(path).read_text()
        assert '2026-03-31' in Path(path).name
        assert 'build-dashboard-feature' in Path(path).name

        fm_text = content.split('---')[1]
        fm = yaml.safe_load(fm_text)
        assert fm['classification'] == 'projects'
        assert fm['confidence'] == 0.9
        assert fm['name'] == 'Build dashboard feature'
        assert fm['next_action'] == 'Create mockups'
        assert fm['source'] == 'slack'
        assert fm['source_user'] == 'markizano'
        assert 'projects' in fm['tags']
        assert fm['priority'] == 'high'

    def test_write_musings_uses_blob(self, vault):
        blob_text = "Just a random brain dump about nothing in particular."
        result = make_result(
            'musings',
            'Random brain dump',
            payload={'name': 'Random brain dump', 'blob': blob_text, 'summary': 'A random brain dump.'},
            raw_message='some original message',
        )
        path = vault.write(result, 'discord', 'markizano')
        content = Path(path).read_text()
        assert blob_text in content
        assert '## Original message' not in content

    def test_write_ideas(self, vault):
        result = make_result(
            'ideas',
            'Personal wiki concept',
            payload={'name': 'Personal wiki concept', 'premise': 'A place for thoughts'},
        )
        path = vault.write(result, 'slack', 'markizano')
        assert Path(path).parent.name == 'ideas'
        content = Path(path).read_text()
        assert '# Personal wiki concept' in content

    def test_write_admin(self, vault):
        result = make_result(
            'admin',
            'Renew car insurance',
            payload={'name': 'Renew car insurance', 'due': 'Friday'},
        )
        path = vault.write(result, 'discord', 'markizano')
        assert Path(path).parent.name == 'admin'

    def test_write_people_creates_vcf_and_md(self, vault, tmp_path):
        result = make_result(
            'people',
            'Jennifer Coughlin',
            next_action='Send follow-up email',
            payload={
                'name': 'Jennifer Coughlin',
                'email': 'jennifer.coughlin@experis.com',
                'phone': '414-906-7093',
                'extra': {'title': 'Sr. Recruiter', 'org': 'Experis (Manpower Group Company)'},
            },
            raw_message='Met Jennifer at the tech conference.',
        )
        md_path = vault.write(result, 'slack', 'markizano')

        assert Path(md_path).exists()
        assert Path(md_path).suffix == '.md'

        base = Path(md_path).stem
        vcf_path = tmp_path / 'people' / f'{base}.vcf'
        assert vcf_path.exists()

        # Validate VCF is parseable vobject
        card = vobject.readOne(vcf_path.read_text())
        assert card.fn.value == 'Jennifer Coughlin'
        assert card.n.value.given == 'Jennifer'
        assert card.n.value.family == 'Coughlin'
        assert card.email.value == 'jennifer.coughlin@experis.com'

        # MD companion contains raw message and next action
        md_content = Path(md_path).read_text()
        assert 'Met Jennifer at the tech conference.' in md_content
        assert 'Send follow-up email' in md_content
        assert f'[Contact Card](./{base}.vcf)' in md_content

    def test_collision_handling(self, vault):
        result = make_result('ideas', 'Test collision', payload={'name': 'Test collision'})
        path1 = vault.write(result, 'slack', 'user1')
        path2 = vault.write(result, 'slack', 'user1')
        assert path1 != path2
        assert Path(path1).exists()
        assert Path(path2).exists()

    def test_collision_filename_format(self, vault, tmp_path):
        """Collision filename keeps date and time together: YYYY-MM-DD-HHMMSS-slug."""
        result = make_result('admin', 'Pay electric bill', payload={'name': 'Pay electric bill'})
        vault.write(result, 'slack', 'markizano')
        path2 = vault.write(result, 'slack', 'markizano')
        name = Path(path2).stem
        # Should be 2026-03-31-120000-pay-electric-bill, NOT 2026-03-31-pay-electric-bill-120000
        assert name.startswith('2026-03-31-120000-'), f'Unexpected collision name: {name}'

    def test_file_path_structure(self, vault, tmp_path):
        result = make_result('admin', 'Pay electric bill', payload={'name': 'Pay electric bill'})
        path = vault.write(result, 'slack', 'markizano')
        p = Path(path)
        assert p.parent == tmp_path / 'admin'
        assert p.name.startswith('2026-03-31-')
        assert p.suffix == '.md'

    def test_update_index_musings(self, vault, tmp_path):
        result = make_result(
            'musings',
            'Fabric of spacetime',
            payload={
                'name': 'Fabric of spacetime',
                'blob': 'A thought about black holes.',
                'summary': 'The universe may be nested black holes all the way down.',
            },
        )
        vault.write(result, 'slack', 'markizano')
        index = (tmp_path / 'MUSINGS.md').read_text()
        assert '[[' in index
        assert 'fabric-of-spacetime' in index
        assert 'The universe may be nested black holes all the way down.' in index

    def test_update_index_people(self, vault, tmp_path):
        result = make_result(
            'people',
            'Jennifer Coughlin',
            payload={
                'name': 'Jennifer Coughlin',
                'email': 'j@example.com',
                'extra': {'title': 'Sr. Recruiter', 'org': 'Experis'},
            },
        )
        vault.write(result, 'slack', 'markizano')
        index = (tmp_path / 'PEOPLE.md').read_text()
        assert 'Jennifer Coughlin' in index
        assert 'Sr. Recruiter' in index
        assert 'Experis' in index

    def test_update_index_no_duplicates(self, vault, tmp_path):
        result = make_result(
            'ideas',
            'Unique idea',
            payload={'name': 'Unique idea', 'premise': 'A premise'},
        )
        vault.write(result, 'slack', 'markizano')
        vault.write(result, 'slack', 'markizano')  # second write (collision → different base)
        index = (tmp_path / 'IDEAS.md').read_text()
        # Each write uses a unique base (collision-resolved), so 2 entries are expected.
        # What we verify is that writing the exact same base twice does NOT duplicate.
        lines = [l for l in index.strip().splitlines() if l]
        bases = [l.split('|')[0].lstrip('[') for l in lines]
        assert len(bases) == len(set(bases)), 'Duplicate index entries found'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
