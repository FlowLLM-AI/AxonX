# AxonX documentation site

English · [简体中文](README_ZH.md)

This directory owns AxonX's static documentation framework: VitePress configuration, Vue theme, content generation, exports, and build verification. Canonical prose remains in `docs/en/`, `docs/zh/`, and project/plugin READMEs. No AxonX backend or Python environment is needed to serve the site.

The default deployment is <https://flowllm-ai.github.io/AxonX/>, with `/en/` and `/zh/` language routes.

## Reader journeys

The site has six navigation areas: **Get started, Research, Agent, Operations, Reference, and Developers**. Studio tutorials belong to Get started; research plugins belong to Research; APIs and configuration belong to Reference. Each area opens with a goal-based overview. Agent readers first choose external integration or built-in sessions. The homepage links to the README benchmark and reproduction instructions without duplicating metric tables.

[The documentation map](../docs/en/index.md) provides goal-based reading paths. Project and plugin READMEs own overview and algorithm details; guides link to those sources instead of duplicating experiment tables. Each document has one navigation owner and may cross-link to related areas.

## Develop and verify

Use Node.js 22+ and npm from a complete repository checkout:

```bash
npm --prefix axonx_studio ci
cd github-pages
npm ci
npm run test
npm run dev
```

Open the printed URL with its `/AxonX/` base path. Development generates canonical sources into `.generated/site/` before starting VitePress. Restart `npm run dev` after changing original prose, navigation, framework modules, or theme files to refresh the generated tree.

```bash
npm run build
npm run preview
```

Build generates content, creates `dist/`, and verifies output. Preview serves the existing build; neither command deploys. Local search, language/appearance preferences, outlines, canonical edit links, and per-page Markdown exports remain available.

| Command                | Purpose                                                                     |
| ---------------------- | --------------------------------------------------------------------------- |
| `npm run content`      | Validate the content catalog and recreate generated input                   |
| `npm run test`         | Check catalog, settings, links, language precedence, and translation parity |
| `npm run dev`          | Generate input and run the development server                               |
| `npm run build`        | Generate, build, and verify HTML, navigation, assets, anchors, and exports  |
| `npm run preview`      | Serve the existing production output                                        |
| `npm run format:check` | Check framework, docs, and root/plugin READMEs with Prettier                |
| `npm run format`       | Format those sources; review changes before committing                      |

Generated files, dependencies, lockfiles, and output are excluded from formatting through the repository's [ignore rules](../.prettierignore). Never edit `.generated/` or `dist/` by hand.

## Source boundaries

| Location                                         | Responsibility                                                             |
| ------------------------------------------------ | -------------------------------------------------------------------------- |
| `../docs/en/`, `../docs/zh/`, `../docs/figures/` | Canonical bilingual prose and shared figures                               |
| `../docs/.vitepress/navigation.mjs`              | Reading order, group landing pages, and unique document ownership          |
| `site/config.mts`                                | VitePress locales, navigation, search, metadata, and build hooks           |
| `site/theme/`                                    | Homepage, document tools, preferences, and styles                          |
| `lib/site-model.mjs`                             | Discover bilingual sources, map imported READMEs, and validate the catalog |
| `lib/headings.mjs`                               | Read titles outside code fences and supply imported overview titles        |
| `lib/settings.mjs`                               | Validate deployment mount and site origin                                  |
| `lib/links.mjs`                                  | Transform document URLs outside fenced examples                            |
| `lib/exports.mjs`                                | Emit Markdown and language/group-ordered LLM exports                       |
| `scripts/generate-content.mjs`                   | Assemble canonical sources, framework, route map, and shared assets        |
| `scripts/verify-build.mjs`                       | Check generated HTML, navigation, anchors, source links, and exports       |
| `tests/`                                         | Focused build-module regression tests                                      |
| `.generated/site/`                               | Disposable VitePress input, including `.source-map.json`                   |
| `dist/`                                          | Deployable HTML, assets, Markdown, `llms.txt`, and `llms-full.txt`         |

Theme translations and VitePress interface labels live in `site/theme/locales/en.json` and `zh.json`, with matching keys checked by tests. `i18n.ts` exposes reactive resources and localized links; `language.mjs` owns language selection and route conversion. `home.ts` holds language-independent homepage metadata. Follow Studio’s separation of language resources from feature code; Vue/VitePress supplies reactivity without another translation dependency. Keep canonical Markdown and navigation labels in `docs/`.

Framework files were moved from `docs/.vitepress/` into `site/` and `lib/`; navigation remains next to content. Existing document URLs are retained. The older `getting-started/introduction` and `guides/plugin-management` routes remain absent without redirects.

### Add a page

1. Add matching English and Chinese Markdown paths with a top-level heading.
2. Register the route once in [navigation.mjs](../docs/.vitepress/navigation.mjs), in reading order.
3. Link from the relevant goal or guide, and update both document maps when a reading path changes.
4. Run tests, build, and format checks; preview both languages and affected narrow layouts and themes.

The catalog rejects mismatched translations, orphan pages, duplicate owners, imported-route collisions, missing sources, and missing headings before replacing generated output. Root and plugin READMEs are imported using the mappings in `lib/site-model.mjs`: `getting-started/overview`, `development/contributing`, `plugins/alpha158`, and `plugins/alpha158-enhanced`. `docs/{lang}/index.md` becomes `{lang}/docs`.

### Links and exports

Links resolve from each canonical file. Published sources become site routes; shared images become `public/media/<repository-path>` assets; unpublished repository files link to GitHub. Inline Markdown and HTML links are transformed, while fenced examples remain unchanged. Titles exclude fenced code comments; the logo-led project README receives a generated H1 without source edits. Language selection follows `?lang=en|zh`, then an explicit `/en/` or `/zh/` route, then the shared Studio `language` preference, then the browser language (Chinese or English fallback). The root page renders English before client-side language selection redirects to the localized homepage. Saved preferences never override an explicit language route. Automatic language redirects replace the current history entry; the selection is also applied after in-site navigation and browser back/forward. The top bar toggles English/Chinese and light/dark; language switches preserve the document, query parameters, and anchor, and update an existing `lang` parameter. The old `axonx-language` preference is no longer read. The default theme is light; legacy browser/system preferences no longer follow browser or OS settings.

The source map preserves canonical edit links. Markdown exports use absolute URLs and UTF-8 BOMs. `llms.txt` and `llms-full.txt` follow the same bilingual navigation order as the site. Historical experiment materials not imported into the site remain linked to their repository sources.

## Deployment

The [documentation workflow](../.github/workflows/docs.yml) installs dependencies, runs module tests, and builds before uploading `dist/` to GitHub Pages. Pull requests validate without deployment; matching pushes or manual runs on `main` can deploy. Configure GitHub Pages to use GitHub Actions.

| Variable        | Default                        | Meaning                                                           |
| --------------- | ------------------------------ | ----------------------------------------------------------------- |
| `DOCS_BASE`     | `/AxonX/`                      | Mount path, with leading and trailing slashes                     |
| `DOCS_SITE_URL` | `https://flowllm-ai.github.io` | HTTP(S) origin for exports, without a path, query, or credentials |

For a custom domain mounted at its root:

```bash
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run build
DOCS_BASE=/ DOCS_SITE_URL=https://docs.example.com npm run preview
```

Use the same settings in CI and configure the domain and DNS in GitHub Pages. Build checks validate local output, not external links or the live deployment.

### Clone badge

The documentation workflow refreshes `/badges/clones.json` daily at 02:17 UTC and on documentation deployments. The root READMEs use this public Shields endpoint to display GitHub's rolling 14-day clone total (not unique cloners). Only the aggregate count is published; the token and daily traffic records are not included.

Configure the repository Actions secret `AXONX_TRAFFIC_TOKEN` with a dedicated fine-grained PAT restricted to this repository and **Administration: read** permission. Then run **CI / Documentation** manually on `main` to initialize the badge. Without the secret, the badge displays `not configured`; API errors fail the build and preserve the previous deployment. Renew the secret before the token expires. Local verification can run `node --test .github/scripts/write-traffic-badge.test.mjs`.

### Vercel

The repository-root [`vercel.json`](../vercel.json) deploys the documentation and Playground as a static site. It selects the **Other** framework preset to prevent the repository's Python dependencies from triggering FastAPI entrypoint detection, installs both frontend packages, and publishes `github-pages/dist`.

Keep Vercel's **Root Directory** at the repository root and select **Node.js 22.x** in Project Settings. Keep **Automatically expose System Environment Variables** enabled. The build uses `DOCS_BASE=/` and defaults `DOCS_SITE_URL` to `https://$VERCEL_PROJECT_PRODUCTION_URL`; set `DOCS_SITE_URL` explicitly to override the production origin. Preview builds also use the production origin for export URLs. These settings leave the GitHub Pages workflow unchanged and do not deploy the AxonX research backend.

To verify the Vercel build locally from the repository root after installing both packages:

```bash
DOCS_BASE=/ DOCS_SITE_URL=https://axon-x.vercel.app npm --prefix github-pages run build
```

## Troubleshooting

| Symptom                                | Action                                                                     |
| -------------------------------------- | -------------------------------------------------------------------------- |
| Changes are absent in development      | Restart `npm run dev` to regenerate canonical sources                      |
| Catalog validation fails               | Check bilingual paths, navigation ownership, imported routes, and headings |
| A local link or anchor fails           | Resolve it from the canonical source and check the target page heading     |
| Assets fail after deployment           | Match the mount path to `DOCS_BASE` and rebuild                            |
| Export URLs use the wrong origin       | Set `DOCS_SITE_URL` and rebuild                                            |
| The site changes language              | Check `?lang`, the language route, then the shared Studio preference       |
| Build passes but deployment is skipped | Check event, branch, Pages source, environment, and workflow permissions   |

See the [content ownership guide](../docs/README.md) and [contribution guide](../CONTRIBUTING.md) for maintenance conventions.

The navigation and homepage link to Playground. `npm run build` also builds Studio in browser simulation mode and merges its separate output into `dist/playground/`. During documentation development, run `npm --prefix axonx_studio run dev:playground` in another terminal to preview the demo; use build and preview to inspect the merged website. No backend service is needed.
