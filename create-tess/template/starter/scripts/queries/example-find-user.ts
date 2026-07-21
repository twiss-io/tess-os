/**
 * Example query: Find a user by email
 *
 * Usage: npx tsx scripts/db-query.ts example-find-user <email>
 *
 * This is a TEST query — not production code.
 */

import type { StrictDB } from 'strictdb';

export default {
  name: 'example-find-user',
  description: 'Look up a user by email address',

  async run(db: StrictDB, args: string[]): Promise<void> {
    const email = args[0];
    if (!email) {
      console.error('  Usage: example-find-user <email>');
      process.exit(1);
    }

    const user = await db.queryOne('users', { email });

    if (!user) {
      console.log(`  No user found with email: ${email}`);
      return;
    }

    console.log('  Found user:');
    console.log(JSON.stringify(user, null, 2));
  },
};
