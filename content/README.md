# Content layer

This directory holds the **content layer**: static material the engine reads at
runtime, so a deployment can retune behaviour without editing Python. Anything
here overrides the built-in default of the same name; nothing here is required,
and the engine runs with the directory missing entirely.

## What exists today

```
content/
├── memory/seed/agentos.json   # live — cold-start memories, read by `aos memory seed`
└── policies/                  # empty — every threshold falls back to policy.py defaults
```

`memory/seed/` matters more than it looks. A fresh store holds no memories, so
recall is empty, so no candidate is ever proposed, so nothing downstream of cold
start is observable. `aos memory seed` loads these files; ids are explicit and
stable, so re-seeding is a no-op and a human's refinement is never reverted. The
shipped entries are facts verified in this repository, so a reviewer can check
one against the code rather than take it on faith.

## Policies

`content/policies/<name>.json` overrides, key by key, the defaults in
`aos/core/memory/policy.py`. Recognised names:

| File | Controls |
|---|---|
| `retrieval.json` | recall weights and the quality bonus |
| `decay.json` | recency windows and the decay floor |
| `promotion.json` | what the learning gate may auto-approve |
| `rejection.json` | what the gate refuses, and when it opens a review |
| `injection.json` | the `<agent_os>` block budget: `max_chars`, `max_items`, `max_body_chars`, `hypothesis_max_items` |

The merge is shallow (`defaults.update(file)`), so a nested value must be written
**complete**: a `retrieval.json` carrying only part of `quality_bonus_weights`
replaces the whole table and zeroes the weights you left out. Unknown keys are
ignored rather than rejected, which keeps an old file from crashing a new
engine — but it also means a typo'd key silently does nothing, so confirm a
tweak landed instead of assuming it did.

## Routing and roles

Those are **not** under `content/` by default; they are bundled in
`aos/core/routing/registry/`. Two different override semantics apply, and
confusing them loses entries silently:

| File | Behaviour |
|---|---|
| `content/routing/roles.json` | **merged** over the built-in catalog — safe to add a few roles |
| `content/routing/taxonomy-map.json` | **merged** over the built-in map |
| `content/routing/registry.json` | **replaces** the bundled registry file entirely |
| `AOS_REGISTRY_PATH` | **replaces** it, and wins over `content/routing/` |

A `registry.json` here must therefore be complete; a partial one does not add to
the built-in vocabulary, it becomes the whole vocabulary.

## Skills are not a source here

`AOS_SKILLS_DIR` resolves to `content/skills`, and the engine reads nothing from
it. Skills belong to the host (OpenCode's own directory), and Agent OS observes
which skill a task used and whether it helped — it does not store or distribute
skill definitions. A `content/skills/` directory here would be a projection of
the host's inventory at best, never a second source of truth, and nothing reads
it today.

## Formats

JSON only. The engine is dependency-free and does not parse YAML, so a format
the standard library cannot read is a format this project does not use.
