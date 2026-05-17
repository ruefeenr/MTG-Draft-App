# Claro Calendar Path Deployment

Use `next.config.ts` from this directory in the Claro Calendar repository before building it for the shared domain.

The important setting is:

```ts
basePath: "/claro"
```

After copying the file to `/opt/claro-calendar/next.config.ts`, rebuild and restart:

```bash
npm run build
sudo systemctl restart claro-calendar
```

In Supabase, configure allowed redirect URLs for the path-based deployment, for example:

```text
https://example.com/claro/**
```
