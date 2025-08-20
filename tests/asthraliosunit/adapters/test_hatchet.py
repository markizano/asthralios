#!/usr/bin/env python3
"""
Pytest test cases for the Hatchet class - GitHub workflow management and log fetching.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from asthralios.adapters.hatchet import Hatchet


class TestHatchet:
    """Test cases for the Hatchet class."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration with GitHub access token."""
        mock_cfg = Mock()
        mock_cfg.github.access_token = "test_token_12345"
        return mock_cfg

    @pytest.fixture
    def mock_github_org(self):
        """Mock GitHub organization."""
        mock_org = Mock()
        mock_org.name = "test-org"
        return mock_org

    @pytest.fixture
    def mock_github_client(self):
        """Mock GitHub client."""
        mock_client = Mock()
        mock_client.get_organization.return_value = Mock()
        return mock_client

    @pytest.fixture
    def hatchet_instance(self, mock_config, mock_github_client):
        """Create a Hatchet instance with mocked dependencies."""
        with patch('asthralios.adapters.hatchet.config') as mock_config_module:
            mock_config_module.getInstance.return_value = mock_config

            with patch('asthralios.adapters.hatchet.github') as mock_github_module:
                mock_auth = Mock()
                mock_github_module.Auth.Token.return_value = mock_auth
                mock_github_module.Github.return_value = mock_github_client

                # Mock successful authentication
                mock_github_client.get_user_info.return_value = {'displayName': 'Test User'}

                hatchet = Hatchet("test-org")
                return hatchet

    def test_initialization_success(self, mock_config):
        """Test successful Hatchet initialization."""
        with patch('asthralios.adapters.hatchet.config') as mock_config_module:
            mock_config_module.getInstance.return_value = mock_config

            with patch('asthralios.adapters.hatchet.github') as mock_github_module:
                mock_auth = Mock()
                mock_github_module.Auth.Token.return_value = mock_auth

                mock_github_client = Mock()
                mock_github_client.get_user_info.return_value = {'displayName': 'Test User'}
                mock_github_module.Github.return_value = mock_github_client

                hatchet = Hatchet("test-org")
                assert hatchet.org is not None
                assert hatchet.github is not None

    def test_initialization_missing_token(self):
        """Test initialization fails when access token is missing."""
        with patch('asthralios.adapters.hatchet.config') as mock_config_module:
            mock_cfg = Mock()
            mock_cfg.github.access_token = None
            mock_config_module.getInstance.return_value = mock_cfg

            with pytest.raises(ValueError, match="GitHub access token not configured"):
                Hatchet("test-org")

    def test_initialization_authentication_failure(self, mock_config):
        """Test initialization fails when GitHub authentication fails."""
        with patch('asthralios.adapters.hatchet.config') as mock_config_module:
            mock_config_module.getInstance.return_value = mock_config

            with patch('asthralios.adapters.hatchet.github') as mock_github_module:
                mock_auth = Mock()
                mock_github_module.Auth.Token.return_value = mock_auth

                mock_github_client = Mock()
                # Mock the get_organization method to fail, which is what Hatchet actually calls
                mock_github_client.get_organization.side_effect = Exception("Auth failed")
                mock_github_module.Github.return_value = mock_github_client

                with pytest.raises(Exception, match="Auth failed"):
                    Hatchet("test-org")

    def test_get_repos_success(self, hatchet_instance):
        """Test successful repository retrieval."""
        # Mock repository data
        mock_repo = Mock()
        mock_repo.id = 123
        mock_repo.name = "test-repo"
        mock_repo.full_name = "test-org/test-repo"
        mock_repo.private = False
        mock_repo.description = "Test repository"
        mock_repo.html_url = "https://github.com/test-org/test-repo"
        mock_repo.clone_url = "https://github.com/test-org/test-repo.git"
        mock_repo.default_branch = "main"
        mock_repo.language = "Python"
        mock_repo.archived = False
        mock_repo.disabled = False
        mock_repo.created_at = Mock()
        mock_repo.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_repo.updated_at = Mock()
        mock_repo.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_repo.pushed_at = Mock()
        mock_repo.pushed_at.isoformat.return_value = "2024-01-01T00:00:00"

        # Mock space object
        mock_space = Mock()
        mock_space.key = "TEST"
        mock_space.name = "Test Space"
        mock_repo.space = mock_space

        # Mock version object
        mock_version = Mock()
        mock_version.number = 1
        mock_repo.version = mock_version

        # Mock author object
        mock_author = Mock()
        mock_author.displayName = "Test Author"
        mock_repo.author = mock_author

        # Mock links
        mock_links = Mock()
        mock_links.webui = "/spaces/TEST/pages/123"
        mock_links.content = "/rest/api/content/123"
        mock_repo._links = mock_links

        # Mock expandable
        mock_expandable = {}
        mock_repo._expandable = mock_expandable

        hatchet_instance.org.get_repos.return_value = [mock_repo]

        repos = list(hatchet_instance.get_repos())

        assert len(repos) == 1
        repo = repos[0]
        assert repo['id'] == 123
        assert repo['name'] == "test-repo"
        assert repo['full_name'] == "test-org/test-repo"
        assert repo['private'] is False
        assert repo['language'] == "Python"

    def test_get_repos_with_visibility_filter(self, hatchet_instance):
        """Test repository retrieval with visibility filter."""
        hatchet_instance.org.get_repos.return_value = []

        list(hatchet_instance.get_repos(visibility="public"))

        hatchet_instance.org.get_repos.assert_called_with(type="public")

    def test_get_workflows_success(self, hatchet_instance):
        """Test successful workflow retrieval."""
        # Mock workflow data
        mock_workflow = Mock()
        mock_workflow.id = 456
        mock_workflow.name = "CI/CD Pipeline"
        mock_workflow.path = ".github/workflows/ci.yml"
        mock_workflow.state = "active"
        mock_workflow.created_at = Mock()
        mock_workflow.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_workflow.updated_at = Mock()
        mock_workflow.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_workflow.url = "https://api.github.com/workflows/456"

        mock_repo = Mock()
        mock_repo.get_workflows.return_value = [mock_workflow]

        hatchet_instance.org.get_repo.return_value = mock_repo

        workflows = hatchet_instance.get_workflows("test-repo")

        assert len(workflows) == 1
        workflow = workflows[0]
        assert workflow['id'] == 456
        assert workflow['name'] == "CI/CD Pipeline"
        assert workflow['state'] == "active"

    def test_get_workflow_runs_success(self, hatchet_instance):
        """Test successful workflow run retrieval."""
        # Mock workflow run data
        mock_run = Mock()
        mock_run.id = 789
        mock_run.run_number = 42
        mock_run.name = "CI/CD Pipeline"
        mock_run.head_branch = "main"
        mock_run.head_sha = "abc123"
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.updated_at = Mock()
        mock_run.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.started_at = Mock()
        mock_run.started_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.completed_at = Mock()
        mock_run.completed_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.workflow_id = 456
        mock_run.html_url = "https://github.com/test-org/test-repo/actions/runs/789"
        mock_run.logs_url = "https://api.github.com/repos/test-org/test-repo/actions/runs/789/logs"
        mock_run.check_suite_id = 123
        mock_run.actor = Mock()
        mock_run.actor.login = "test-user"

        mock_repo = Mock()
        mock_repo.get_workflow_runs.return_value = [mock_run]

        hatchet_instance.org.get_repo.return_value = mock_repo

        runs = hatchet_instance.get_workflow_runs("test-repo", limit=10)

        assert len(runs) == 1
        run = runs[0]
        assert run['id'] == 789
        assert run['run_number'] == 42
        assert run['status'] == "completed"
        assert run['conclusion'] == "success"

    def test_get_workflow_runs_with_filters(self, hatchet_instance):
        """Test workflow run retrieval with various filters."""
        mock_repo = Mock()
        mock_repo.get_workflow_runs.return_value = []

        hatchet_instance.org.get_repo.return_value = mock_repo

        # Test with status filter
        list(hatchet_instance.get_workflow_runs("test-repo", status="failure"))
        mock_repo.get_workflow_runs.assert_called_with(status="failure", per_page=30)

        # Test with custom limit
        list(hatchet_instance.get_workflow_runs("test-repo", limit=50))
        mock_repo.get_workflow_runs.assert_called_with(status="all", per_page=50)

    def test_get_workflow_status_success(self, hatchet_instance):
        """Test successful workflow status retrieval."""
        # Mock workflow run
        mock_run = Mock()
        mock_run.id = 789
        mock_run.run_number = 42
        mock_run.name = "CI/CD Pipeline"
        mock_run.head_branch = "main"
        mock_run.head_sha = "abc123"
        mock_run.status = "completed"
        mock_run.conclusion = "success"
        mock_run.created_at = Mock()
        mock_run.created_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.updated_at = Mock()
        mock_run.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.started_at = Mock()
        mock_run.started_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.completed_at = Mock()
        mock_run.completed_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_run.workflow_id = 456
        mock_run.html_url = "https://github.com/test-org/test-repo/actions/runs/789"
        mock_run.logs_url = "https://api.github.com/repos/test-org/test-repo/actions/runs/789/logs"
        mock_run.check_suite_id = 123
        mock_run.actor = Mock()
        mock_run.actor.login = "test-user"

        # Mock job
        mock_job = Mock()
        mock_job.id = 101
        mock_job.name = "Build and Test"
        mock_job.status = "completed"
        mock_job.conclusion = "success"
        mock_job.started_at = Mock()
        mock_job.started_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_job.completed_at = Mock()
        mock_job.completed_at.isoformat.return_value = "2024-01-01T00:00:00"

        # Mock step
        mock_step = Mock()
        mock_step.name = "Run tests"
        mock_step.status = "completed"
        mock_step.conclusion = "success"
        mock_step.started_at = Mock()
        mock_step.started_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_step.completed_at = Mock()
        mock_step.completed_at.isoformat.return_value = "2024-01-01T00:00:00"

        mock_job.get_steps.return_value = [mock_step]
        mock_run.get_jobs.return_value = [mock_job]

        mock_repo = Mock()
        mock_repo.get_workflow_run.return_value = mock_run

        hatchet_instance.org.get_repo.return_value = mock_repo

        status = hatchet_instance.get_workflow_status("test-repo", 789)

        assert status['id'] == 789
        assert status['status'] == "completed"
        assert status['conclusion'] == "success"
        assert status['total_jobs'] == 1
        assert status['completed_jobs'] == 1
        assert status['failed_jobs'] == 0
        assert len(status['jobs']) == 1
        assert status['jobs'][0]['name'] == "Build and Test"

    @patch('asthralios.adapters.hatchet.requests.get')
    def test_get_workflow_logs_file_format(self, mock_requests_get, hatchet_instance):
        """Test workflow log retrieval in file format."""
        # Mock workflow run
        mock_run = Mock()
        mock_run.id = 789
        mock_run.logs_url = "https://api.github.com/repos/test-org/test-repo/actions/runs/789/logs"

        mock_repo = Mock()
        mock_repo.get_workflow_run.return_value = mock_run

        hatchet_instance.org.get_repo.return_value = mock_repo

        # Mock requests response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = [b"log line 1\n", b"log line 2\n"]
        mock_requests_get.return_value = mock_response

        # Mock tempfile
        with patch('asthralios.adapters.hatchet.tempfile.NamedTemporaryFile') as mock_tempfile:
            mock_temp = Mock()
            mock_temp.name = "/tmp/test_logs.txt"
            mock_tempfile.return_value = mock_temp

            log_file_path = hatchet_instance.get_workflow_logs("test-repo", 789, output_format="file")

            assert log_file_path == "/tmp/test_logs.txt"
            mock_requests_get.assert_called_once()

    @patch('asthralios.adapters.hatchet.requests.get')
    def test_get_workflow_logs_stream_format(self, mock_requests_get, hatchet_instance):
        """Test workflow log retrieval in stream format."""
        # Mock workflow run
        mock_run = Mock()
        mock_run.id = 789
        mock_run.logs_url = "https://api.github.com/repos/test-org/test-repo/actions/runs/789/logs"

        mock_repo = Mock()
        mock_repo.get_workflow_run.return_value = mock_run

        hatchet_instance.org.get_repo.return_value = mock_repo

        # Mock requests response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_content.return_value = ["log line 1\n", "log line 2\n"]
        mock_requests_get.return_value = mock_response

        log_stream = hatchet_instance.get_workflow_logs("test-repo", 789, output_format="stream")

        log_lines = list(log_stream)
        assert len(log_lines) == 2
        assert log_lines[0] == "log line 1\n"
        assert log_lines[1] == "log line 2\n"

    def test_get_workflow_logs_invalid_format(self, hatchet_instance):
        """Test workflow log retrieval with invalid output format."""
        mock_repo = Mock()
        hatchet_instance.org.get_repo.return_value = mock_repo

        with pytest.raises(ValueError, match="output_format must be either 'file' or 'stream'"):
            hatchet_instance.get_workflow_logs("test-repo", 789, output_format="invalid")

    def test_cleanup_temp_file_success(self, hatchet_instance):
        """Test successful temporary file cleanup."""
        with patch('os.path.exists') as mock_exists, patch('os.unlink') as mock_unlink:
            mock_exists.return_value = True

            hatchet_instance.cleanup_temp_file("/tmp/test_file.txt")

            mock_exists.assert_called_with("/tmp/test_file.txt")
            mock_unlink.assert_called_with("/tmp/test_file.txt")

    def test_cleanup_temp_file_not_exists(self, hatchet_instance):
        """Test cleanup when file doesn't exist."""
        with patch('os.path.exists') as mock_exists, patch('os.unlink') as mock_unlink:
            mock_exists.return_value = False

            hatchet_instance.cleanup_temp_file("/tmp/nonexistent.txt")

            mock_exists.assert_called_with("/tmp/nonexistent.txt")
            mock_unlink.assert_not_called()

    def test_cleanup_temp_file_error(self, hatchet_instance):
        """Test cleanup handles errors gracefully."""
        with patch('os.path.exists') as mock_exists, patch('os.unlink') as mock_unlink:
            mock_exists.return_value = True
            mock_unlink.side_effect = Exception("Permission denied")

            # Should not raise exception
            hatchet_instance.cleanup_temp_file("/tmp/test_file.txt")

            mock_exists.assert_called_with("/tmp/test_file.txt")
            mock_unlink.assert_called_with("/tmp/test_file.txt")


if __name__ == "__main__":
    pytest.main([__file__])
