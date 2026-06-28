/**
 * Content Builder — Markdown Processor
 *
 * Converts markdown text to HTML with support for code blocks,
 * tables, lists, blockquotes, headings, and inline formatting.
 */

import type { CollectedHeading } from './types.js';

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

export function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*\*(.*?)\*\*\*/g, '$1')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
}

export function processInlineFormatting(text: string): string {
  let result = text;
  result = result.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  result = result.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  result = result.replace(/\*(.*?)\*/g, '<em>$1</em>');
  result = result.replace(/`([^`]+)`/g, '<code>$1</code>');
  result = result.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');
  result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  result = result.replace(/ {2}$/gm, '<br>');
  return result;
}

function convertTableToHtml(rows: string[]): string {
  if (rows.length === 0) return '';
  let html = '<div class="table-wrapper">\n<table>\n';

  rows.forEach((row, idx) => {
    const cells = row.split('|').slice(1, -1);
    const tag = idx === 0 ? 'th' : 'td';
    html += '<tr>';
    for (const cell of cells) {
      let content = cell.trim();
      content = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
      content = content.replace(/\*(.*?)\*/g, '<em>$1</em>');
      html += `<${tag}>${content}</${tag}>`;
    }
    html += '</tr>\n';
  });

  html += '</table>\n</div>';
  return html;
}

function processMarkdownTables(html: string): string {
  const lines = html.split('\n');
  const result: string[] = [];
  let inTable = false;
  let tableRows: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      if (!inTable) {
        inTable = true;
        tableRows = [];
      }
      if (!/^\|[\s\-:|]+\|$/.test(trimmed)) {
        tableRows.push(trimmed);
      }
    } else {
      if (inTable) {
        result.push(convertTableToHtml(tableRows));
        inTable = false;
        tableRows = [];
      }
      result.push(line);
    }
  }

  if (inTable && tableRows.length > 0) {
    result.push(convertTableToHtml(tableRows));
  }

  return result.join('\n');
}

function processLists(html: string): string {
  const lines = html.split('\n');
  const result: string[] = [];
  let inList = false;

  for (const line of lines) {
    const match = line.match(/^(\s*)- (.*)$/);
    if (match) {
      const content = processInlineFormatting(match[2]);
      if (!inList) {
        result.push('<ul>');
        inList = true;
      }
      result.push(`<li>${content}</li>`);
    } else {
      if (inList) {
        result.push('</ul>');
        inList = false;
      }
      result.push(line);
    }
  }

  if (inList) result.push('</ul>');
  return result.join('\n');
}

function processOrderedLists(html: string): string {
  const lines = html.split('\n');
  const result: string[] = [];
  let inList = false;

  for (const line of lines) {
    const match = line.match(/^\d+\.\s+(.*)$/);
    if (match) {
      if (!inList) {
        result.push('<ol>');
        inList = true;
      }
      result.push(`<li>${processInlineFormatting(match[1])}</li>`);
    } else {
      if (inList) {
        result.push('</ol>');
        inList = false;
      }
      result.push(line);
    }
  }

  if (inList) result.push('</ol>');
  return result.join('\n');
}

export function convertMarkdownToHtml(md: string, headings: CollectedHeading[]): string {
  let html = md;

  // Code blocks first (preserve content)
  const codeBlocks: string[] = [];
  html = html.replace(/````(\w*)\n([\s\S]*?)````/g, (_match, lang: string, code: string) => {
    const placeholder = `___CODEBLOCK_${codeBlocks.length}___`;
    codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${escapeHtml(code.trim())}</code></pre>`);
    return placeholder;
  });
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang: string, code: string) => {
    const placeholder = `___CODEBLOCK_${codeBlocks.length}___`;
    codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${escapeHtml(code.trim())}</code></pre>`);
    return placeholder;
  });

  // Tables
  html = processMarkdownTables(html);

  // Blockquotes
  html = html.replace(/^>\s*(.*)$/gm, '<blockquote><p>$1</p></blockquote>');
  html = html.replace(/<\/blockquote>\n<blockquote>/g, '\n');

  // Headings (collect for sidebar TOC)
  html = html.replace(/^#### (.*)$/gm, (_m, text: string) => {
    const id = slugify(text);
    headings.push({ level: 4, id, text: stripMarkdown(text) });
    return `<h4 id="${id}">${processInlineFormatting(text)}</h4>`;
  });
  html = html.replace(/^### (.*)$/gm, (_m, text: string) => {
    const id = slugify(text);
    headings.push({ level: 3, id, text: stripMarkdown(text) });
    return `<h3 id="${id}">${processInlineFormatting(text)}</h3>`;
  });
  html = html.replace(/^## (.*)$/gm, (_m, text: string) => {
    const id = slugify(text);
    headings.push({ level: 2, id, text: stripMarkdown(text) });
    return `<h2 id="${id}">${processInlineFormatting(text)}</h2>`;
  });
  html = html.replace(/^# (.*)$/gm, (_m, text: string) => {
    const id = slugify(text);
    headings.push({ level: 1, id, text: stripMarkdown(text) });
    return `<h1 id="${id}">${processInlineFormatting(text)}</h1>`;
  });

  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr>');

  // Lists
  html = processLists(html);
  html = processOrderedLists(html);

  // Remaining inline formatting
  html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

  // Paragraphs
  const blockTags = /^<(h[1-6]|ul|ol|li|blockquote|pre|div|table|tr|th|td|hr|nav|header|footer|article|section)/i;
  const rawLines = html.split('\n');
  const groups: Array<{ type: string; lines?: string[]; content?: string }> = [];
  let currentGroup: string[] = [];

  for (const line of rawLines) {
    const trimmed = line.trim();
    if (trimmed === '' || blockTags.test(trimmed) || trimmed.startsWith('___CODEBLOCK_')) {
      if (currentGroup.length > 0) {
        groups.push({ type: 'paragraph', lines: currentGroup });
        currentGroup = [];
      }
      if (trimmed !== '') {
        groups.push({ type: 'html', content: trimmed });
      }
    } else if (line.endsWith('  ')) {
      currentGroup.push(trimmed + '<br>');
    } else {
      currentGroup.push(trimmed);
    }
  }
  if (currentGroup.length > 0) {
    groups.push({ type: 'paragraph', lines: currentGroup });
  }

  const result: string[] = [];
  for (const group of groups) {
    if (group.type === 'html') {
      result.push(group.content!);
    } else if (group.type === 'paragraph' && group.lines) {
      result.push(`<p>${group.lines.join('\n')}</p>`);
    }
  }

  html = result.join('\n');

  // Restore code blocks
  codeBlocks.forEach((block, i) => {
    html = html.replace(`___CODEBLOCK_${i}___`, block);
  });

  html = html.replace(/<p><\/p>/g, '');
  html = html.replace(/\n{3,}/g, '\n\n');

  return html;
}
