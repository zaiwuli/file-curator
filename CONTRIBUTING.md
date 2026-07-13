# Contributing

## Language

Source code, public contracts, database fields, processor identifiers, error codes, and logs must be English. User-facing text must use translation keys and include an English fallback.

## Module boundaries

- Domain modules cannot import API route modules.
- Filesystem mutation is allowed only in the execution module.
- Processors are deterministic and cannot mutate the filesystem.
- Plans are immutable after confirmation.
- Safety checks cannot be disabled by workflow configuration.

## Changes

Every processor change must include tests for its manifest, dependencies, deterministic result, decision evidence, and extension preservation. Every execution change must include failure and rollback coverage.

