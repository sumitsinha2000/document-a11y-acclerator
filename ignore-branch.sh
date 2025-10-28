#!/bin/bash

# Get the current branch name
BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "Current branch: $BRANCH"

# Ignore builds from the "fixes" branch
if [ "$BRANCH" = "fixes" ]; then
  echo "🛑 Build cancelled - ignoring branch: $BRANCH"
  exit 1
else
  echo "✅ Proceeding with build for branch: $BRANCH"
  exit 0
fi
