/**
 * Content Builder — Sidebar Generator
 *
 * Generates sidebar HTML with TOC, parent/child navigation, and grouping.
 */

import type { ArticleConfig, CollectedHeading } from './types.js';

export function generateSidebarHtml(article: ArticleConfig, headings: CollectedHeading[]): string {
  if (!article.sidebar) return '';

  const parts: string[] = [];

  if (article.parent) {
    parts.push(`        <a href="${article.parent.url}" class="sidebar-back">${article.parent.title}</a>`);
  }

  const maxLevel = article.tocLevel ?? (article.parent ? 2 : 1);
  let tocHeadings = headings.filter((h) => h.level <= maxLevel);
  if (article.tocFilter) {
    const re = new RegExp(article.tocFilter);
    tocHeadings = tocHeadings.filter((h) => re.test(h.text));
  }

  if (tocHeadings.length > 0) {
    parts.push('        <div class="sidebar-label">CONTENTS</div>');
    parts.push('        <ul class="sidebar-toc">');
    for (const h of tocHeadings) {
      const cls = h.level === 1 ? 'toc-h1' : 'toc-h2';
      parts.push(`            <li><a href="#${h.id}" class="${cls}">${h.text}</a></li>`);
    }
    parts.push('        </ul>');
  }

  if (article.children && article.children.length > 0) {
    const currentPath = '/' + article.htmlOutput.replace(/index\.html$/, '');
    const hasGroups = article.children.some((c) => c.group);

    if (hasGroups) {
      let listOpen = false;
      for (const child of article.children) {
        if (child.group) {
          if (listOpen) parts.push('        </ul>');
          parts.push(`        <div class="sidebar-label">${child.group}</div>`);
          parts.push('        <ul class="sidebar-links">');
          listOpen = true;
        }
        const isCurrent = child.url === currentPath;
        const cls = isCurrent ? ' class="sidebar-current"' : '';
        parts.push(`            <li><a href="${child.url}"${cls}>${child.title}</a></li>`);
      }
      if (listOpen) parts.push('        </ul>');
    } else {
      const label = article.childrenLabel ?? (article.parent ? 'RELATED' : 'DEEP DIVES');
      parts.push(`        <div class="sidebar-label">${label}</div>`);
      parts.push('        <ul class="sidebar-links">');
      for (const child of article.children) {
        const isCurrent = child.url === currentPath;
        const cls = isCurrent ? ' class="sidebar-current"' : '';
        parts.push(`            <li><a href="${child.url}"${cls}>${child.title}</a></li>`);
      }
      parts.push('        </ul>');
    }
  }

  return `    <aside class="article-sidebar" id="articleSidebar">
        <div class="sidebar-inner">
${parts.join('\n')}
        </div>
    </aside>`;
}
