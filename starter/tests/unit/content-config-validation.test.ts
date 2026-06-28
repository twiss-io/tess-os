/**
 * Content Config Validation — Unit Tests
 *
 * Tests the Zod schema validation for content.config.json.
 */

import { describe, it, expect } from 'vitest';
import { ContentConfigSchema, ArticleConfigSchema } from '../../scripts/content/types.js';

const validArticle = {
  id: 'test-article',
  published: true,
  mdSource: 'content/test.md',
  htmlOutput: 'public/articles/test/index.html',
  title: 'Test Article',
  description: 'A test article for validation',
  url: 'https://example.com/articles/test/',
  datePublished: '2026-01-01',
};

const validConfig = {
  siteUrl: 'https://example.com',
  siteName: 'My Site',
  author: 'Test Author',
  outputDir: 'public/articles',
  categories: ['All', 'Guides'],
  articles: [validArticle],
};

describe('ArticleConfigSchema', () => {
  it('should accept a valid article', () => {
    const result = ArticleConfigSchema.safeParse(validArticle);
    expect(result.success).toBe(true);
  });

  it('should reject missing id', () => {
    const result = ArticleConfigSchema.safeParse({ ...validArticle, id: '' });
    expect(result.success).toBe(false);
  });

  it('should reject missing title', () => {
    const result = ArticleConfigSchema.safeParse({ ...validArticle, title: '' });
    expect(result.success).toBe(false);
  });

  it('should reject missing description', () => {
    const result = ArticleConfigSchema.safeParse({ ...validArticle, description: '' });
    expect(result.success).toBe(false);
  });

  it('should reject invalid url', () => {
    const result = ArticleConfigSchema.safeParse({ ...validArticle, url: 'not-a-url' });
    expect(result.success).toBe(false);
  });

  it('should reject missing mdSource', () => {
    const result = ArticleConfigSchema.safeParse({ ...validArticle, mdSource: '' });
    expect(result.success).toBe(false);
  });

  it('should reject missing htmlOutput', () => {
    const result = ArticleConfigSchema.safeParse({ ...validArticle, htmlOutput: '' });
    expect(result.success).toBe(false);
  });

  it('should accept optional fields', () => {
    const withOptionals = {
      ...validArticle,
      titleHtml: 'Test <span>Article</span>',
      subtitle: 'A subtitle',
      bannerImage: '/images/banner.webp',
      bannerAlt: 'Banner alt text',
      category: 'Guides',
      tags: ['test', '2026'],
      keywords: ['test', 'article'],
      sidebar: true,
      parent: { title: 'Parent', url: '/articles/' },
      children: [{ title: 'Child 1', url: '/articles/child-1/' }],
      childrenLabel: 'Related',
      tocLevel: 2,
      tocFilter: '.*',
      faqSchema: [{ question: 'What?', answer: 'This.' }],
    };
    const result = ArticleConfigSchema.safeParse(withOptionals);
    expect(result.success).toBe(true);
  });

  it('should reject children with empty title', () => {
    const withBadChild = {
      ...validArticle,
      children: [{ title: '', url: '/articles/child/' }],
    };
    const result = ArticleConfigSchema.safeParse(withBadChild);
    expect(result.success).toBe(false);
  });

  it('should reject faqSchema with empty question', () => {
    const withBadFaq = {
      ...validArticle,
      faqSchema: [{ question: '', answer: 'Answer' }],
    };
    const result = ArticleConfigSchema.safeParse(withBadFaq);
    expect(result.success).toBe(false);
  });

  it('should reject tocLevel outside 1-6', () => {
    const result = ArticleConfigSchema.safeParse({ ...validArticle, tocLevel: 7 });
    expect(result.success).toBe(false);
  });
});

describe('ContentConfigSchema', () => {
  it('should accept a valid config', () => {
    const result = ContentConfigSchema.safeParse(validConfig);
    expect(result.success).toBe(true);
  });

  it('should reject invalid siteUrl', () => {
    const result = ContentConfigSchema.safeParse({ ...validConfig, siteUrl: 'not-a-url' });
    expect(result.success).toBe(false);
  });

  it('should reject missing siteName', () => {
    const result = ContentConfigSchema.safeParse({ ...validConfig, siteName: '' });
    expect(result.success).toBe(false);
  });

  it('should reject missing author', () => {
    const result = ContentConfigSchema.safeParse({ ...validConfig, author: '' });
    expect(result.success).toBe(false);
  });

  it('should reject missing outputDir', () => {
    const result = ContentConfigSchema.safeParse({ ...validConfig, outputDir: '' });
    expect(result.success).toBe(false);
  });

  it('should accept empty articles array', () => {
    const result = ContentConfigSchema.safeParse({ ...validConfig, articles: [] });
    expect(result.success).toBe(true);
  });

  it('should reject invalid article within config', () => {
    const result = ContentConfigSchema.safeParse({
      ...validConfig,
      articles: [{ ...validArticle, id: '' }],
    });
    expect(result.success).toBe(false);
  });
});
