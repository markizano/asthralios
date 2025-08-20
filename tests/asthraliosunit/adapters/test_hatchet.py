#!/usr/bin/env python3
"""
Example usage of the Hatchet class for GitHub workflow management and log fetching.
This demonstrates all the main functionality of the Hatchet class.
"""

from asthralios.adapters.hatchet import Hatchet
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)

def main():
    """Example usage of the Hatchet class."""
    
    # Replace with your actual GitHub organization name
    org_name = "your-org-name"
    
    try:
        # Initialize Hatchet with your organization
        hatchet = Hatchet(org_name)
        print(f"✅ Successfully connected to GitHub organization: {org_name}")
        
        # Example 1: Get all repositories
        print("\n📚 Getting repositories...")
        repos = hatchet.get_repos()
        print(f"Found {len(repos)} repositories:")
        for repo in repos[:5]:  # Show first 5 repos
            print(f"  - {repo['name']} ({repo['language'] or 'No language'})")
        
        if repos:
            # Use the first repository for workflow examples
            first_repo = repos[0]['name']
            print(f"\n🔧 Using repository '{first_repo}' for workflow examples...")
            
            # Example 2: Get workflows for the repository
            print("\n📋 Getting workflows...")
            workflows = hatchet.get_workflows(first_repo)
            print(f"Found {len(workflows)} workflows:")
            for workflow in workflows:
                print(f"  - {workflow['name']} (ID: {workflow['id']}, State: {workflow['state']})")
            
            # Example 3: Get workflow runs
            print("\n🏃 Getting recent workflow runs...")
            runs = hatchet.get_workflow_runs(first_repo, limit=5)
            print(f"Found {len(runs)} recent runs:")
            for run in runs:
                print(f"  - Run #{run['run_number']}: {run['name']} - {run['status']} ({run['conclusion'] or 'pending'})")
            
            if runs:
                # Use the first run for detailed examples
                first_run = runs[0]
                run_id = first_run['id']
                
                # Example 4: Get detailed workflow status
                print(f"\n📊 Getting detailed status for run #{first_run['run_number']}...")
                status = hatchet.get_workflow_status(first_repo, run_id)
                print(f"Run Status: {status['status']}")
                print(f"Conclusion: {status['conclusion'] or 'pending'}")
                print(f"Jobs: {status['total_jobs']} total, {status['completed_jobs']} completed, {status['failed_jobs']} failed")
                
                # Example 5: Get workflow logs (download to file)
                print(f"\n📥 Downloading logs for run #{first_run['run_number']}...")
                log_file_path = hatchet.get_workflow_logs(first_repo, run_id, output_format="file")
                print(f"Logs downloaded to: {log_file_path}")
                
                # Example 6: Stream logs (alternative approach)
                print(f"\n📖 Streaming logs for run #{first_run['run_number']}...")
                log_stream = hatchet.get_workflow_logs(first_repo, run_id, output_format="stream")
                
                # Read first few lines from stream
                line_count = 0
                for line in log_stream:
                    if line_count < 5:  # Show first 5 lines
                        print(f"  {line.strip()}")
                        line_count += 1
                    else:
                        break
                
                # Clean up the temporary file
                print(f"\n🧹 Cleaning up temporary log file...")
                hatchet.cleanup_temp_file(log_file_path)
                print("✅ Cleanup completed")
        
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("Make sure you have set up your GitHub access token in the config file.")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Check your GitHub access token and organization name.")

if __name__ == "__main__":
    main()
