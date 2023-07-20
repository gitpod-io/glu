#!/usr/bin/env bash

cat ${GITPOD_REPO_ROOT:-.}/ProdBotConfig.toml | base64 -w0 | gh variable -R gitpod-io/glu set CONFIG_BASE64
gh workflow run deploy.yaml -R gitpod-io/glu