#!/bin/sh
# Start (or update) the self-hosted Onyx that formform retrieves context from.
#   ./up.sh              start        FORMFORM_SMALL=1 ./up.sh   8 GB trial
#   ./up.sh down         stop         ./up.sh logs -f api_server  any docker compose subcommand
set -eu
cd "$(dirname "$0")"
export FORMFORM_SERVER_DIR="$PWD"
ONYX_REPO=https://github.com/onyx-dot-app/onyx

if [ ! -f .env ]; then
  umask 077
  secret() { openssl rand -hex "$1"; }
  sed -e "s/^USER_AUTH_SECRET=$/USER_AUTH_SECRET=$(secret 32)/" \
      -e "s/^ENCRYPTION_KEY_SECRET=$/ENCRYPTION_KEY_SECRET=$(secret 32)/" \
      -e "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$(secret 16)/" \
      -e "s/^OPENSEARCH_ADMIN_PASSWORD=$/OPENSEARCH_ADMIN_PASSWORD=Aa1-$(secret 16)/" env.template > .env
  echo "Created server/.env with generated secrets."
fi
TAG=$(sed -n 's/^IMAGE_TAG=//p' .env)

# Onyx's compose file and nginx templates come from the pinned tag; the source is not vendored here.
if [ "$(git -C .onyx describe --tags --exact-match 2>/dev/null || true)" != "$TAG" ]; then
  rm -rf .onyx
  git clone --quiet --depth 1 --branch "$TAG" "$ONYX_REPO" .onyx
fi
ln -sf "$PWD/.env" .onyx/deployment/docker_compose/.env

set -- "${@:-up}"
[ "$1" = up ] && set -- "$@" -d
exec docker compose --env-file .env \
  -f .onyx/deployment/docker_compose/docker-compose.yml \
  -f docker-compose.formform.yml \
  ${FORMFORM_SMALL:+-f docker-compose.small.yml} "$@"
