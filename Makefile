# Versions come from versions.env, which is also valid make syntax
include versions.env

PYTHON?=python3
REMOTE?=origin
BRANCH?=main
Z3_TAG=z3-$(Z3_VERSION)-$(Z3_REVISION)

.PHONY: all build release clean

all: build

# Builds the z3 package for this platform into dist/
build:
	@$(PYTHON) build_z3.py

# Tags the current commit as z3-<Z3_VERSION>-<Z3_REVISION> and pushes the tag,
# which makes the CI build every platform and publish the release. The commit
# must already be on $(REMOTE)/$(BRANCH), so that the release is built from
# sources that the branch has too.
release:
	@test -z "$$(git status --porcelain)" || \
		{ echo "Error: the working tree has uncommitted changes"; exit 1; }
	@test "$$(git rev-parse --abbrev-ref HEAD)" = "$(BRANCH)" || \
		{ echo "Error: releases are made from $(BRANCH), not $$(git rev-parse --abbrev-ref HEAD)"; exit 1; }
	@git fetch --quiet --tags $(REMOTE) $(BRANCH) 2>/dev/null || \
		{ echo "Error: cannot fetch $(BRANCH) from $(REMOTE): push it first"; exit 1; }
	@test "$$(git rev-parse HEAD)" = "$$(git rev-parse $(REMOTE)/$(BRANCH))" || \
		{ echo "Error: HEAD is not $(REMOTE)/$(BRANCH): push or pull first"; exit 1; }
	@! git rev-parse --quiet --verify "refs/tags/$(Z3_TAG)" >/dev/null || \
		{ echo "Error: $(Z3_TAG) already exists: bump Z3_REVISION in versions.env"; exit 1; }
	@git tag -a "$(Z3_TAG)" -m "z3 $(Z3_VERSION), build revision $(Z3_REVISION)"
	@git push $(REMOTE) "refs/tags/$(Z3_TAG)"
	@echo "# Pushed $(Z3_TAG): the CI now builds and publishes the release"

clean:
	@rm -rf work dist
