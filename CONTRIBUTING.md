# Contributing to AxonX

English · [简体中文](CONTRIBUTING_ZH.md)

We welcome bug reports, feature requests, documentation improvements, research plugins, and code contributions.

## Before you start

Search [existing issues](https://github.com/FlowLLM-AI/AxonX/issues) and related code. For bugs, include reproduction steps, expected and actual behavior, environment versions, and relevant logs with credentials removed. For features, explain the research or development problem and the desired behavior.

For changes to public CLI/API/configuration contracts, persisted task records, or task lifecycle behavior, discuss the design in an issue before a large implementation. Keep each PR focused on one coherent problem.

## Find the right area

| Location | Responsibility |
| --- | --- |
| `axonx/` | Application composition, Components, Jobs, CLI, service, and Task runtime |
| `plugins/` | Research Tasks, algorithms, plugin manifests, and plugin tests |
| `axonx_studio/` | Browser UI, API client, task forms, and research charts |
| `tests/` | Framework unit and integration tests |
| `docs/en/`, `docs/zh/`, `docs/figures/` | Bilingual guides and shared screenshots/diagrams |
| `docs/.vitepress/`, `github-pages/` | Documentation theme and site build tooling |

See the [Task development guide](https://flowllm-ai.github.io/AxonX/en/dev_guide), [framework extensions](https://flowllm-ai.github.io/AxonX/en/development/framework-extensions), and [plugin manifest](https://flowllm-ai.github.io/AxonX/en/reference/plugin-manifest) for implementation contracts.

## Development setup

Fork the repository and clone your fork. From its root, use Python 3.12+ on macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

For research plugin development, install the relevant plugin in editable mode:

```bash
axonx plugin install -e ./plugins/a158
# Or: axonx plugin install -e ./plugins/a158_enhanced
```

The default pytest configuration includes enhanced-plugin tests and both plugin source paths. Install the research dependencies above when running those tests. See the [plugin guide](https://flowllm-ai.github.io/AxonX/en/guides/plugin-management) for discovery and restart behavior.

For Studio, use Node.js 22.13+ (22.x), 24.x, or 26+, and run:

```bash
cd axonx_studio
npm ci
npm run dev
```

Start the Python service separately as described in the [quick start](https://flowllm-ai.github.io/AxonX/en/getting-started/quickstart). See [Studio development](https://flowllm-ai.github.io/AxonX/en/development/studio) for proxy configuration. The documentation site requires Node.js 22+.

## Making a change

Reuse existing contracts and extension points. Keep research algorithms in Tasks/plugins, and preserve ownership and cleanup of asynchronous resources in the framework. Document intentional changes to CLI flags, API responses, configuration, task identity, and artifact formats.

Use temporary workspaces for tests. Do not commit `.env`, tokens, private data, runtime `.axonx/` contents, logs, or generated outputs. Ensure screenshots contain no credentials or private session content.

## Validation

Choose checks for the affected area and state the commands and results in your PR. For Python or plugin changes, run relevant tests first, then the non-integration suite as appropriate:

```bash
pytest tests/unit/<affected_test_file>.py
pytest
pre-commit run --all-files
```

Bare `pytest` excludes tests marked `integration`. Run `pytest -m integration` only with the required credentials and services available, after reviewing the tests' external effects. Explain any checks you could not run.

For Studio changes, run from `axonx_studio/`:

```bash
npm run test
npm run lint
npm run format:check
npm run build
```

Check relevant UI flows in English and Chinese, including empty data and request failures.

For documentation or theme changes, run from `github-pages/`:

```bash
npm ci
npm run build
```

The build verifies rendered pages and Markdown exports. For root README/contribution-guide changes, check local links, documentation routes, and example commands; those files are not rendered by the documentation build.

## Documentation contributions

Edit canonical sources under `docs/`, and update corresponding English and Chinese guides together. Keep matching paths and shared assets under `docs/figures/`. Site navigation is defined in `docs/.vitepress/navigation.ts`.

Do not edit `github-pages/.generated/` or `github-pages/dist/`; they are regenerated. For site development and deployment details, see [github-pages/README.md](github-pages/README.md). Keep the two root READMEs and contribution guides aligned when their instructions change.

## Submitting a pull request

Use a descriptive title; Conventional Commits such as `fix(tasks): preserve run status` or `docs: clarify quick start` are encouraged. Explain the problem, resulting behavior, compatibility impact, and validation. Include screenshots for visible UI changes and note any external-service tests that were skipped.

Contributions are covered by the project's [Apache License 2.0](LICENSE).

## Releases

AxonX and Studio release independently. Commit version updates and pass the relevant CI before tagging. Integration tests require model API keys and run locally when needed.

- **AxonX**: synchronize `pyproject.toml` and `axonx/_version.py`, then create and push `v<version>`. Publishing a GitHub Release for that tag automatically publishes `axonx` to PyPI. Alternatively, run `Release / AxonX Python package` manually with the version without `v`.
- **Studio**: synchronize `axonx_studio/pyproject.toml`, `package.json`, and `package-lock.json`, then create and push `studio-v<version>`. Run `Release / AxonX Studio` manually. The default `both` publishes PyPI before npm; `pypi` and `npm` publish independently. The npm tag is selected automatically: `latest` for stable versions and `next` for prereleases.

Every release builds from its tag and verifies distribution versions. Studio's Python and npm packages contain identical static assets; Python prerelease metadata is normalized according to PEP 440. The AxonX release does not publish research plugins.

Configure PyPI Trusted Publishers for `axonx` and `axonx-studio` with their respective workflows and the `pypi` environment. Configure npm Trusted Publishing for `@flowllm-ai/axonx-studio` with `release-axonx-studio.yml` and the `npm` environment. A new npm package needs its initial publication before Trusted Publishing can be configured.

Existing versions fail publication rather than being overwritten or silently skipped. If npm fails during a dual release, publish `npm` alone from the same tag. Do not move release tags.
