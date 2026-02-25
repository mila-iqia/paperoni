#!/bin/bash

# Exit on error
set -e

_PROJECT_ROOT=$(git rev-parse --show-toplevel)

cd "$_PROJECT_ROOT/tests/refinement/"

cd tests/refinement/

find data/ -path "*/prompt/*" -type f -name "gemini-2.5-pro_*_0000" | while read f
do
  dir=$(dirname "$f")
  new_f=$(ls -t "$_PROJECT_ROOT/$dir/" | head -n 1)
  cp "$_PROJECT_ROOT/$dir/$new_f" "$f" 
done
