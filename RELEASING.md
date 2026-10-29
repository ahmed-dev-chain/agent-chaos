# Releasing to PyPI

Published as **`agent-chaos-toolkit`** on PyPI (`agent-chaos` was already taken by an unrelated
project) — the import name (`import agent_chaos`) and the CLI command (`chaos`) are unaffected.

`.github/workflows/release.yml` builds and publishes automatically whenever a tag matching `v*`
is pushed, using [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OpenID
Connect) — no API token is ever stored as a GitHub secret.

## One-time setup (do this before the first release)

Needs a PyPI account (create one at <https://pypi.org/account/register/> if you don't have one).

1. Go to <https://pypi.org/manage/account/publishing/> while logged in.
2. Add a new **pending publisher** (this works even though the project hasn't been published yet):
   - **PyPI project name**: `agent-chaos-toolkit`
   - **Owner**: `ahmed-dev-chain`
   - **Repository name**: `agent-chaos`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
3. Save it. The first push of a `v*` tag will create the project on PyPI automatically.

Optional but recommended: in the GitHub repo's Settings → Environments, create an environment
named `pypi` and add a required reviewer, so every publish needs a manual approval click before
it goes out — a safety net against an accidental tag push.

## Cutting a release

1. Bump the version in **both** `pyproject.toml`'s `version` and `src/agent_chaos/__init__.py`'s
   `__version__` (they must match).
2. Update `docs/ROADMAP.md`/`README.md` if the release closes out a milestone.
3. Commit, then tag and push:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
4. Watch the `release` workflow in the Actions tab. Once `publish` succeeds,
   `pip install agent-chaos-toolkit` / `pipx install agent-chaos-toolkit` picks it up within
   minutes.

A tag push is the only thing that triggers a publish — pushing commits to `master` alone never
does.
