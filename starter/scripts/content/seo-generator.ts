/**
 * Content Builder — SEO & Schema.org Generator
 *
 * Generates JSON-LD structured data for articles and FAQ pages.
 */

import type { ArticleConfig, ContentConfig } from './types.js';

export function generateSchemaJson(article: ArticleConfig, config: ContentConfig): string {
  const schema: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: article.title,
    description: article.description,
    url: article.url,
    datePublished: article.datePublished,
    dateModified: article.datePublished,
    author: { '@type': 'Person', name: config.author, url: config.siteUrl },
    publisher: { '@type': 'Person', name: config.author },
    keywords: article.keywords ?? [],
    isPartOf: article.parent
      ? { '@type': 'Article', url: `${config.siteUrl}${article.parent.url}` }
      : { '@type': 'WebSite', name: config.siteName, url: config.siteUrl },
  };

  let block = `    <script type="application/ld+json">\n    ${JSON.stringify(schema, null, 4)}\n    </script>`;

  if (article.faqSchema && article.faqSchema.length > 0) {
    const faqSchema = {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: article.faqSchema.map((faq) => ({
        '@type': 'Question',
        name: faq.question,
        acceptedAnswer: { '@type': 'Answer', text: faq.answer },
      })),
    };
    block += `\n    <script type="application/ld+json">\n    ${JSON.stringify(faqSchema, null, 4)}\n    </script>`;
  }

  return block;
}
