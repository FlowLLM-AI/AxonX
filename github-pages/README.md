# AxonX documentation site

English · [简体中文](README_ZH.md)

This directory contains the build scripts for AxonX's bilingual product homepage and documentation site. It uses VitePress with a custom Vue theme and publishes a static site to GitHub Pages. It does not need an AxonX backend or Python environment to build or serve documentation.

The default deployment is <https://flowllm-ai.github.io/AxonX/>, with English content under `/AxonX/en/` and Simplified Chinese under `/AxonX/zh/`.

## Site features

- Bilingual product homepages with research workflow links and Studio screenshots.
- Documentation grouped into Docs, Plugins, Research, Studio, Agent, and Developers tabs, with a sidebar for each group.
- Local search, page outlines, previous/next links, and edit links to canonical repository sources.
- Saved language preferences (English, Chinese, or browser language) and appearance preferences (light, dark, or system).
- Per-page **View Markdown** links, a document index in `llms.txt`, and combined documentation in `llms-full.txt`.

## Local development

Requires **Node.js 22+** and npm. Start from a complete repository checkout: generation reads files outside this directory.

```bash
cd github-pages
npm ci
npm run dev
```

Open the URL printed by VitePress, including the `/AxonX/` base path. `dev` first generates the site sources, then starts VitePress with hot updates to that generated tree. After editing canonical sources, stop and restart `npm run dev` to refresh the copied content, configuration, and theme.

To build and preview the production output:

```bash
npm run build
npm run preview
```

`preview` serves the existing build; it does not regenerate or rebuild content. Neither command deploys the site.

| Command (in `github-pages/`) | Purpose                                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------ |
| `npm run content`            | Recreate `.generated/site/` from canonical sources.                                              |
| `npm run dev`                | Generate content and start the VitePress development server.                                     |
| `npm run build`              | Generate content, build into `dist/`, and verify the output.                                     |
| `npm run preview`            | Preview the built static site.                                                                   |
| `npm run format:check`       | Check site sources, `docs/`, root READMEs/contribution guides, and plugin READMEs with Prettier. |
| `npm run format`             | Format the same set of sources.                                                                  |

The formatting commands also operate outside `github-pages/`. Generated files, build output, lockfiles, and dependencies are excluded through the repository's [Prettier ignore file](../.prettierignore).

## Canonical content and routes

Edit the original sources. `.generated/` and `dist/` are disposable build directories and are excluded from Git.

| Site route (after `/en/` or `/zh/`) | Canonical source                                                                            |
| ----------------------------------- | ------------------------------------------------------------------------------------------- |
| Language homepage                   | `docs/.vitepress/theme/HomePage.vue`; language entry pages are generated.                   |
| `docs`                              | `docs/en/index.md` or `docs/zh/index.md`.                                                   |
| `getting-started/overview`          | Root `README.md` or `README_ZH.md`.                                                         |
| `development/contributing`          | Root `CONTRIBUTING.md` or `CONTRIBUTING_ZH.md`.                                             |
| `plugins/alpha158`                  | `plugins/a158/README.md` or `README_ZH.md`.                                                 |
| `plugins/alpha158-enhanced`         | `plugins/a158_enhanced/README.md` or `README_ZH.md`.                                        |
| Other documentation routes          | Matching Markdown files under `docs/en/` and `docs/zh/`, including `plugins/management.md`. |

The generator writes `.generated/site/.source-map.json` to map each published document to its original repository file. VitePress uses this mapping for canonical edit links and Markdown exports. This directory's README files describe the build tooling and are not imported as documentation pages.

### Add or update a page

1. Edit its canonical source, or add matching files under `docs/en/` and `docs/zh/`.
2. Use a top-level `#` heading: navigation labels are read from document headings.
3. Register a new document route in exactly one group in [navigation.mjs](../docs/.vitepress/navigation.mjs). Each registered route must exist in both languages.
4. Keep images in shared repository locations such as `docs/figures/` and link to them from the canonical source.
5. Run `npm run build` and `npm run format:check`, then preview the affected pages in both languages.

For homepage, layout, or preferences changes, edit `docs/.vitepress/theme/`. Site configuration, search, metadata, deployment paths, and export generation live in [config.mts](../docs/.vitepress/config.mts).

### Link and asset transformation

[scripts/generate-content.mjs](scripts/generate-content.mjs) resolves links relative to each canonical source:

- Links to published Markdown sources become site routes, including mapped root and plugin documents.
- Shared images are copied under `public/media/<repository-path>` and served under `media/` in the build. Studio logo/icon assets are also copied into the site's public directory.
- Links to repository code, data, and other unpublished files point to GitHub `blob/main` or `tree/main` URLs.
- Markdown inline links and HTML `<a>`/`<img>` URLs are transformed; fenced code examples remain unchanged.

Markdown exports use absolute site URLs, including image URLs. Exported text has a UTF-8 BOM so static hosts can render Chinese text correctly even without an explicit charset.

The legacy `getting-started/introduction` and `guides/plugin-management` routes are absent and have no redirects. Use `getting-started/overview` and `plugins/management` instead.

## Build verification

`npm run build` finishes by running [scripts/verify-build.mjs](scripts/verify-build.mjs). A successful build checks:

- Required HTML pages, bilingual homepages, icons, Markdown exports, and LLM text files exist and are nonempty.
- Every document belongs to exactly one navigation tab, with the expected sidebar and active top-level tab.
- English and Chinese documentation have matching routes, and every navigation entry has a source in both languages.
- Edit links point to canonical sources; local HTML links and assets stay within the deployment base and resolve to build output.
- Markdown exports contain absolute URLs (apart from local anchors), valid UTF-8, and the expected BOM.
- Removed legacy pages are absent.

These checks validate generated local output. They do not verify remote websites, DNS, or the live deployment. `format:check` is a separate command and is not run by the documentation workflow.

## Deployment

The [documentation workflow](../.github/workflows/docs.yml) installs dependencies with Node.js 22, builds the site, and uploads `github-pages/dist/` as the Pages artifact.

- Pull requests targeting `main` build and verify documentation without deploying it.
- Matching pushes to `main` build and deploy; manual workflow runs on `main` can deploy as well.
- Watched paths include `docs/`, `github-pages/`, root READMEs/contribution guides, both research plugin directories, Studio logo/icon SVGs, and the workflow itself.

Before the first deployment, select **GitHub Actions** as the repository's Pages source. Deployment uses the `github-pages` environment with `pages: write` and `id-token: write` permissions.

### Base path and custom domain

| Variable        | Default                        | Meaning                                                                |
| --------------- | ------------------------------ | ---------------------------------------------------------------------- |
| `DOCS_BASE`     | `/AxonX/`                      | Site mount path; use leading and trailing slashes.                     |
| `DOCS_SITE_URL` | `https://flowllm-ai.github.io` | Site origin used by Markdown and LLM exports; excludes the mount path. |

For a custom domain hosted at its root:

```bash
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run build
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run preview
```

Configure the same values in CI and set the custom domain and DNS in GitHub Pages. The current workflow explicitly sets `DOCS_BASE: /AxonX/`; update it for a different mount path. Keep the base consistent across development, build, and preview. Deploy the generated `dist/` output.

## Code organization

| Path                                | Responsibility                                                                                                 |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `scripts/generate-content.mjs`      | Copy canonical sources/theme, map routes and links, copy shared assets, and generate homepages/source mapping. |
| `scripts/verify-build.mjs`          | Verify pages, navigation, bilingual paths, links/assets, edit links, and exports.                              |
| `../docs/.vitepress/config.mts`     | VitePress configuration, locales, search, output paths, canonical edit links, and text exports.                |
| `../docs/.vitepress/navigation.mjs` | Top-level tabs and document ownership.                                                                         |
| `../docs/.vitepress/links.mjs`      | Link transformation outside fenced code blocks.                                                                |
| `../docs/.vitepress/theme/`         | Homepage, document tools, preference controls, and styles.                                                     |
| `.generated/site/`                  | Generated VitePress input; includes `.source-map.json`.                                                        |
| `dist/`                             | Deployable static HTML, assets, Markdown, and LLM text.                                                        |
| `../.github/workflows/docs.yml`     | Documentation CI and Pages deployment.                                                                         |

Dependencies are declared in `package.json` and locked in `package-lock.json`. VitePress is pinned to `1.6.4`; the Vite override uses the `^6.4.3` release range.

## Troubleshooting

| Symptom                                 | Check                                                                                              |
| --------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Edits do not appear in development      | Restart `npm run dev` to regenerate canonical sources; do not edit `.generated/`.                  |
| Missing source or navigation errors     | Add both language files, register the route once, and check the source mapping for imported pages. |
| Missing image or local link errors      | Resolve the path from the canonical source and confirm the target exists in the repository.        |
| Broken assets or links after deployment | Match `DOCS_BASE` to the deployed mount path and rebuild.                                          |
| Exports point to the wrong domain       | Set `DOCS_SITE_URL` to the origin and `DOCS_BASE` to the mount path, then rebuild.                 |
| The page switches to another language   | Check the saved language preference in the navigation menu.                                        |
| CI builds but Pages does not deploy     | Check the branch/event, Pages source setting, deployment environment, and workflow permissions.    |

See the [documentation index](../docs/README.md) and [contribution guide](../CONTRIBUTING.md) for content maintenance. AxonX is released under the [Apache License 2.0](../LICENSE).
