# Installation and launch

[简体中文](INSTALL.zh-CN.md) · [Home](../README.md) · [Complete features](FEATURES.md)

## Requirements

A signed-in Codex desktop app/CLI and Python 3.10+. PDF compilation needs an existing TeX Live, MiKTeX or MacTeX installation providing `xelatex` or `pdflatex`, plus `bibtex` and `synctex`. Markdown HTML preview does not need TeX; Markdown PDF requires XeLaTeX. Supply missing tools/packages yourself; the plugin does not install TeX or change global settings.

Frontend assets are bundled: users do not need npm, pip or Poppler. macOS can use `/Library/TeX/texbin`. The Windows/Linux picker optionally uses tkinter; command-line file opening works without it.

## Install in Codex

1. Download/clone this repository and open its folder in Codex.
2. Ask: “Install latex-codex following AGENTS.md.” Alternatively, run from the repository root:

   ```sh
   codex plugin marketplace add .
   codex plugin add latex-codex@latex-codex-shared
   ```

   On Windows, when the CLI is absent from PATH, use the Codex-provided terminal:

   ```powershell
   & $env:CODEX_CLI_PATH plugin marketplace add .
   & $env:CODEX_CLI_PATH plugin add latex-codex@latex-codex-shared
   ```

3. Start a new chat: “Use latex-codex to open /path/to/main.tex.” `.md` and `.markdown` paths also work.

Keep the repository available as the local plugin source. To upgrade, update the source, reinstall the plugin and restart only after handling drafts, annotations and running jobs.

## Start without a chat

Run from the repository root and open the printed URL. macOS/Linux commonly use `python3`.

```sh
python plugins/latex-codex/scripts/editor.py /path/to/main.tex
```

The default listener is local-only with an available port. Markdown uses the same command.

## Collaboration and LAN detection

```sh
python plugins/latex-codex/scripts/editor.py /path/to/main.tex --collaborate --owner-name Owner --host auto --port auto
```

Log in with the printed private owner link. Create individual invitations in Collaboration and share each with its intended person. Do not share owner/administrator links. Grant Codex permission separately per member; editing, ordinary comments and editor compilation do not require it.

`--host auto` selects a private local IPv4 address; multiple adapters/VPNs may require an explicit IP. `--port auto` tries 8765, then binds an OS-selected free port. For stable access, provide a numeric port such as `--port 8765`; an occupied explicit port fails rather than silently changing.

## Multiple projects on one port

```sh
python plugins/latex-codex/scripts/gateway.py --project /path/to/paper/main.tex --project /path/to/notes/draft.md --host auto --port 8765 --owner-name Owner
```

Use the private local administrator link to select/register projects. Collaborator invitations include the project path and choose it automatically. Registration lives in the user's `.latex-codex/projects.json`, outside published source. Administrator sessions require login after restart; persistent collaborator invitations/permissions remain.

## Public tunnel

Append the real public origin to an existing collaborative/gateway command, for example:

```sh
--public-url https://editor.example.com
```

Map the tunnel to the actual listening port, preserve the browser Host and use valid HTTPS. HTTP and HTTPS are distinct origins and must be configured accurately. The plugin does not install/configure tunnels or firewalls, or infer public domains. Repeat `--public-url` for additional origins.

The project root defaults to the main file's folder. Use `--project-root /path/to/project` for a common root containing child folders. Use a dedicated document folder: ordinary project files/history are shared. Local TeX compilation by editors has no OS sandbox, so do not grant editor access to untrusted strangers.

## Storage, migration and source publication

History, discussions, permissions, trash and translation caches live in private project `.latex-codex/` storage; preferences live in the user directory. Back up private project data when migrating documents, but exclude it from GitHub. Preserve unsaved drafts and handle queued annotations/suggestions before switching/upgrading.

Create a source-only package using the release allowlist:

```sh
python plugins/latex-codex/scripts/package_source.py --output /path/to/latex-codex-source.zip
```

It excludes manuscripts, PDFs, databases, caches, credentials and demo media. See [AGENTS.md](../AGENTS.md) and [Features](FEATURES.md) for full options, maintenance and verification status.

## Origin and acknowledgments

This plugin is adapted from [Fr0zenWatter/codex-latex-editor](https://github.com/Fr0zenWatter/codex-latex-editor/tree/main). Thank you to **Fr0zenWatter** and the original contributors. This is a modified derivative, not an official release by the original author.
