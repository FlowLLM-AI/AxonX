# Contributing to AxonX

English · [简体中文](CONTRIBUTING_ZH.md)

We welcome fixes, research plugins, experiment evidence and documentation. Search [existing issues](https://github.com/FlowLLM-AI/AxonX/issues) first. Report reproducible steps, expected/actual behavior, versions and sanitized logs. Discuss substantial public-contract changes before implementation; keep each PR focused.

## Development setup

Use Python 3.12+ on macOS or Linux, from your source checkout:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pre-commit install
```

For Studio, use Node.js **22.13+ (22.x), 24.x or 26+**:

```bash
cd axonx_studio
npm ci
npm run dev
```

Start the Python service in another terminal. See [Studio development](docs/en/development/studio.md) for proxy and build settings.

## Choose the right area

| Location                      | Responsibility                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------ |
| `axonx/task/`                 | Typed models, authoring bases, synchronous runtime, storage and built-in Tasks |
| `axonx/plugin/`               | Plugin discovery, wheel validation and installation                            |
| `axonx/app/`, `axonx/client/` | Application capabilities, Jobs, transports and caller connections              |
| `axonx/cli/`, `axonx/daemon/` | Command routing, service supervision and scheduled process ownership           |
| `plugins/`                    | Research algorithms, manifests and plugin tests                                |
| `axonx_studio/`               | UI, forms, API client and research views                                       |
| `docs/`, `github-pages/`      | Bilingual guides, figures, navigation and site tooling                         |

Keep algorithms in Tasks/plugins. Task execution must not depend on App, Plugin or CLI; startup assembles catalogs and injects host capabilities. Import from owning modules, keep data contracts free of execution side effects, and make resource cleanup explicit. See [architecture](docs/en/concepts/architecture.md), [framework extensions](docs/en/development/framework-extensions.md) and the [dependency map](module-dependencies.md).

## Develop a plugin

Install only the layers needed for your change, including their upstream dependencies, in order:

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

Research plugins are not published to PyPI. Restart persistent services after code changes; reinstall after dependency or entry-point changes. Remote deployment requires build, upload, target-side installation, staging cleanup and restart; see [plugin management](docs/en/plugins/management.md).

A plugin includes package metadata, an `axonx.plugins` entry point, `plugin.yaml`, typed Tasks, tests and bilingual READMEs. Add runtime resources to `tool.setuptools.package-data`; package CI compares wheel/sdist contents with source. Follow [Task development](docs/en/dev_guide.md) and [artifact contracts](docs/en/reference/research-artifacts.md).

Agent-authored code follows the same checks. For improvement claims, preserve source/plugin versions, data snapshots, windows, parameters, costs, Task IDs and `started_at`; publish sanitized reproduction evidence and follow [experiment design](docs/en/research/experiments.md).

## Validate the change

Run focused checks first, then the relevant suite. Report commands, results and skipped checks in the PR.

| Area                   | Checks                                                                                  |
| ---------------------- | --------------------------------------------------------------------------------------- |
| Framework              | `python -m pytest tests`                                                                |
| Plugin                 | Its test directory, for example `python -m pytest plugins/qlib_factor/tests`            |
| Studio                 | In `axonx_studio/`: `npm test`, `npm run lint`, `npm run format:check`, `npm run build` |
| Python wire contracts  | In `axonx_studio/`: `npm run contracts:generate` and `npm run contracts:check`          |
| Documentation examples | `python -m pytest tests/unit/test_documentation_contracts.py`                           |

Bare `pytest` also collects plugin tests and needs their research dependencies. Integration tests are excluded by default; run `pytest -m integration` only with the required services and credentials after reviewing external effects.

Use temporary workspaces. Keep credentials, private data, `.axonx/`, logs and generated research outputs out of commits. Check affected UI flows in both languages, including empty and failed requests. Run `pre-commit run --files <changed-files>` with actual paths; review automatic fixes. Hooks use Ruff for import ordering, Black for formatting, and additional lint checks.

## Update documentation

Edit canonical sources in `docs/en/`, `docs/zh/`, or the imported root/plugin READMEs and contribution guides. Keep translations aligned and shared assets in `docs/figures/`. Navigation lives in `docs/.vitepress/navigation.mjs`; generated site files are rebuilt.

The built-in Agent guide resources link to `docs/{en,zh}/dev_guide.md`; keep the distributable [AxonX Skill](skills/axonx/SKILL.md) behavior consistent with the English guide. Verify commands and update contract examples when APIs change.

From the repository root, prepare both frontend dependency sets and verify the site:

```bash
npm --prefix axonx_studio ci
npm --prefix github-pages ci
npm --prefix github-pages test
npm --prefix github-pages run build
```

The build checks bilingual pages, links, assets, anchors and Markdown exports. See [site development](github-pages/README.md) for details.

## Submit a pull request

Explain the problem, resulting behavior, compatibility impact and validation. Include screenshots for visible UI changes and note documentation updates. Conventional Commit titles are encouraged. Contributions use the [Apache License 2.0](LICENSE).

## Releases

AxonX and Studio release independently after version updates and passing CI:

- **AxonX:** update `axonx/_version.py`, push `v<version>`, then publish its GitHub Release. Alternatively, run [Release / AxonX Python package](.github/workflows/release-python.yml) with the version without `v`; it builds that tag.
- **Studio:** synchronize `axonx_studio/pyproject.toml`, `package.json` and `package-lock.json`, then run [Release / AxonX Studio](.github/workflows/release-axonx-studio.yml) on `main`. `both` publishes PyPI then npm; `pypi`/`npm` select one. npm uses `latest` for stable versions and `next` for prereleases.

Configure the corresponding Trusted Publishers (`pypi`/`npm` environments). Releases reject existing versions; keep tags fixed. If npm fails after PyPI succeeds, rerun the failed job in the original workflow to reuse its artifacts. Main-package releases do not publish research plugins.
