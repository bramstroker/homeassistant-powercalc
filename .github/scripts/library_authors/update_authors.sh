#!/bin/bash

# Ensure the directory is specified
if [ -z "$1" ]; then
  echo "Usage: $0 <directory>"
  exit 1
fi

directory=$1

# Get the list of commits that affected the directory, including renames
commits=$(git log --follow --format="%H" -- $directory)

# Iterate through the commits in reverse order (oldest first)
for commit in $(echo "$commits" | tac); do
  # Check if the directory was affected by this commit
  if git diff-tree --no-commit-id --name-only -r $commit | grep -q "^$directory"; then
    # Get the author of the first commit that affected the directory
    author=$(git show -s --format="%an <%ae>" $commit)
    echo "First commit author for directory $directory: $author"
    exit 0
  fi
done

echo "No commits found for directory $directory"
