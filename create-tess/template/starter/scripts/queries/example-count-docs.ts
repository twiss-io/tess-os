/**
 * Example query: Count documents in a collection
 *
 * Usage: npx tsx scripts/db-query.ts example-count-docs <collection>
 *
 * This is a TEST query — not production code.
 */

import type { StrictDB } from 'strictdb';

export default {
  name: 'example-count-docs',
  description: 'Count documents in any collection',

  async run(db: StrictDB, args: string[]): Promise<void> {
    const collection = args[0];
    if (!collection) {
      console.error('  Usage: example-count-docs <collection>');
      process.exit(1);
    }

    const total = await db.count(collection);
    console.log(`  Collection "${collection}" has ${total} documents.`);
  },
};
