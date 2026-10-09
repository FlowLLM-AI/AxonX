# Contributing to AxonX

English · [简体中文](CONTRIBUTING_ZH.md)

We welcome bug reports, feature requests, documentation improvements, research plugins, and code contributions.

## Before you start

Search [existing issues](https://github.com/FlowLLM-AI/AxonX/issues) and related code. For bugs, include reproduction steps, expected and actual behavior, environment versions, and relevant logs with credentials removed. For features, explain the research or development problem and the desired behavior.

Use the bug report, feature request, or usage question form, or a free-form issue for other topics. For bugs, distinguish reproduced failures, intermittent observations, and static-analysis suspicions; identify the affected area and local or remote target. Share sanitized excerpts rather than the entire `.axonx/` workspace.

For changes to public CLI/API/configuration contracts, persisted task records, or task lifecycle behavior, discuss the design in an issue before a large implementation. Keep each PR focused on one coherent problem.

## Find the right area

| Location                                          | Responsibility                                                            |
| ------------------------------------------------- | ------------------------------------------------------------------------- |
| `axonx/`                                          | Application composition, Components, Jobs, CLI, service, and Task runtime |
| `plugins/`                                        | Research Tasks, algorithms, plugin manifests, and plugin tests            |
| `axonx_studio/`                                   | Browser UI, API client, task forms, and research charts                   |
| `tests/`                                          | Framework unit and integration tests                                      |
| `docs/en/`, `docs/zh/`, `docs/figures/`           | Bilingual guides and shared screenshots/diagrams                          |
| `docs/.vitepress/navigation.mjs`, `github-pages/` | Documentation navigation, theme, and site build tooling                   |

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
axonx plugin install -e ./plugins/qlib_a158
# Factor and strategy layers:
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

The default pytest configuration includes factor and strategy plugin tests and all three plugin source paths. Install the research dependencies above when running those tests. See the [plugin guide](https://flowllm-ai.github.io/AxonX/en/plugins/management) for discovery and restart behavior.

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
npm ci && npm run build
```

The build verifies rendered pages and Markdown exports. Root and plugin READMEs and contribution guides are rendered from their canonical sources by the same build; update both languages together and verify example commands.

## Documentation contributions

Edit the canonical guide under `docs/`, or the root/plugin README or contribution guide imported into the site, and update both languages together. Keep matching paths and shared assets under `docs/figures/`. Site navigation is defined in `docs/.vitepress/navigation.mjs`.

Do not edit `github-pages/.generated/` or `github-pages/dist/`; they are regenerated. For site development and deployment details, see [github-pages/README.md](github-pages/README.md). Keep the two root READMEs and contribution guides aligned when their instructions change.

## Submitting a pull request

Use a descriptive title; Conventional Commits such as `fix(tasks): preserve run status` or `docs: clarify quick start` are encouraged. Explain the problem, resulting behavior, compatibility impact, and validation. Include screenshots for visible UI changes and note any external-service tests that were skipped.

The PR template prompts for these details. List validation commands and results, explain any checks not run, and note English/Chinese documentation updates. Remove optional sections that do not apply.

Contributions are covered by the project's [Apache License 2.0](LICENSE).

## Releases

AxonX and Studio release independently. Commit version updates and pass the relevant CI before publishing. Integration tests require model API keys and run locally when needed.

- **AxonX**: update `axonx/_version.py`, then create and push `v<version>`. Publishing a GitHub Release for that tag automatically publishes `axonx` to PyPI. Alternatively, run `Release / AxonX Python package` manually with the version without `v`.
- **Studio**: synchronize `axonx_studio/pyproject.toml`, `package.json`, and `package-lock.json`, then push to `main`. Run `Release / AxonX Studio` manually with the `main` branch selected. Versions are read from the manifests; no tag or version input is required. The default `both` publishes PyPI before npm; `pypi` and `npm` publish independently. The npm tag is selected automatically: `latest` for stable versions and `next` for prereleases.

AxonX builds from its release tag; Studio builds from the exact `main` commit selected when the workflow starts. Both verify distribution versions. Studio's Python and npm packages contain identical static assets; Python prerelease metadata is normalized according to PEP 440. The AxonX release does not publish research plugins.

Package CI also checks that research-plugin wheels and sdists contain all Python modules and data files declared in `tool.setuptools.package-data`, with contents identical to the source tree. Update package-data declarations when adding runtime resources; declared patterns must match source files.

Configure PyPI Trusted Publishers for `axonx` and `axonx-studio` with their respective workflows and the `pypi` environment. Configure npm Trusted Publishing for `@flowllm-ai/axonx-studio` with `release-axonx-studio.yml` and the `npm` environment. A new npm package needs its initial publication before Trusted Publishing can be configured.

Existing versions fail publication rather than being overwritten or silently skipped. If npm fails during a dual release, rerun the failed job in the original workflow run to reuse the same artifacts. Single-package publishing is also available; keep the Studio sources unchanged when recovering through a new run. Do not move AxonX release tags.
