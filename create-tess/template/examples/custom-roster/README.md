# Custom roster reference kit

This directory is portable reference material for drafting a small persona and
squad description in another project. It is not a Tess OS configuration
directory, has no runtime effect, and is not a source of dispatchable agents.

Copy the files somewhere outside this repository before adapting them to the
documented format of the host tool you use. Keep the kit as descriptive source
material: it defines no executable behavior, permissions, review state,
credential access, or release state.

## Contents

- `identity.template.md` — a concise role and boundary profile.
- `personality.template.md` — a working-style profile.
- `soul.template.md` — durable purpose and operating principles.
- `squad.template.json` — a reference-shaped collection that connects the
  three profiles for each member.

Every angle-bracket value is a placeholder. The JSON file is intentionally a
reference template rather than an input for Tess OS tooling.

## Safe use

1. Copy the kit to a project-specific documentation area.
2. Replace placeholders with descriptive, least-privilege role information.
3. Apply the separate, documented configuration process of the host tool if
   you decide to make a persona available there.

Nothing in this directory changes a running roster. Tess OS does not read this
directory while selecting, dispatching, or maintaining its curated squads.
