#!/usr/bin/env python3
"""
Tests for BrainWriter.
"""

import pytest
from datetime import datetime
from pathlib import Path

import yaml

from asthralios.brain.writer import BrainWriter, _slugify
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


class TestBrainWriter:

    @pytest.fixture
    def vault(self, tmp_path):
        return BrainWriter(str(tmp_path))

    def test_creates_category_dirs(self, tmp_path):
        BrainWriter(str(tmp_path))
        for cat in ('people', 'projects', 'ideas', 'admin', 'musings'):
            assert (tmp_path / cat).is_dir()

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

        # Parse frontmatter
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

    def test_write_musings_uses_blob(self, vault, tmp_path):
        blob_text = "Just a random brain dump about nothing in particular."
        result = make_result(
            'musings',
            'Random brain dump',
            payload={'name': 'Random brain dump', 'blob': blob_text},
            raw_message='some original message',
        )
        path = vault.write(result, 'discord', 'markizano')
        content = Path(path).read_text()
        assert blob_text in content
        # musings should NOT have "## Original message" section
        assert '## Original message' not in content

    def test_write_people(self, vault):
        result = make_result(
            'people',
            'Follow up with Alice',
            next_action='Send proposal email',
            payload={'name': 'Alice', 'email': 'alice@example.com', 'labels': ['work']},
        )
        path = vault.write(result, 'slack', 'markizano')
        content = Path(path).read_text()
        fm_text = content.split('---')[1]
        fm = yaml.safe_load(fm_text)
        assert fm['email'] == 'alice@example.com'
        assert '## Original message' in content

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

    def test_collision_handling(self, vault, tmp_path):
        result = make_result('ideas', 'Test collision', payload={'name': 'Test collision'})
        path1 = vault.write(result, 'slack', 'user1')
        path2 = vault.write(result, 'slack', 'user1')
        assert path1 != path2
        assert Path(path1).exists()
        assert Path(path2).exists()

    def test_file_path_structure(self, vault, tmp_path):
        result = make_result('admin', 'Pay electric bill', payload={'name': 'Pay electric bill'})
        path = vault.write(result, 'slack', 'markizano')
        p = Path(path)
        assert p.parent == tmp_path / 'admin'
        assert p.name.startswith('2026-03-31-')
        assert p.suffix == '.md'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
