# Deploying the Qvalento version of the Google Analytics MCP server

This branch (`qvalento`) is a fork of [googleanalytics/google-analytics-mcp](https://github.com/googleanalytics/google-analytics-mcp), based on Google's release **1.1.0**. It adds Qvalento's own read-only tools, which live in `analytics_mcp/tools/admin/setup.py` and are registered in `analytics_mcp/coordinator.py`.

The server runs on Cloud Run and is connected to Claude as a custom connector. Each person signs in with their own Google account, so they only see the GA4 properties they already have access to.

## Where everything lives

| What | Value |
| --- | --- |
| Google Cloud project | `qvalento-mcp` |
| Region | `europe-north1` |
| Cloud Run service | `google-analytics-mcp` |
| Service URL | `https://google-analytics-mcp-929514887029.europe-north1.run.app` |
| Connector URL in Claude | `https://google-analytics-mcp-929514887029.europe-north1.run.app/mcp` |
| Image repository | `europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp` |
| Runtime service account | `google-analytics-mcp@qvalento-mcp.iam.gserviceaccount.com` |
| OAuth client secret | Secret Manager: `google-analytics-mcp-oauth-secret` |
| Git branch that gets deployed | `qvalento` |

The service's settings (environment variables, the secret, the service account, and one instance minimum and maximum) are stored on the Cloud Run service itself. A normal deploy only swaps the image, so none of those settings need to be repeated.

## One-time setup on your computer

Deploying from Cursor's terminal needs the Google Cloud CLI. Install it from https://cloud.google.com/sdk/docs/install, then sign in and set the project:

```bash
gcloud auth login
gcloud config set project qvalento-mcp
```

If you'd rather not install it, use Cloud Shell instead (see "Deploying from Cloud Shell" below). The commands are the same.

All commands in this file are written on one line so they work in both PowerShell (Windows) and bash/zsh (Mac, Linux, Cloud Shell).

## Deploying a change

### 1. Check the change locally

Every deploy signs everyone out of the connector (see "Important to know"), so catch mistakes before deploying. The first time, create a virtual environment in the repo folder (`.venv` is already in `.gitignore`):

```bash
python -m venv .venv
```

Activate it with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Mac, then install the project and list the tools the server will offer:

```bash
pip install -e .
python -c "import analytics_mcp.coordinator as c; print(sorted(c._READ_ONLY_TOOL_NAMES))"
```

If the command prints the list of tools, including any new one, the code imports correctly and the tool is registered. An error here would also have broken the deployed server.

### 2. Commit and push

`gcloud builds submit` uploads the folder exactly as it is on disk, including uncommitted changes. Commit and push first, so that what runs in Cloud Run always matches what's in git. `git status` should show nothing to commit.

### 3. Choose the next image tag

Use the format `<Google release>-qv<number>`, for example `1.1.0-qv2`, and take the next number after the latest entry in the deploy log at the bottom of this file. To see which image is live right now:

```bash
gcloud run services describe google-analytics-mcp --region europe-north1 --project qvalento-mcp --format="value(spec.template.spec.containers[0].image)"
```

### 4. Build the image

Replace `1.1.0-qv2` with your tag:

```bash
gcloud builds submit --tag europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp:1.1.0-qv2 --project qvalento-mcp
```

### 5. Deploy it

```bash
gcloud run deploy google-analytics-mcp --image europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp:1.1.0-qv2 --region europe-north1 --project qvalento-mcp
```

### 6. Check that the server responds

```bash
curl -s https://google-analytics-mcp-929514887029.europe-north1.run.app/.well-known/oauth-authorization-server
curl -s -i -X POST -d "{}" https://google-analytics-mcp-929514887029.europe-north1.run.app/mcp
```

The first command should show `"issuer"` as the service URL. The first line of the second command's output should say `401`, which means the server is up and rejecting requests that don't carry a Google token. In Windows PowerShell, type `curl.exe` instead of `curl`.

### 7. Reconnect and test in Claude

Open Settings → Connectors in Claude and connect the Google Analytics connector again. Then start a new chat and try the changed tool, for example: "Show me the setup for Axel Arigato GA4." Let colleagues know they need to reconnect too.

### 8. Add a line to the deploy log

Record the tag, date, commit and what changed at the bottom of this file, then commit and push. This is what you use to roll back.

## Deploying from Cloud Shell

Open Cloud Shell in the Google Cloud console. The first time, clone the branch:

```bash
git clone --branch qvalento https://github.com/qvalinlar/google-analytics-mcp.git qv-analytics-mcp
```

After that, update the copy before each deploy:

```bash
cd ~/qv-analytics-mcp && git pull
```

Then run steps 4 to 8 above from that folder.

## Rolling back

Deploy the previous tag from the deploy log. For example, to go back to Google's original 1.1.0 image:

```bash
gcloud run deploy google-analytics-mcp --image europe-north1-docker.pkg.dev/qvalento-mcp/mcp-servers/google-analytics-mcp:1.1.0 --region europe-north1 --project qvalento-mcp
```

Everyone has to reconnect afterwards, just as after a normal deploy.

## Adding a new tool

Write the tool as an `async` function in `analytics_mcp/tools/admin/setup.py`, using `get_property_setup` as the model. Then register it in `analytics_mcp/coordinator.py` with two lines: an import next to the existing `from analytics_mcp.tools.admin.setup import ...` line, and `FunctionTool(your_function),` in the `read_only_tools` list.

The function's docstring is what Claude reads to decide when to use the tool. Start with what the tool returns, then say when to use it, and describe each argument.

Follow the checks in step 1 before deploying.

## Conventions for changes

These apply to people and to Cursor's agent working in this repo.

**Keep Qvalento code separate from Google's code.** Put it in `setup.py` or in new files under `analytics_mcp/`, and touch Google's files only to register tools in `coordinator.py`. That keeps updates to new Google releases down to a few lines. New code must live under `analytics_mcp/`, because the Docker build (`.dockerignore`) only includes that folder plus `pyproject.toml`, `README.md` and `LICENSE`. A new Python dependency goes in `pyproject.toml`.

**Keep the tools read-only.** They must not create, change or delete anything in Google Analytics.

**Always use the existing API clients.** Create clients with `create_admin_api_client()`, `create_admin_alpha_api_client()` or `create_data_api_client()` from `analytics_mcp/tools/client.py`. These use the signed-in person's own Google token. Never create credentials or service-account clients in a tool.

**Keep one failing setting from breaking a whole tool.** Wrap each lookup in `_safe(...)` so a setting the person isn't allowed to read shows up as an error while the rest of the result still comes back.

**Never return secret values.** For example, return the names of Measurement Protocol secrets, never the secret values themselves.

**Prefer one tool that answers a whole question over many small ones.** For example, `get_property_setup` returns all of a property's settings in one call. Every tool's description takes up room in Claude's context, and Claude chooses tools more reliably when there are fewer of them.

## Updating to a new Google release

When Google publishes a new release (for example 1.2.0), move the Qvalento commits onto it from Cursor's terminal. First check whether the `upstream` remote exists:

```bash
git remote -v
```

If no line starts with `upstream`, add it:

```bash
git remote add upstream https://github.com/googleanalytics/google-analytics-mcp.git
```

Then move the branch onto the new release and push:

```bash
git fetch upstream --tags
git checkout qvalento
git rebase --onto 1.2.0 1.1.0
git push --force-with-lease
```

If the rebase stops with a conflict, it will be in the two registration lines in `coordinator.py`. Keep both Google's new lines and the Qvalento lines, then run `git rebase --continue`.

Before deploying, read Google's release notes and the "Deploy with Docker & Google Cloud Run" section of `README.md` for new environment variables or changed deploy steps. Then update "based on Google's release" at the top of this file and the rebase command above, run the step 1 checks, and deploy with a new tag series such as `1.2.0-qv1`.

## Important to know

**Every deploy or restart signs everyone out.** This version of the server keeps sign-ins in memory. Deploy at a quiet time and tell colleagues to reconnect.

**Keep the service at exactly one instance.** The minimum and maximum are both 1. More than one instance would split sign-ins across instances, and zero would sign everyone out whenever the service goes idle.

**Write tools are off.** Setting `ANALYTICS_MCP_ALLOW_WRITE=true` would enable Google's write tools and ask everyone for edit access to Google Analytics. Decide that deliberately before changing it.

**This repository is public.** Never commit secrets. The OAuth client secret belongs in Secret Manager only.

## Deploy log

| Image tag | Date | Commit | What changed |
| --- | --- | --- | --- |
| `1.1.0` | 2026-11-19 | Google's release | Original deploy of Google's release 1.1.0 |
| `1.1.0-qv1` | 2026-11-19 | `1d8bbe7` | Added `get_property_setup` |
