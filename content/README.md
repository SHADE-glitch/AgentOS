# Content layer (deferred)

This directory holds the **content layer** of Agent OS: the static material
the engine reads at runtime. It is intentionally empty for now — the content
layer was removed and will be rebuilt under a new design.

The engine ships built-in defaults so it works with an empty content layer;
anything here overrides those defaults.

## Expected layout

```
content/
├── skills/       # role playbooks (SKILL.md per role)
├── memory/       # seed memories (optional; the live store is store/aos.db)
├── knowledge/    # domain reference material
├── policies/     # learning thresholds (JSON)
│   ├── promotion.json
│   ├── rejection.json
│   └── decay.json
└── routing/
    └── taxonomy-map.json   # abstract skill id -> concrete role
```

## Overrides

Every path is overridable via environment variables (see `aos/config.py`):
`AOS_CONTENT_DIR`, `AOS_SKILLS_DIR`, `AOS_MEMORY_DIR`, `AOS_KNOWLEDGE_DIR`,
`AOS_POLICIES_DIR`.

## Formats

- **Policies / routing maps**: JSON (the engine is dependency-free and does
  not parse YAML).
- **Skills**: Markdown with a JSON metadata block, once the content layer is
  rebuilt.
