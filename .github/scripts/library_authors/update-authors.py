import glob
import json
import os
import subprocess
import sys


def run_git_command(command):
    """ Run a git command and return the output. """
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    result.check_returncode()  # Raise an error if the command fails
    return result.stdout.strip()


def get_commits_affected_directory(directory: str) -> list:
    """ Get a list of commits that affected the given directory, including renames. """
    command = f"git log --follow --format='%H' -- '{directory}'"
    commits = run_git_command(command)
    return commits.splitlines()


def get_commit_author(commit_hash: str) -> str:
    """ Get the author of a given commit. """
    command = f"git show -s --format='%an <%ae>' {commit_hash}"
    author = run_git_command(command)
    return author


def find_first_commit_author(file: str, check_paths: bool = True) -> str | None:
    """ Find the first commit that affected the directory and return the author's name. """
    commits = get_commits_affected_directory(file)
    for commit in reversed(commits):  # Process commits from the oldest to newest
        command = f"git diff-tree --no-commit-id --name-only -r {commit}"
        if not check_paths:
            return get_commit_author(commit)

        affected_files = run_git_command(command)
        paths = [
            file.replace("profile_library", "custom_components/powercalc/data"),
            file.replace("profile_library", "data"),
            file
        ]
        if any(path in affected_files.splitlines() for path in paths):
            author = get_commit_author(commit)
            return author
    return None


def process_model_json_files(root_dir):
    # Find all model.json files in the directory tree
    model_json_files = glob.glob(os.path.join(root_dir, '**', 'model.json'), recursive=True)

    for model_json_file in model_json_files:
        # Skip sub profiles
        if model_json_file.count("/") != 3:
            continue

        author = read_author_from_file(os.path.abspath(model_json_file))
        if author:
            print(f"Skipping {model_json_file}, author already set to {author}")
            continue

        author = find_first_commit_author(model_json_file)
        if author is None:
            print(f"Skipping {model_json_file}, author not found")
            continue

        write_author_to_file(os.path.abspath(model_json_file), author)
        print(f"Updated {model_json_file} with author {author}")


def read_author_from_file(file_path: str) -> str | None:
    """Read the author from the model.json file."""
    with open(file_path, "r") as file:
        json_data = json.load(file)

    return json_data.get("author")


def write_author_to_file(file_path: str, author: str) -> None:
    """Write the author to the model.json file."""
    # Read the existing content
    with open(file_path, "r") as file:
        json_data = json.load(file)

    json_data["author"] = author

    with open(file_path, "w") as file:
        json.dump(json_data, file, indent=2)


def main():
    try:
        process_model_json_files("profile_library")
    except subprocess.CalledProcessError as e:
        print(f"Error running git command: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
