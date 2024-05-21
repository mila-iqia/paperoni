#!/bin/bash

if ! gifnoc check paperoni.services.paperoni-cleanup.enabled
then
    echo "Service paperoni-cleanup is disabled in the config"
    exit
fi

set -e

# TODO: clean up old history

CACHE_PATH=$(gifnoc dump paperoni.paths.cache)

echo Cleaning up $CACHE_PATH

# Clean up downloaded pdfs
find $CACHE_PATH -name '*.pdf' -delete
