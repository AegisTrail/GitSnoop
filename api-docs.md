# GitSnoop API

GitSnoop can run as an HTTP service for environments where the TUI is not practical or where repository scans need to be triggered programmatically.

The API is only started when the CLI is launched with `--api`. If no port is provided, GitSnoop listens on `6969`.

## Start the server

```bash
gitsnoop --api
```

Run on a custom port:

```bash
gitsnoop --api --port 8080
```

## Base URL

When running locally with the default configuration:

```text
http://127.0.0.1:6969
```

## OpenAPI specification

A standalone OpenAPI file is included in this repository:

```text
openapi.yaml
```

This file can be imported into tools such as Swagger UI, Postman, Insomnia, or Stoplight.

## Endpoints

### `GET /health`

Simple readiness endpoint.

Example request:

```bash
curl http://127.0.0.1:6969/health
```

Example response:

```json
{
  "status": "ok",
  "service": "gitsnoop"
}
```

### `POST /scan`

Scans a remote Git repository or a local repository path and returns the collected author email metadata.

Example request for a remote repository:

```bash
curl -X POST http://127.0.0.1:6969/scan \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "https://github.com/example/project.git",
    "exclude_github_noreply": false,
    "sort_mode": "commits",
    "skip_breach_checks": false,
    "include_breach_details": true
  }'
```

Example request for a local repository:

```bash
curl -X POST http://127.0.0.1:6969/scan \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "/absolute/path/to/local/repo",
    "exclude_github_noreply": true,
    "sort_mode": "recent",
    "skip_breach_checks": true,
    "include_breach_details": false
  }'
```

Request body format:

```json
{
  "repo": "https://github.com/example/project.git",
  "exclude_github_noreply": false,
  "sort_mode": "commits",
  "skip_breach_checks": false,
  "include_breach_details": true
}
```

Request fields:

- `repo`: Required. Git repository URL or local filesystem path.
- `exclude_github_noreply`: Optional. Removes GitHub noreply addresses from the returned result set.
- `sort_mode`: Optional. One of `commits`, `recent`, `name`, `email`, or `domain`.
- `skip_breach_checks`: Optional. When `true`, GitSnoop skips breach lookups entirely.
- `include_breach_details`: Optional. When `false`, the response omits breach metadata from each record.

Successful response:

```json
{
  "repository": "project",
  "repo_source": "https://github.com/example/project.git",
  "count": 2,
  "breached_count": 1,
  "results": [
    {
      "name": "Alice Example",
      "email": "alice@example.com",
      "domain": "example.com",
      "commit_count": 42,
      "first_seen": "2023-01-02",
      "last_seen": "2026-05-12",
      "is_breached": true,
      "breach_count": 1,
      "breach_error": null,
      "breaches": [
        {
          "title": "Example Breach",
          "domain": "example.com",
          "breach_date": "2024-06-01",
          "pwn_count": 1000,
          "data_classes": ["Email addresses", "Passwords"]
        }
      ]
    }
  ]
}
```

Error response:

If cloning or reading the repository fails, the API returns `400 Bad Request` with the Git error message in the `detail` field.

## Notes

- The API uses the same repository scanning logic as the CLI.
- Repository scans clone into a temporary directory for processing.
- Local repository paths are accepted as long as the API process can access them.
- Interactive TUI mode is not used when `--api` is enabled.
- When the server is running, FastAPI also exposes the live schema endpoints at `/openapi.json` and `/docs`.
