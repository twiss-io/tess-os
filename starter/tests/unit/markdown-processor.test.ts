/**
 * Markdown Processor — Unit Tests
 *
 * Tests the markdown-to-HTML conversion functions used by the content builder.
 */

import { describe, it, expect } from 'vitest';
import {
  escapeHtml,
  slugify,
  stripMarkdown,
  processInlineFormatting,
  convertMarkdownToHtml,
} from '../../scripts/content/markdown-processor.js';
import type { CollectedHeading } from '../../scripts/content/types.js';

describe('escapeHtml', () => {
  it('should escape ampersands', () => {
    expect(escapeHtml('a & b')).toBe('a &amp; b');
  });

  it('should escape angle brackets', () => {
    expect(escapeHtml('<div>')).toBe('&lt;div&gt;');
  });

  it('should handle all three together', () => {
    expect(escapeHtml('<a href="x">&</a>')).toBe('&lt;a href="x"&gt;&amp;&lt;/a&gt;');
  });

  it('should return empty string unchanged', () => {
    expect(escapeHtml('')).toBe('');
  });
});

describe('slugify', () => {
  it('should convert to lowercase and replace spaces with hyphens', () => {
    expect(slugify('Hello World')).toBe('hello-world');
  });

  it('should remove special characters', () => {
    expect(slugify("What's New?")).toBe('whats-new');
  });

  it('should collapse multiple hyphens', () => {
    expect(slugify('one -- two --- three')).toBe('one-two-three');
  });

  it('should trim leading/trailing hyphens', () => {
    expect(slugify('  Hello  ')).toBe('hello');
  });
});

describe('stripMarkdown', () => {
  it('should strip bold markers', () => {
    expect(stripMarkdown('**bold**')).toBe('bold');
  });

  it('should strip italic markers', () => {
    expect(stripMarkdown('*italic*')).toBe('italic');
  });

  it('should strip bold-italic markers', () => {
    expect(stripMarkdown('***both***')).toBe('both');
  });

  it('should strip inline code', () => {
    expect(stripMarkdown('`code`')).toBe('code');
  });

  it('should strip links keeping text', () => {
    expect(stripMarkdown('[click here](http://example.com)')).toBe('click here');
  });

  it('should handle mixed formatting', () => {
    expect(stripMarkdown('**bold** and *italic* and `code`')).toBe('bold and italic and code');
  });
});

describe('processInlineFormatting', () => {
  it('should convert bold to <strong>', () => {
    expect(processInlineFormatting('**bold**')).toBe('<strong>bold</strong>');
  });

  it('should convert italic to <em>', () => {
    expect(processInlineFormatting('*italic*')).toBe('<em>italic</em>');
  });

  it('should convert inline code to <code>', () => {
    expect(processInlineFormatting('`code`')).toBe('<code>code</code>');
  });

  it('should convert links to <a>', () => {
    expect(processInlineFormatting('[text](http://example.com)')).toBe('<a href="http://example.com">text</a>');
  });

  it('should convert images to <img>', () => {
    expect(processInlineFormatting('![alt](image.png)')).toBe('<img src="image.png" alt="alt">');
  });

  it('should convert bold-italic to nested tags', () => {
    expect(processInlineFormatting('***both***')).toBe('<strong><em>both</em></strong>');
  });
});

describe('convertMarkdownToHtml', () => {
  it('should convert headings and collect them', () => {
    const headings: CollectedHeading[] = [];
    const html = convertMarkdownToHtml('## My Section', headings);
    expect(html).toContain('<h2 id="my-section">My Section</h2>');
    expect(headings).toHaveLength(1);
    expect(headings[0]).toEqual({ level: 2, id: 'my-section', text: 'My Section' });
  });

  it('should convert all heading levels', () => {
    const headings: CollectedHeading[] = [];
    const md = '# H1\n\n## H2\n\n### H3\n\n#### H4';
    convertMarkdownToHtml(md, headings);
    expect(headings).toHaveLength(4);
    // Headings processed h4→h3→h2→h1 (smaller first to avoid ## matching ###)
    expect(headings.map((h) => h.level)).toEqual([4, 3, 2, 1]);
  });

  it('should convert code blocks with language', () => {
    const headings: CollectedHeading[] = [];
    const md = '```typescript\nconst x = 1;\n```';
    const html = convertMarkdownToHtml(md, headings);
    expect(html).toContain('<pre><code class="language-typescript">');
    expect(html).toContain('const x = 1;');
  });

  it('should escape HTML inside code blocks', () => {
    const headings: CollectedHeading[] = [];
    const md = '```html\n<div>hello</div>\n```';
    const html = convertMarkdownToHtml(md, headings);
    expect(html).toContain('&lt;div&gt;hello&lt;/div&gt;');
  });

  it('should convert unordered lists', () => {
    const headings: CollectedHeading[] = [];
    const md = '- item one\n- item two\n- item three';
    const html = convertMarkdownToHtml(md, headings);
    expect(html).toContain('<ul>');
    expect(html).toContain('<li>item one</li>');
    expect(html).toContain('<li>item two</li>');
    expect(html).toContain('<li>item three</li>');
    expect(html).toContain('</ul>');
  });

  it('should convert ordered lists', () => {
    const headings: CollectedHeading[] = [];
    const md = '1. first\n2. second\n3. third';
    const html = convertMarkdownToHtml(md, headings);
    expect(html).toContain('<ol>');
    expect(html).toContain('<li>first</li>');
    expect(html).toContain('</ol>');
  });

  it('should convert blockquotes', () => {
    const headings: CollectedHeading[] = [];
    const md = '> This is a quote';
    const html = convertMarkdownToHtml(md, headings);
    expect(html).toContain('<blockquote>');
    expect(html).toContain('This is a quote');
  });

  it('should convert horizontal rules', () => {
    const headings: CollectedHeading[] = [];
    const md = 'before\n\n---\n\nafter';
    const html = convertMarkdownToHtml(md, headings);
    expect(html).toContain('<hr>');
  });

  it('should convert markdown tables', () => {
    const headings: CollectedHeading[] = [];
    const md = '| Name | Value |\n|------|-------|\n| foo | bar |';
    const html = convertMarkdownToHtml(md, headings);
    expect(html).toContain('<table>');
    expect(html).toContain('<th>Name</th>');
    expect(html).toContain('<td>foo</td>');
    expect(html).toContain('</table>');
  });

  it('should wrap plain text in paragraph tags', () => {
    const headings: CollectedHeading[] = [];
    const html = convertMarkdownToHtml('Hello world', headings);
    expect(html).toContain('<p>Hello world</p>');
  });

  it('should not wrap block elements in paragraphs', () => {
    const headings: CollectedHeading[] = [];
    const html = convertMarkdownToHtml('## Heading', headings);
    expect(html).not.toContain('<p><h2');
  });

  it('should handle empty input', () => {
    const headings: CollectedHeading[] = [];
    const html = convertMarkdownToHtml('', headings);
    expect(html).toBe('');
    expect(headings).toHaveLength(0);
  });
});
