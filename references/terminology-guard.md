# Terminology Guard

The Terminology Guard is the release wording gate for Wallstreet Tieling. It
keeps public documentation, comments, configuration, demo pages, and release
copy aligned with the project's professional boundary:

- public, licensed, or user-authorized sources;
- provenance before narrative;
- high-sensitivity leads described as leads, not confirmed facts;
- consent-based session wording;
- challenge-response wording for verification flows;
- source-admission wording for non-standard providers.

It is a project hygiene tool that makes the public repo easier to review,
publish, and maintain.

## Commands

```bash
python bin/terminology_guard.py --list-rules
python bin/terminology_guard.py --format json
python bin/terminology_guard.py --fix
python bin/terminology_guard.py --text "paste one sentence here"
```

Default scan scope excludes generated, private, and self-referential locations
such as `.git`, `.colab`, `output`, `deliverables`, and the guard's own rule
definition. The rule table reports legacy expression families rather than
printing every raw legacy phrase in public logs, which keeps the checker from
becoming its own false-positive source.

## Release Gate

Recommended release checks:

```bash
python bin/terminology_guard.py --fail-on error
python -m pytest tests/unit/test_release_hygiene.py tests/unit/test_terminology_guard.py -q
```

Use `--fix` before a public release branch. For source files, the automatic
fixer only rewrites comment-like lines so runtime protocol names and API
contracts are not changed accidentally.

The release hygiene gate also checks that public branches do not track local
runtime artifacts such as collaboration databases, browser profiles,
session-state files, local datasource credentials, or stale portal version
markers. Local/private deployments can keep those files outside the public Git
index.
