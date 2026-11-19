---
name: deploy-qvalento
description: Deploys committed changes on the qvalento branch of the Google Analytics MCP server to Cloud Run (project qvalento-mcp, service google-analytics-mcp). Use only when the user explicitly asks to deploy, release or roll out a change to the GA4 MCP server.
disable-model-invocation: true
---

# Deploy the Qvalento GA4 MCP server

`docs/DEPLOY_QVALENTO.md` is the source of truth for this process. If it disagrees with this skill, follow the document and tell the user about the mismatch.

This skill only deploys a new image. Never change service settings (environment variables, secret, service account, instance counts, CPU, memory, billing mode) as part of a deploy; if the user wants that, stop and discuss it separately.

## Fixed values

| What | Value |
| --- | --- |
| Project | `qvalento-mcp` |
| Region | `europe-north1` |
| Service | `google-analytics-mcp` |
| Image repository | `europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp` |
| Service URL | `https://google-analytics-mcp-929514887029.europe-north1.run.app` |
| Branch | `qvalento` |

The user's shell is PowerShell on Windows: use `curl.exe`, not `curl`, and keep every command on one line.

## Workflow

Copy this checklist and track progress:

```
- [ ] 1. Preflight checks
- [ ] 2. Local import check
- [ ] 3. Choose the image tag
- [ ] 4. Confirm with the user
- [ ] 5. Build the image
- [ ] 6. Deploy
- [ ] 7. Verify the live server
- [ ] 8. Update the deploy log
```

### 1. Preflight checks

Run and stop with an explanation if any check fails:

```powershell
git branch --show-current; git status --porcelain; git fetch origin; git status -sb
gcloud auth list --filter=status:ACTIVE --format="value(account)"
```

- The branch must be `qvalento`.
- `git status --porcelain` must be empty. `gcloud builds submit` uploads the folder as it is on disk, so uncommitted changes would be deployed without being in git. Offer to commit them (with a message the user approves) rather than deploying them uncommitted.
- The branch must not be ahead of or behind `origin/qvalento`. If it's ahead, push first.
- If `gcloud` reports an auth error, ask the user to run `gcloud auth login` in their own terminal (it needs a browser), then continue.

### 2. Local import check

Create the virtual environment on first use, then confirm the server imports and list the tools:

```powershell
if (-not (Test-Path .venv)) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install -q -e .
.venv\Scripts\python.exe -c "import analytics_mcp.coordinator as c; print(sorted(c._READ_ONLY_TOOL_NAMES))"
```

Any error here would also break the deployed server: stop and fix it. Check that new tools appear in the list.

### 3. Choose the image tag

Get the live image:

```powershell
gcloud run services describe google-analytics-mcp --region europe-north1 --project qvalento-mcp --format="value(spec.template.spec.containers[0].image)"
```

Tags use the format `<Google release>-qv<number>`, for example `1.1.0-qv2`. Read the deploy log at the bottom of `docs/DEPLOY_QVALENTO.md`:

- Normally use the next number after the latest log entry.
- If the latest log entry's tag is not the live image and has no commit filled in, it was logged but never deployed: reuse that tag and fill in its row in step 8 instead of adding a new one.
- Check the tag doesn't already exist, so an old image is never overwritten:

```powershell
gcloud artifacts docker tags list europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp --project qvalento-mcp --format="value(tag)"
```

### 4. Confirm with the user

Deploying signs everyone out of the connector within about an hour (sign-ins are held in memory). Before building, tell the user the tag, the commit (`git log --oneline -1`), the live image it replaces, and the changes since the last deploy (`git log --oneline <last deployed commit>..HEAD`). Ask them to confirm with AskQuestion. Don't continue without a clear yes.

### 5. Build the image

```powershell
gcloud builds submit --tag europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp:<TAG> --project qvalento-mcp
```

Builds take a few minutes; run with a long timeout and wait for it. If the build fails, show the relevant error and stop. Nothing has changed on the live service at this point.

### 6. Deploy

```powershell
gcloud run deploy google-analytics-mcp --image europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp:<TAG> --region europe-north1 --project qvalento-mcp
```

### 7. Verify the live server

```powershell
curl.exe -s https://google-analytics-mcp-929514887029.europe-north1.run.app/.well-known/oauth-authorization-server
curl.exe -s -i -X POST -d "{}" https://google-analytics-mcp-929514887029.europe-north1.run.app/mcp
```

- The first must return JSON whose `issuer` is the service URL.
- The second must start with `HTTP/1.1 401 Unauthorized`.
- Re-run the step 3 describe command and confirm the live image is the new tag.

If any check fails, tell the user and offer to roll back to the previous tag from the deploy log:

```powershell
gcloud run deploy google-analytics-mcp --image europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp:<PREVIOUS TAG> --region europe-north1 --project qvalento-mcp
```

### 8. Update the deploy log

Add (or fill in) the row in the deploy log table at the bottom of `docs/DEPLOY_QVALENTO.md`: tag, today's date (YYYY-MM-DD), short commit hash, and a plain-language summary of what changed. Then commit only that file with the message `Deploy log: <TAG>` and push.

## Finish

Tell the user:

- the tag that is now live and the commit it was built from,
- that the health checks passed,
- that they and their colleagues need to reconnect the connector in Claude (Settings → Connectors) and should start a new chat to test the change.
