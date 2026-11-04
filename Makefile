UV ?= uv
DOCKER_COMPOSE ?= docker compose -f apps/deploy/docker-compose.yml

.PHONY: help bootstrap doctor hygiene test-fast test-control-plane test-acquisition ui-check platform-model platform-model-check up down

help:
	@printf '%s\n' \
	  'bootstrap              Install the locked Python workspace' \
	  'doctor                 Check required local toolchains' \
	  'hygiene                Reject local/runtime files in the tracked tree' \
	  'test-fast              Run the hermetic platform suite' \
	  'test-control-plane     Run control-plane tests' \
	  'test-acquisition       Run acquisition tests' \
	  'ui-check               Build and test the React application' \
	  'platform-model         Regenerate source-derived architecture docs' \
	  'platform-model-check   Verify generated docs are current' \
	  'up / down              Start or stop the core local stack'

bootstrap:
	$(UV) sync --locked --all-packages --all-groups

doctor:
	@command -v uv >/dev/null || (echo 'uv is required' && exit 1)
	@command -v docker >/dev/null || (echo 'Docker is required for live-stack tasks' && exit 1)
	@command -v node >/dev/null || (echo 'Node.js 22+ is required for the webapp' && exit 1)
	@$(UV) --version
	@docker compose version
	@node --version

hygiene:
	$(UV) run python tools/repo_hygiene.py --check

test-fast:
	$(UV) run pytest apps -m 'not live' -q

test-control-plane:
	$(UV) run --project apps/control-plane pytest apps/control-plane/tests -q

test-acquisition:
	$(UV) run --project apps/acquisition pytest apps/acquisition/tests -q

ui-check:
	cd apps/webapp && npm ci && npm run build && npm test

platform-model:
	$(UV) run python -m platform_model.build

platform-model-check:
	$(UV) run python -m platform_model.build --check

up:
	$(DOCKER_COMPOSE) --profile core --profile analytics up -d

down:
	$(DOCKER_COMPOSE) down
