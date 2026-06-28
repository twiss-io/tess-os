/**
 * SEO Generator — Unit Tests
 *
 * Tests Schema.org JSON-LD generation for articles and FAQ pages.
 */

import { describe, it, expect } from 'vitest';
import { generateSchemaJson } from '../../scripts/content/seo-generator.js';
import type { ArticleConfig, ContentConfig } from '../../scripts/content/types.js';

const config: ContentConfig = {
  siteUrl: 'https://example.com',
  siteName: 'My Site',
  author: 'Test Author',
  outputDir: 'public/articles',
  categories: ['All'],
  articles: [],
};

const baseArticle: ArticleConfig = {
  id: 'test',
  published: true,
  mdSource: 'content/test.md',
  htmlOutput: 'public/articles/test/index.html',
  title: 'Test Article',
  description: 'A test article',
  url: 'https://example.com/articles/test/',
  datePublished: '2026-01-01',
};

describe('generateSchemaJson', () => {
  it('should generate valid JSON-LD script tags', () => {
    const result = generateSchemaJson(baseArticle, config);
    expect(result).toContain('<script type="application/ld+json">');
    expect(result).toContain('</script>');
  });

  it('should include article metadata', () => {
    const result = generateSchemaJson(baseArticle, config);
    expect(result).toContain('"@type": "Article"');
    expect(result).toContain('"headline": "Test Article"');
    expect(result).toContain('"description": "A test article"');
  });

  it('should include author info', () => {
    const result = generateSchemaJson(baseArticle, config);
    expect(result).toContain('"name": "Test Author"');
  });

  it('should include parent link when parent is defined', () => {
    const withParent = { ...baseArticle, parent: { title: 'Parent', url: '/articles/' } };
    const result = generateSchemaJson(withParent, config);
    expect(result).toContain('https://example.com/articles/');
  });

  it('should include FAQ schema when faqSchema is defined', () => {
    const withFaq = {
      ...baseArticle,
      faqSchema: [{ question: 'What is this?', answer: 'A test.' }],
    };
    const result = generateSchemaJson(withFaq, config);
    expect(result).toContain('"@type": "FAQPage"');
    expect(result).toContain('What is this?');
    expect(result).toContain('A test.');
  });

  it('should not include FAQ schema when faqSchema is empty', () => {
    const withEmptyFaq = { ...baseArticle, faqSchema: [] };
    const result = generateSchemaJson(withEmptyFaq, config);
    expect(result).not.toContain('"@type": "FAQPage"');
  });
});
