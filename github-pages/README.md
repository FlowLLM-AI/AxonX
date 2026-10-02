# AxonX documentation site

VitePress builds the bilingual product homepage and documentation for GitHub Pages.
Canonical sources are `docs/`, the root `README.md` / `README_ZH.md` and
`CONTRIBUTING.md` / `CONTRIBUTING_ZH.md`, and the bilingual READMEs in
`plugins/a158/` and `plugins/a158_enhanced/`. `.generated/` and `dist/` are disposable.

```sh
cd github-pages
npm ci
npm run dev
npm run build
npm run format:check
npm run preview
```

Requires Node.js 22+. Restart development after changing canonical sources so the
generated tree refreshes. `docs/.vitepress/navigation.mjs` assigns every document
to exactly one tab; labels come from document headings. `scripts/generate-content.mjs`
maps each page to its canonical source:

| Site route (under `/en/` or `/zh/`) | Canonical source                                 |
| ----------------------------------- | ------------------------------------------------ |
| `getting-started/overview`          | Root README in the selected language             |
| `development/contributing`          | Root contribution guide in the selected language |
| `plugins/management`                | `docs/<language>/plugins/management.md`          |
| `plugins/alpha158`                  | `plugins/a158/README*.md`                        |
| `plugins/alpha158-enhanced`         | `plugins/a158_enhanced/README*.md`               |

Published document links become site links, shared images are copied to `media/`,
and code/data links point to GitHub. Markdown and HTML links are transformed;
fenced code examples stay unchanged. Edit links point to the canonical source.
The old introduction and plugin-management routes have been removed without redirects.

The default deployment is `https://flowllm-ai.github.io/AxonX/`. For a custom domain,
set `DOCS_BASE=/` and `DOCS_SITE_URL=https://your-domain` and configure Pages DNS.
`DOCS_SITE_URL` is the origin; `DOCS_BASE` supplies the mount path.

`.github/workflows/docs.yml` builds pull requests and deploys the main branch.
It watches documentation, root READMEs/contribution guides, and both plugin directories.
Select **GitHub Actions** as the repository's Pages source before the first deployment.
The build verifies pages, navigation ownership, canonical edit links, bilingual paths,
local links/images, and Markdown exports alongside `llms.txt` and `llms-full.txt`.
Markdown exports use absolute site URLs, including images.

Run `npm run format` to format all site sources. Vite is pinned to the patched
6.4 release line; VitePress stays on stable 1.6.4.
