---
name: update-project
description: Update project documentation from what was accomplished in this session
argument-hint: [name-or-number]
---

# Update Project Documentation

Update a project's documentation based on what was accomplished in the
current conversation. Apply edits directly.

## Scope Rules

**Update:** files under `projects/<name>/` in the workspace — CLAUDE.md
(index, checklists, progress) and detail files (investigation notes, test
results, plans, etc.).

**NEVER touch during this command:**
- The `status:` frontmatter field — use `/workspace:close-project` to change it
- Memory files (`memory/MEMORY.md`, `memory/project_*.md`)
- Internal session tasks (TaskCreate / TaskUpdate)
- Repo source files under `repos/`

## Step 1: Resolve Project

Use the project already loaded in this conversation (from
`/workspace:resume-project` or any earlier project interaction). If `$ARGUMENTS`
has a token, use that as the project name instead.

If no project is in context and no argument was given, ask which project.

## Step 2: Read Current State

Read `projects/<name>/CLAUDE.md` in full.

## Step 3: Identify Updates

Review the conversation history and identify:

1. **Checklist items completed** — `- [ ]` items now done.
2. **New checklist items** — work discovered or queued.
3. **Detail file updates** — new findings, test results, or analysis to
   add to existing detail files, or new detail files to create.
4. **New detail files in Reference Files table** — files created in
   `projects/<name>/` not yet registered in CLAUDE.md's table.
5. **Progress entries** — milestones or outcomes to append.
6. **`last-active` timestamp** — always update `last-active: <YYYY-MM-DD>`
   in the frontmatter to today's date when any other update is applied.
   If the field does not exist yet, add it after the `status:` line.

If nothing to update, say so and stop.

## Step 4: Dispatch to Background Agent

Build a self-contained agent prompt from the updates identified in
Step 3:

> Update project documentation for project `<name>`.
>
> **Project directory:** `<absolute path to projects/<name>/>`
>
> Read `CLAUDE.md` in the project directory, then apply these updates:
> - [specific checklist items to check off]
> - [specific new items to add]
> - [specific detail files to update, with the content to add]
> - [new Reference Files table rows if any]
>
> Also update the `last-active` frontmatter field to today's date
> (YYYY-MM-DD).
>
> Rules: only edit files under the project directory. Never change the
> `status:` frontmatter field. Use the Edit tool for existing files,
> Write tool for new files. Edit each file individually — do not rewrite
> entire files.

Dispatch using the Agent tool with `run_in_background: true`. Say
"Updating project docs in the background." and return immediately.

**On agent completion notification:** Briefly confirm what was updated
(one line). If the session produced durable domain-level knowledge (not
just project status), suggest `/workspace:update-domain`.

