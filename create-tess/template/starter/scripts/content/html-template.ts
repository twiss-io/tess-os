/**
 * Content Builder — HTML Page Template
 *
 * Assembles final HTML pages from processed content, SEO data, and sidebar.
 */

import fs from 'node:fs';
import path from 'node:path';
import type { ArticleConfig, ContentConfig, CollectedHeading } from './types.js';
import { convertMarkdownToHtml } from './markdown-processor.js';
import { generateSchemaJson } from './seo-generator.js';
import { generateSidebarHtml } from './sidebar-generator.js';

export function buildArticle(article: ArticleConfig, config: ContentConfig): void {
  const markdown = fs.readFileSync(article.mdSource, 'utf8').replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  const headings: CollectedHeading[] = [];

  // Remove first H1 (shown in header)
  const processedMd = markdown.replace(/^# .*\n+/, '');
  const articleContent = convertMarkdownToHtml(processedMd.trim(), headings);

  const sidebarHtml = generateSidebarHtml(article, headings);
  const hasSidebar = article.sidebar === true;

  const mainSection = hasSidebar
    ? `    <div class="article-layout">
${sidebarHtml}
        <main>
            <article class="article-content">
${articleContent}
            </article>
        </main>
    </div>
    <div class="sidebar-overlay" id="sidebarOverlay"></div>
    <button class="sidebar-toggle" id="sidebarToggle">Contents</button>`
    : `    <main>
        <article class="article-content">
${articleContent}
        </article>
    </main>`;

  const sidebarJs = hasSidebar ? generateSidebarJs() : '';

  const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${article.title} — ${config.siteName}</title>
    <meta name="description" content="${article.description}">
    <meta name="author" content="${config.author}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="${article.url}">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="article">
    <meta property="og:url" content="${article.url}">
    <meta property="og:title" content="${article.title} — ${config.siteName}">
    <meta property="og:description" content="${article.description}">
    ${article.bannerImage ? `<meta property="og:image" content="${config.siteUrl}${article.bannerImage}">` : ''}
    <meta property="og:site_name" content="${config.siteName}">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="${article.title} — ${config.siteName}">
    <meta name="twitter:description" content="${article.description}">
    ${article.bannerImage ? `<meta name="twitter:image" content="${config.siteUrl}${article.bannerImage}">` : ''}

    <!-- Schema.org -->
${generateSchemaJson(article, config)}

    <!-- Syntax highlighting -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>

    <!-- Add your CSS here -->
    <link rel="stylesheet" href="/css/global.css">
    <link rel="stylesheet" href="/css/article.css">
</head>
<body>
    <header>
        <h1>${article.titleHtml ?? article.title}</h1>
        ${article.subtitle ? `<p class="subtitle">${article.subtitle}</p>` : ''}
    </header>

    ${article.bannerImage ? `<div class="hero-banner" role="img" aria-label="${article.bannerAlt ?? article.title}" style="background-image: url('${article.bannerImage}')"></div>` : ''}

${mainSection}

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('pre code').forEach(function(block) {
                hljs.highlightElement(block);
            });
        });
${sidebarJs}
    </script>
</body>
</html>`;

  const outputDir = path.dirname(article.htmlOutput);
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  fs.writeFileSync(article.htmlOutput, fullHtml);
  const sizeKb = (fullHtml.length / 1024).toFixed(1);
  console.log(`  \u2713 ${article.id} \u2192 ${article.htmlOutput} (${sizeKb} KB, ${headings.length} headings)`);
}

function generateSidebarJs(): string {
  return `
        // Sidebar scroll spy
        (function() {
            var tocLinks = document.querySelectorAll('.sidebar-toc a');
            var headings = [];
            tocLinks.forEach(function(link) {
                var id = link.getAttribute('href').slice(1);
                var heading = document.getElementById(id);
                if (heading) headings.push({ el: heading, link: link });
            });
            if (headings.length > 0) {
                var observer = new IntersectionObserver(function(entries) {
                    entries.forEach(function(entry) {
                        if (entry.isIntersecting) {
                            tocLinks.forEach(function(l) { l.classList.remove('active'); });
                            var match = headings.find(function(h) { return h.el === entry.target; });
                            if (match) match.link.classList.add('active');
                        }
                    });
                }, { rootMargin: '-80px 0px -70% 0px' });
                headings.forEach(function(h) { observer.observe(h.el); });
            }
            var sidebar = document.getElementById('articleSidebar');
            var overlay = document.getElementById('sidebarOverlay');
            var toggle = document.getElementById('sidebarToggle');
            function openSidebar() { if (sidebar) sidebar.classList.add('open'); if (overlay) overlay.classList.add('open'); }
            function closeSidebar() { if (sidebar) sidebar.classList.remove('open'); if (overlay) overlay.classList.remove('open'); }
            if (toggle) toggle.addEventListener('click', openSidebar);
            if (overlay) overlay.addEventListener('click', closeSidebar);
            tocLinks.forEach(function(link) { link.addEventListener('click', closeSidebar); });
        })();`;
}
