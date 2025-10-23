import git
import os
from tqdm import tqdm

def clone_or_pull_repo(repo_url: str, local_path: str):
    """Clones a repository if it doesn't exist, otherwise pulls latest changes."""
    if not os.path.exists(local_path): 
        print(f"Cloning repository from {repo_url} to {local_path}...")
        try:
            git.Repo.clone_from(repo_url, local_path)
            print("Repository cloned successfully.")
        except git.GitCommandError as e:
            print(f"Error cloning repository: {e}")
            raise
    else:
        print(f"Repository already exists at {local_path}. Pulling latest changes...")
        try:
            repo = git.Repo(local_path)
            repo.remotes.origin.pull()
            print("Repository updated.")
        except git.GitCommandError as e:
            print(f"Error pulling latest changes: {e}")
            raise

