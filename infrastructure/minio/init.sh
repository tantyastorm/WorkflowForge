#!/bin/sh
set -eu

mc alias set workflowforge "$WORKFLOWFORGE_S3_ENDPOINT_URL" "$WORKFLOWFORGE_S3_ACCESS_KEY" "$WORKFLOWFORGE_S3_SECRET_KEY"
mc mb --ignore-existing "workflowforge/$WORKFLOWFORGE_S3_BUCKET"
mc ls "workflowforge/$WORKFLOWFORGE_S3_BUCKET" >/dev/null
