# Features (0.6.5)

[简体中文](FEATURES.zh-CN.md) · [Home](../README.md) · [Installation and launch](INSTALL.md)

## Documents and source editing

- Open local UTF-8 `.tex`, `.md` and `.markdown` files; edit and autosave the original file. File switching saves first and protects drafts, conflicts and pending suggestions.
- Standard, Vim and Emacs modes; syntax highlighting, undo/redo, line numbers and line/selection comment toggling.
- LaTeX command/environment completion, including names found in the current document; selecting a beginning environment inserts its matching end.
- Local KaTeX preview at the formula under the caret, including supported directly declared macros; this is not a complete TeX macro interpreter.
- Search and replacement with case sensitivity, regular expressions, whole words and selection-only scope; previous/next matches and undoable Replace All.
- Source font size of 10–32 px, Ctrl + wheel adjustment, and draggable source/preview proportions.

## Local PDF compilation and reading

- Existing XeLaTeX/pdfLaTeX engines, document engine directives and BibTeX. Biber is not supported.
- Save-and-compile, optional automatic compilation, status/logs, error-line diagnostics and regular PDF download. Collaboration defaults to manual compilation.
- Windows TeX, BibTeX, engine/package probes and SyncTeX run without creating console windows.
- Bundled PDF.js renders visible pages on demand; chapter navigation, page counts, scrolling, zoom and panning retain reading position across preview updates.
- Source-to-PDF and PDF-to-source navigation across project child files; stale mappings are disabled after changes invalidate compilation.
- Native PDF text selection and rectangular selection from blank page space. Hold Space to pan or Space + Alt and drag to zoom continuously from 30% to 500%.
- Add AI annotations to selected text/formulas, retaining complete supported formula boundaries. Ambiguous, cross-file or unreliable selections require a more precise selection.

## Markdown and Obsidian

- Local HTML live preview for headings, lists, code blocks, tables, KaTeX formulas and Obsidian image references.
- Optional XeLaTeX PDF preview supports callouts, displayed wiki-link text and TikZ fences, using packages already installed locally.
- Conversion skips YAML frontmatter and creates temporary TeX/assets in the build directory, preserving the original note's bytes.
- HTML images: PNG/JPG/GIF/WebP/AVIF. PDF images: PNG/JPG/PDF; unsupported formats show a notice.
- Select live-preview prose and right-click to add an AI annotation or ordinary discussion comment. Image/table discussion comments anchor to the corresponding source block.
- Live HTML uses browser text selection rather than PDF box selection; ambiguous ranges require narrowing or source selection.
- Collaboration image lookup stays within the project. Single-user mode can find attachments in the note's Obsidian vault.

## AI annotations and per-change proofreading

- An always-visible **AI annotations · count** button opens the list. View, edit, delete, collect several annotations, then Send a batch.
- Use the signed-in local Codex CLI, choose available models/reasoning levels and stop requests. Later batches send only annotations without generated suggestions.
- Red original text and green suggestions appear in source with independent Keep/Undo. Preview does not write source; Keep saves that change and Undo preserves the original.
- LaTeX suggestions can produce a temporary red/green PDF with shared Keep/Undo controls. Ordinary PDF download continues to export the regular document.
- Editor and PDF proofreading switches are independent; switching never accepts or discards pending suggestions. Markdown uses editor proofreading.
- Style offers None, Chinese/English Tao Compact and Shelah Compact presets, and UTF-8 prompt import. The default persists across documents; each annotation retains its own snapshot.
- Optional LaTeX replacement-color markup; Markdown replacements do not insert TeX color commands.
- When the Codex browser supports its annotation interface, selected source can be added to native main-chat annotations. Native annotations and the plugin's AI list are separate.

## Project chat and external-change review

- Ask about a selection in persistent project chat; files in the project share memory. Start a new conversation, stop generation or apply an answer to the tracked unchanged range.
- Single-user launches can link context to the initiating Codex thread ID. Collaborative AI requests exclude the main chat that launched the service.
- Optional project change review tracks external/main-chat edits already written to `.tex` files and provides per-change Keep/Undo in source and temporary PDF.
- Review baselines and pending edits survive refresh/restart. This defaults off and cannot intercept an external tool before it writes to disk.

## Collaboration and permissions

- Owners create individual named/color-coded editor or viewer invitations and can revoke them. Revoked members are omitted from the active invitation list.
- Online presence and roughly one-second synchronization. Non-overlapping edits merge automatically; overlapping edits preserve the local draft for explicit resolution, without last-write-wins overwrites.
- Source overlays display author colors/names and history records authorship. Regular PDFs do not receive collaboration author colors.
- Owners and editors can compile the fixed main file without Codex authorization. Viewers can only read/download an existing PDF.
- Owners grant Codex permission per member. New members default to unauthorized; viewers cannot receive it. The backend checks chat, AI annotations, model discovery, summaries and new translation requests.
- Revoking an invitation or Codex permission stops that member's running AI requests. Authorized members manage their own jobs; owners manage all jobs.
- Authorization uses the owner's Codex allowance. There are no per-member usage caps; consumed allowance is not refunded.

## Ordinary discussion comments

- These comments do not invoke AI. Add them from source, PDF text or Markdown live preview.
- The Comments panel shows current-file threads, quotes, authors, colors and replies, with locate, resolve, reopen and show-resolved actions.
- Editors can comment/reply without Codex permission; viewers read only. Authors or owners can resolve threads.
- Threads live in the collaboration database, not manuscript source. Polling preserves unpublished comment/reply drafts.
- Changed or repeated quotes are not guessed. For PDF images, comment on the associated source instead.

## Project files

- Browse a project tree and switch existing files. Editors can modify UTF-8 `.tex/.md/.markdown/.bib/.sty/.cls/.txt/.csv/.json` files.
- Owners can create files/folders, upload multiple files, replace, rename and delete. All collaborators can download individual files or a project ZIP.
- Limits: 16 MiB per uploaded file; 128 MiB for project uploads/ZIP. ZIP excludes hidden history and trash.
- Deleted files move into private project trash for manual disk recovery; only empty folders can be removed.
- Reject traversal, hidden paths, symlinks/junctions and Windows special paths. Main files and files being edited by online pages cannot be renamed/deleted.
- Replacement, renaming and deletion validate versions. Renaming does not rewrite LaTeX references or migrate old-path history/comments.

## Multiple projects and networking

- One gateway port serves projects under `/p/<project-id>/`. The private local administrator entry selects projects or registers local documents.
- Projects isolate invitations, sessions, file boundaries, history and Codex permissions. Invitations automatically choose their project without exposing the project list to collaborators.
- Administrator login is restricted to the local listening entry; public Hosts cannot use management APIs. Restart requires a new administrator login.
- Default loopback binding; an explicit LAN address or `--host auto` enables LAN access. `--port auto` tries 8765, then binds an OS-selected available port.
- Explicit numeric ports remain fixed. Tunnels must map the actual port, preserve Host and configure the exact public URL. Host/Origin checks remain enforced; firewall/tunnel configuration is manual.

## Chinese reading translation

- Optional per-project toggle, off by default; a separate Chinese pane beside PDF/Markdown, optional synchronized scrolling and a downloadable reading copy.
- Initial English paragraphs are translated once. Saved/compiled changes are coalesced and only changed/missing paragraphs are processed; content caching survives reordering, restoration and restart.
- Copies/cache live in private project storage, never replace source and are not the official PDF. Failure retains completed work; disabling stops work without deleting the cache.
- New translation requires Codex authorization; unauthorized members read cached translations and cannot trigger work via saves or direct API requests.
- Markdown aligns by source paragraphs; PDF aligns by page text and falls back to reading progress. Sentence-perfect alignment is not guaranteed.
- TeX follows static project-local inputs/includes, without dynamic macro expansion or external/`.bib` reads. Markdown skips frontmatter, code and references.
- Maximum 12 paragraphs/12000 characters per batch, one million characters/2000 paragraphs per document. Initial full-document translation still consumes allowance.

## History and personalization

- Project-wide source history for main/child files with filename, chapter, time, author and AI requirements; source diffs, restoration and PDF-change comparison.
- PDF differences mark complete changed sentences, including across pages. Comparison images are generated/cached on demand; ordinary compilation does not archive complete historical PDFs.
- Optional Codex summaries are cached by revision/baseline/interface language. Local chapter information remains on failure. Collaborative history operations belong to the owner.
- Eight interface languages, three editing modes, 14 light/dark palettes, custom themes, revision colors, font size, outline styles and pane proportions.
- Uploaded/pasted screenshots can generate palettes locally without AI or uploading the screenshot. Major preferences persist across documents and ports.

## Boundaries and current verification status

Collaboration is intended for trusted coauthors. Web path restrictions are not an OS sandbox: an editor compiling malicious TeX may still read other local files. Ordinary files/history inside the project are shared, so use a dedicated project folder. Login credentials are not sent to the browser; invitations/sessions use hashes and HttpOnly cookies, with Secure for HTTPS. Public access requires collaboration authentication and valid HTTPS.

Windows has been exercised locally; macOS path/picker behavior has simulated checks and still needs device testing. Users supply TeX and required packages. Complex macros, repeated text and unusual layouts can affect navigation, translation and PDF differences. In 0.6.5 maintenance checks, Markdown PDF range navigation and the comprehensive editor asset-loading assertion have unresolved failures. The independent real compilation check for hidden Windows TeX/BibTeX/package/SyncTeX processes passes; this documentation does not claim the entire suite passes.

## Origin and acknowledgments

This plugin is a modified derivative of [Fr0zenWatter/codex-latex-editor](https://github.com/Fr0zenWatter/codex-latex-editor/tree/main). It retains the original local editing, compilation, PDF reading, annotation and history foundation, and adds collaboration, permissions, multi-project access, file management and Chinese reading translation. Thank you to **Fr0zenWatter**, the original contributors and the authors of bundled third-party libraries. Their existing resource licenses remain in `plugins/latex-codex/scripts/vendor/`. This derivative is not an official release or endorsement by the original author.
