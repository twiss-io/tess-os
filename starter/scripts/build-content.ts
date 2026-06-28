#!/usr/bin/env npx tsx
/**
 * build-content.ts — Markdown-to-HTML Article Builder (CLI)
 *
 * Converts markdown files to fully SEO-ready static HTML pages using a
 * JSON config file as the single source of truth.
 *
 * Based on the production article builder from TheDecipherist.
 * https://github.com/TheDecipherist/claude-code-mastery
 *
 * USAGE:
 *   npx tsx scripts/build-content.ts                    # Build all published
 *   npx tsx scripts/build-content.ts --id getting-started # Build one article
 *   npx tsx scripts/build-content.ts --list             # List all articles
 *   npx tsx scripts/build-content.ts --dry-run          # Show what would build
 *
 * CONFIG:
 *   Edit scripts/content.config.json to add/modify articles.
 *   Each article needs: id, mdSource, htmlOutput, title, description, url
 *
 * MODULES:
 *   scripts/content/types.ts             — Types & Zod validation
 *   scripts/content/markdown-processor.ts — Markdown → HTML conversion
 *   scripts/content/seo-generator.ts     — Schema.org JSON-LD
 *   scripts/content/sidebar-generator.ts — Sidebar TOC & navigation
 *   scripts/content/html-template.ts     — Full HTML page assembly
 */

import fs from 'node:fs';
import path from 'node:path';
import { ContentConfigSchema } from './content/types.js';
import { buildArticle } from './content/html-template.js';

function main(): void {
  const args = process.argv.slice(2);
  const configPath = path.resolve(import.meta.dirname ?? __dirname, 'content.config.json');

  if (!fs.existsSync(configPath)) {
    console.error(`Config not found: ${configPath}`);
    console.error('Create scripts/content.config.json first.');
    process.exit(1);
  }

  const raw: unknown = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  const parsed = ContentConfigSchema.safeParse(raw);
  if (!parsed.success) {
    console.error('\n  Invalid content.config.json:\n');
    for (const issue of parsed.error.issues) {
      console.error(`    - ${issue.path.join('.')}: ${issue.message}`);
    }
    console.error('');
    process.exit(1);
  }
  const config = parsed.data;

  const published = config.articles.filter((a) => a.published);

  // --list
  if (args.includes('--list')) {
    console.log(`\n  ${config.articles.length} articles (${published.length} published):\n`);
    for (const a of config.articles) {
      const status = a.published ? '\u2713' : '\u25CB';
      console.log(`    ${status} ${a.id.padEnd(35)} ${a.category ?? ''}`);
    }
    console.log('');
    return;
  }

  // --dry-run
  if (args.includes('--dry-run')) {
    console.log(`\n  Would build ${published.length} articles:\n`);
    for (const a of published) {
      console.log(`    ${a.mdSource} \u2192 ${a.htmlOutput}`);
    }
    console.log('');
    return;
  }

  // --id <article-id>
  const idIdx = args.indexOf('--id');
  if (idIdx !== -1) {
    const targetId = args[idIdx + 1];
    const article = config.articles.find((a) => a.id === targetId);
    if (!article) {
      console.error(`Article not found: ${targetId}`);
      console.error('Run with --list to see available articles.');
      process.exit(1);
    }
    console.log(`\n  Building: ${article.id}\n`);
    buildArticle(article, config);
    console.log('\n  Done.\n');
    return;
  }

  // Default: build all published
  if (published.length === 0) {
    console.log('\n  No published articles to build.\n');
    return;
  }

  console.log(`\n  Building ${published.length} published article(s)...\n`);
  for (const article of published) {
    buildArticle(article, config);
  }
  console.log(`\n  Done. ${published.length} articles built.\n`);
}

main();
