#!/bin/bash

if ! gifnoc check paperoni.services.paperoni-upload.enabled
then
    echo "Service paperoni-upload is disabled in the config"
    exit
fi

paperoni misc upload
