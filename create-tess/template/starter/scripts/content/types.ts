/**
 * Content Builder — Types & Validation
 *
 * Shared types and Zod schemas for the content build system.
 */

import { z } from 'zod';

// ---------------------------------------------------------------------------
// Zod Schemas (runtime validation)
// ---------------------------------------------------------------------------

const SidebarChildSchema = z.object({
  title: z.string().min(1),
  url: z.string().min(1),
  group: z.string().optional(),
});

const FaqItemSchema = z.object({
  question: z.string().min(1),
  answer: z.string().min(1),
});

const ArticleConfigSchema = z.object({
  id: z.string().min(1, 'Article id is required'),
  published: z.boolean(),
  mdSource: z.string().min(1, 'mdSource path is required'),
  htmlOutput: z.string().min(1, 'htmlOutput path is required'),
  title: z.string().min(1, 'title is required'),
  titleHtml: z.string().optional(),
  subtitle: z.string().optional(),
  description: z.string().min(1, 'description is required'),
  bannerImage: z.string().optional(),
  bannerAlt: z.string().optional(),
  url: z.string().url('url must be a valid URL'),
  datePublished: z.string().min(1, 'datePublished is required'),
  category: z.string().optional(),
  tags: z.array(z.string()).optional(),
  keywords: z.array(z.string()).optional(),
  sidebar: z.boolean().optional(),
  parent: z.object({ title: z.string(), url: z.string() }).optional(),
  children: z.array(SidebarChildSchema).optional(),
  childrenLabel: z.string().optional(),
  tocLevel: z.number().int().min(1).max(6).optional(),
  tocFilter: z.string().optional(),
  faqSchema: z.array(FaqItemSchema).optional(),
});

const ContentConfigSchema = z.object({
  siteUrl: z.string().url('siteUrl must be a valid URL'),
  siteName: z.string().min(1, 'siteName is required'),
  author: z.string().min(1, 'author is required'),
  outputDir: z.string().min(1, 'outputDir is required'),
  categories: z.array(z.string()),
  articles: z.array(ArticleConfigSchema),
});

export { ContentConfigSchema, ArticleConfigSchema };

// ---------------------------------------------------------------------------
// TypeScript interfaces (inferred from Zod for zero drift)
// ---------------------------------------------------------------------------

export type SidebarChild = z.infer<typeof SidebarChildSchema>;
export type ArticleConfig = z.infer<typeof ArticleConfigSchema>;
export type ContentConfig = z.infer<typeof ContentConfigSchema>;

export interface CollectedHeading {
  level: number;
  id: string;
  text: string;
}
