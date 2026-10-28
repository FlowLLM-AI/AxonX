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

Start the Python service from the repository root in another terminal:

```bash
export AXONX_SERVICE_TOKEN='replace-with-your-service-token'
axonx app --service.host 127.0.0.1
```

The default port is `1024`; runtime data goes into `.axonx/` and service/CLI logs into `logs/`. Use [example.env](example.env) for optional credentials and bundled configuration variables. CLI startup loads the nearest `.env` from the current directory or up to five parents, preserving existing environment values. See [Studio development](docs/en/development/studio.md) for proxy and build settings.

## Configure a 0.3.0 application

`axonx app --config NAME_OR_PATH` accepts YAML/YML/JSON files, bundled `default`/`remote` names, and installed `axonx.configs` entries. Custom files must explicitly inherit defaults. For example, save this as `axonx.local.yaml`:

```yaml
extends: default
workspace_dir: .axonx
service:
  host: 127.0.0.1
```

```bash
axonx app --config ./axonx.local.yaml
```

Mappings merge recursively; lists and scalars replace inherited values. Relative workspace/log paths resolve from the process working directory. `exec`/`kill` settings use explicit CLI options, then service `get_config`, then built-in defaults; Task parameters belong to each Task's input schema. `get_config` can include credentials, so keep its output out of public reports. See [configuration](docs/en/reference/configuration.md).

## Choose the right area

| Location                      | Responsibility                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------ |
| `axonx/task/`                 | Typed models, authoring bases, synchronous runtime, storage and built-in Tasks |
| `axonx/plugin/`               | Plugin discovery, wheel validation and installation                            |
| `axonx/utils/`                | Shared environment, logging, value conversion and async cleanup                |
| `axonx/app/`, `axonx/client/` | Application capabilities, Jobs, transports and caller connections              |
| `axonx/cli/`, `axonx/daemon/` | Command routing, service supervision and scheduled process ownership           |
| `plugins/`                    | Research algorithms, manifests and plugin tests                                |
| `axonx_studio/`               | UI, forms, API client and research views                                       |
| `docs/`, `github-pages/`      | Bilingual guides, figures, navigation and site tooling                         |

Keep algorithms in Tasks/plugins. Task execution must not depend on App, Plugin or CLI; startup assembles catalogs and injects host capabilities. `app/core/composition.py` selects concrete Providers and orders managed lifecycles; Steps adapt Jobs to component base contracts. HTTP/MCP clients remain independent of App. Import from owning modules, keep data contracts free of execution side effects, and make resource cleanup explicit. See [architecture](docs/en/concepts/architecture.md), [framework extensions](docs/en/development/framework-extensions.md) and the [dependency map](module-dependencies.md).

## Develop a plugin

Install only the layers needed for your change, including their upstream dependencies, in order:

```bash
axonx plugin install -e ./plugins/qlib_a158
axonx plugin install -e ./plugins/qlib_factor
axonx plugin install -e ./plugins/qlib_strategy
```

Research plugins are not published to PyPI. Restart persistent services after code changes; reinstall after dependency or entry-point changes. Remote deployment requires build, upload, target-side installation, staging cleanup and restart; see [plugin management](docs/en/plugins/management.md).

A plugin includes package metadata, an `axonx.plugins` entry point, `plugin.yaml`, typed Tasks, tests and bilingual READMEs. Add runtime resources to `tool.setuptools.package-data`; package CI compares wheel/sdist contents with source. Follow [Task development](docs/en/dev_guide.md) and [artifact contracts](docs/en/reference/research-artifacts.md).

Optional named application configs use an `axonx.configs` entry point targeting a package and file stem, for example `qlib_a158 = "axonx_qlib_a158.config:qlib_a158_demo"`. Include `config/__init__.py` and the YAML resource in the distribution. Entry points must have unique names; application configs do not register Tasks.

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

Also check Agent resources with `python -m scripts.sync_agent_guides --check` and architecture changes with `python -m pytest tests/unit/test_module_boundaries.py`.

Bare `pytest` also collects plugin tests and needs their research dependencies. Integration tests are deselected by default; run `python -m pytest tests/integration -m integration` only with the required services and credentials after reviewing external effects.

Contract generation updates both `axonx_studio/src/shared/api/contracts.ts` and `axonx_studio/src/playground/job-contracts.json`. Regenerate after changing serialized Python models, default Jobs, or `axonx/_version.py`; do not edit the generated output.

Use temporary workspaces. Keep credentials, private data, `.axonx/`, logs and generated research outputs out of commits. Check affected UI flows in both languages, including empty and failed requests. Run `pre-commit run --files <changed-files>` with actual paths; review automatic fixes. Hooks use Ruff for import ordering, Black for formatting, and additional lint checks.

## Update documentation

Edit canonical sources in `docs/en/`, `docs/zh/`, or the imported root/plugin READMEs and contribution guides. Keep translations aligned and shared assets in `docs/figures/`. Navigation lives in `docs/.vitepress/navigation.mjs`; generated site files are rebuilt.

The canonical Agent guides live in `docs/{en,zh}/dev_guide.md`. Run `python -m scripts.sync_agent_guides` after editing them to regenerate the packaged guide resources and [AxonX Skill](skills/axonx/SKILL.md); `--check` verifies consistency. Verify commands and update contract examples when APIs change. Studio's `contracts:generate` also exports default Job schemas and the AxonX version for Playground; keep both generated files in the change.

From the repository root, prepare both frontend dependency sets and verify the site:

```bash
npm --prefix axonx_studio ci
npm --prefix github-pages ci
npm --prefix github-pages test
npm --prefix github-pages run build
```

The build checks bilingual pages, links, assets, anchors and Markdown exports. See [site development](github-pages/README.md) for details.

Vercel uses the repository-root `vercel.json` to build the static documentation and Playground with `DOCS_BASE=/` and clean URLs. It installs both frontend packages and publishes `github-pages/dist`; the Python service runs separately. Validate the root deployment path with `DOCS_BASE=/ DOCS_SITE_URL=https://axon-x.vercel.app npm --prefix github-pages run build`.

## Submit a pull request

Explain the problem, resulting behavior, affected contracts and validation. Include screenshots for visible UI changes and note documentation updates. Conventional Commit titles are encouraged. Contributions use the [Apache License 2.0](LICENSE).

## Releases

AxonX and Studio release independently after version updates and passing CI:

- **AxonX:** update `axonx/_version.py` (currently `0.3.0`), regenerate Studio contracts, push `v<version>`, then publish its GitHub Release. Alternatively, run [Release / AxonX Python package](.github/workflows/release-python.yml) with the version without `v`; it builds that tag.
- **Studio:** synchronize `axonx_studio/pyproject.toml`, `package.json` and `package-lock.json`, then run [Release / AxonX Studio](.github/workflows/release-axonx-studio.yml) on `main`. `both` publishes PyPI then npm; `pypi`/`npm` select one. npm uses `latest` for stable versions and `next` for prereleases.

Configure the corresponding Trusted Publishers (`pypi`/`npm` environments). Releases reject existing versions; keep tags fixed. If npm fails after PyPI succeeds, rerun the failed job in the original workflow to reuse its artifacts. Main-package releases do not publish research plugins.
