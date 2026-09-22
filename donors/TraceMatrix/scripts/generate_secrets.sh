#!/usr/bin/env bash
set -euo pipefail

# Generate secrets for .env (Unix/WSL)

searx_secret=$(openssl rand -hex 32)
admin_pass=$(openssl rand -base64 24 | tr -d '\n' | tr -dc 'A-Za-z0-9!@#%^&*()_+-=')

cat <<EOF
# Add these to your .env
SEARXNG_SECRET_KEY=$searx_secret
OPENSEARCH_INITIAL_ADMIN_PASSWORD=$admin_pass
EOF

