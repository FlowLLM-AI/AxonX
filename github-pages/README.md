# AxonX documentation site

VitePress builds the product homepage and bilingual documentation for GitHub Pages.
Canonical content and theme live in `docs/`; `.generated/` and `dist/` are disposable.

```sh
cd github-pages
npm ci
npm run dev
npm run build
npm run preview
```

Requires Node.js 22+. Restart development after changing canonical docs or theme files
so the generated tree refreshes. Navigation order is defined in `docs/.vitepress/navigation.ts`;
labels come from document headings. Repository-relative source links become GitHub links
at build time. Existing Markdown guides remain unchanged.

The default deployment is `https://flowllm-ai.github.io/AxonX/`. For a custom domain,
set `DOCS_BASE=/` and `DOCS_SITE_URL=https://your-domain` and configure Pages DNS.
`DOCS_SITE_URL` is the origin; `DOCS_BASE` supplies the mount path.

`.github/workflows/docs.yml` builds pull requests and deploys the main branch.
Select **GitHub Actions** as the repository's Pages source before the first deployment.
The build verifies rendered pages and exports each guide as Markdown alongside
`llms.txt` and `llms-full.txt`.

Vite is pinned through an override to the patched 6.4 release line; VitePress stays
on stable 1.6.4. The verification script supports the project base (`/AxonX/`) and custom-domain
base (`/`). Markdown exports use absolute links.
