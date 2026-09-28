# Deployment assets

`compose.demo.yml` packages the synthetic local demo in a non-root, read-only container with a loopback-only published port, dropped Linux capabilities, and a health check. It does not enable production mode or accept real company data.

Run it only on a development workstation:

```powershell
docker compose -f deployment/compose.demo.yml up --build
```

The application rejects `CAUSE_AI_ENV=production` by design. Before a separately engineered production service is released, run:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m cause_ai.preflight
```

The preflight requires PostgreSQL, OIDC, secure sessions, HTTPS ingress, observability, evidence object storage, durable workers, backups, data governance, and security release controls.
