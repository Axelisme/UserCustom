# config-single-source source map

Call sites that currently read configuration, and which loader each one uses today:

- `config/legacy_loader.py:LegacyConfigLoader.load` — the deletion target named in
  `tickets/config-single-source.md`.
- `config/loader.py:ConfigLoader.load` — the surviving single owner.
- `app/startup.py:bootstrap` — the only call site that currently imports the legacy loader
  directly; it must switch to `ConfigLoader`.
