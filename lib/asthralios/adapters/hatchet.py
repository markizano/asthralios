
from asthralios import config, getLogger
import github
import tempfile
import os
import requests
from typing import List, Dict, Optional, Generator, Union

log = getLogger(__name__)

class Hatchet:
    """
    Comprehensive GitHub API integration class for workflow management and log fetching.
    Handles authentication, repository listing, workflow operations, and log retrieval.
    """

    def __init__(self, org: str):
        """
        Initialize Hatchet with GitHub organization authentication.

        Args:
            org (str): GitHub organization name
        """
        # Get config instance and check for access token
        self.config = config.getInstance()
        if not self.config.github.access_token:
            raise ValueError("GitHub access token not configured")

        try:
            auth = github.Auth.Token(self.config.github.access_token)
            self.github = github.Github(auth=auth)
            self.org = self.github.get_organization(org)
            log.info(f"Successfully authenticated to GitHub organization: {org}")
        except Exception as e:
            log.error(f"Failed to authenticate to GitHub or access organization: {e}")
            raise

    def get_repos(self, visibility: str = "all") -> List[Dict]:
        """
        Get list of repositories in the organization.

        Args:
            visibility (str): Repository visibility filter ('all', 'public', 'private')

        Returns:
            List[Dict]: List of repository information dictionaries
        """
        try:
            repos = []
            for repo in self.org.get_repos(type=visibility):
                repo_info = {
                    'id': repo.id,
                    'name': repo.name,
                    'full_name': repo.full_name,
                    'private': repo.private,
                    'description': repo.description,
                    'html_url': repo.html_url,
                    'clone_url': repo.clone_url,
                    'default_branch': repo.default_branch,
                    'language': repo.language,
                    'archived': repo.archived,
                    'disabled': repo.disabled,
                    'created_at': repo.created_at.isoformat() if repo.created_at else None,
                    'updated_at': repo.updated_at.isoformat() if repo.updated_at else None,
                    'pushed_at': repo.pushed_at.isoformat() if repo.pushed_at else None
                }
                repos.append(repo_info)

            log.info(f"Retrieved {len(repos)} repositories from organization")
            return repos

        except github.GithubException as e:
            log.error(f"Failed to retrieve repositories: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error retrieving repositories: {e}")
            raise

    def get_workflows(self, repo_name: str) -> List[Dict]:
        """
        Get list of workflow runs for a specific repository.

        Args:
            repo_name (str): Name of the repository

        Returns:
            List[Dict]: List of workflow run information
        """
        try:
            repo = self.org.get_repo(repo_name)
            workflows = repo.get_workflows()

            workflow_list = []
            for workflow in workflows:
                workflow_info = {
                    'id': workflow.id,
                    'name': workflow.name,
                    'path': workflow.path,
                    'state': workflow.state,
                    'created_at': workflow.created_at.isoformat() if workflow.created_at else None,
                    'updated_at': workflow.updated_at.isoformat() if workflow.updated_at else None,
                    'url': workflow.url
                }
                workflow_list.append(workflow_info)

            log.info(f"Retrieved {len(workflow_list)} workflows from repository: {repo_name}")
            return workflow_list

        except github.GithubException as e:
            log.error(f"Failed to retrieve workflows for {repo_name}: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error retrieving workflows for {repo_name}: {e}")
            raise

    def get_workflow_runs(self, repo_name: str, workflow_id: Optional[int] = None,
                          status: str = "all", branch: Optional[str] = None,
                          limit: int = 30) -> List[Dict]:
        """
        Get list of workflow runs for a specific repository and optionally a specific workflow.

        Args:
            repo_name (str): Name of the repository
            workflow_id (int, optional): Specific workflow ID to filter by
            status (str): Filter by run status ('all', 'completed', 'action_required', 'cancelled', 'failure', 'neutral', 'skipped', 'stale', 'success', 'timed_out', 'in_progress', 'queued', 'requested', 'waiting')
            branch (str, optional): Filter by branch name
            limit (int): Maximum number of runs to return

        Returns:
            List[Dict]: List of workflow run information
        """
        try:
            repo = self.org.get_repo(repo_name)

            if workflow_id:
                workflow = repo.get_workflow(workflow_id)
                runs = workflow.get_runs(status=status, per_page=limit)
            else:
                runs = repo.get_workflow_runs(status=status, per_page=limit)

            # Apply branch filter if specified
            if branch:
                runs = [run for run in runs if run.head_branch == branch]

            runs_list = []
            for run in runs:
                run_info = {
                    'id': run.id,
                    'run_number': run.run_number,
                    'name': run.name,
                    'head_branch': run.head_branch,
                    'head_sha': run.head_sha,
                    'status': run.status,
                    'conclusion': run.conclusion,
                    'created_at': run.created_at.isoformat() if run.created_at else None,
                    'updated_at': run.updated_at.isoformat() if run.updated_at else None,
                    'started_at': run.started_at.isoformat() if run.started_at else None,
                    'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                    'workflow_id': run.workflow_id,
                    'html_url': run.html_url,
                    'logs_url': run.logs_url,
                    'check_suite_id': run.check_suite_id,
                    'actor': run.actor.login if run.actor else None
                }
                runs_list.append(run_info)

            log.info(f"Retrieved {len(runs_list)} workflow runs from repository: {repo_name}")
            return runs_list

        except github.GithubException as e:
            log.error(f"Failed to retrieve workflow runs for {repo_name}: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error retrieving workflow runs for {repo_name}: {e}")
            raise

    def get_workflow_status(self, repo_name: str, run_id: int) -> Dict:
        """
        Get detailed status information for a specific workflow run.

        Args:
            repo_name (str): Name of the repository
            run_id (int): Workflow run ID

        Returns:
            Dict: Detailed workflow run status information
        """
        try:
            repo = self.org.get_repo(repo_name)
            run = repo.get_workflow_run(run_id)

            # Get jobs for this run
            jobs = run.get_jobs()
            jobs_list = []
            for job in jobs:
                job_info = {
                    'id': job.id,
                    'name': job.name,
                    'status': job.status,
                    'conclusion': job.conclusion,
                    'started_at': job.started_at.isoformat() if job.started_at else None,
                    'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                    'steps': [
                        {
                            'name': step.name,
                            'status': step.status,
                            'conclusion': step.conclusion,
                            'started_at': step.started_at.isoformat() if step.started_at else None,
                            'completed_at': step.completed_at.isoformat() if step.completed_at else None
                        }
                        for step in job.get_steps()
                    ]
                }
                jobs_list.append(job_info)

            status_info = {
                'id': run.id,
                'run_number': run.run_number,
                'name': run.name,
                'head_branch': run.head_branch,
                'head_sha': run.head_sha,
                'status': run.status,
                'conclusion': run.conclusion,
                'created_at': run.created_at.isoformat() if run.created_at else None,
                'updated_at': run.updated_at.isoformat() if run.updated_at else None,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'completed_at': run.completed_at.isoformat() if run.completed_at else None,
                'workflow_id': run.workflow_id,
                'html_url': run.html_url,
                'logs_url': run.logs_url,
                'check_suite_id': run.check_suite_id,
                'actor': run.actor.login if run.actor else None,
                'jobs': jobs_list,
                'total_jobs': len(jobs_list),
                'completed_jobs': len([j for j in jobs_list if j['status'] == 'completed']),
                'failed_jobs': len([j for j in jobs_list if j['conclusion'] == 'failure'])
            }

            log.info(f"Retrieved status for workflow run {run_id} from repository: {repo_name}")
            return status_info

        except github.GithubException as e:
            log.error(f"Failed to retrieve workflow status for run {run_id} in {repo_name}: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error retrieving workflow status for run {run_id} in {repo_name}: {e}")
            raise

    def get_workflow_logs(self, repo_name: str, run_id: int,
                          output_format: str = "file") -> Union[str, Generator[str, None, None]]:
        """
        Get workflow logs for a specific run. Can return either a file path or stream the logs.

        Args:
            repo_name (str): Name of the repository
            run_id (int): Workflow run ID
            output_format (str): Output format - 'file' for temp file path, 'stream' for generator

        Returns:
            Union[str, Generator[str, None, None]]: Either file path or log stream generator
        """
        try:
            repo = self.org.get_repo(repo_name)
            run = repo.get_workflow_run(run_id)

            if output_format == "file":
                return self._download_logs_to_file(run)
            elif output_format == "stream":
                return self._stream_logs(run)
            else:
                raise ValueError("output_format must be either 'file' or 'stream'")

        except github.GithubException as e:
            log.error(f"Failed to retrieve workflow logs for run {run_id} in {repo_name}: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error retrieving workflow logs for run {run_id} in {repo_name}: {e}")
            raise

    def _download_logs_to_file(self, run) -> str:
        """
        Download workflow logs to a temporary file.

        Args:
            run: GitHub workflow run object

        Returns:
            str: Path to the temporary file containing the logs
        """
        try:
            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                prefix=f'github_workflow_logs_{run.id}_',
                delete=False
            )
            temp_file_path = temp_file.name
            temp_file.close()

            # Download logs using the logs URL
            logs_url = run.logs_url
            headers = {'Authorization': f'token {self.config.github.access_token}'}

            response = requests.get(logs_url, headers=headers, stream=True)
            response.raise_for_status()

            with open(temp_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            log.info(f"Downloaded workflow logs to temporary file: {temp_file_path}")
            return temp_file_path

        except requests.RequestException as e:
            log.error(f"Failed to download logs: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error downloading logs: {e}")
            raise

    def _stream_logs(self, run) -> Generator[str, None, None]:
        """
        Stream workflow logs as a generator.

        Args:
            run: GitHub workflow run object

        Yields:
            str: Log content chunks
        """
        try:
            logs_url = run.logs_url
            headers = {'Authorization': f'token {self.config.github.access_token}'}

            response = requests.get(logs_url, headers=headers, stream=True)
            response.raise_for_status()

            for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
                if chunk:
                    yield chunk

        except requests.RequestException as e:
            log.error(f"Failed to stream logs: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error streaming logs: {e}")
            raise

    def cleanup_temp_file(self, file_path: str) -> None:
        """
        Clean up temporary log files.

        Args:
            file_path (str): Path to the temporary file to delete
        """
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                log.info(f"Cleaned up temporary file: {file_path}")
        except Exception as e:
            log.warning(f"Failed to cleanup temporary file {file_path}: {e}")

    def __del__(self):
        """Cleanup method to ensure proper resource cleanup."""
        try:
            if hasattr(self, 'github'):
                self.github.close()
        except Exception as e:
            log.warning(f"Error during cleanup: {e}")
