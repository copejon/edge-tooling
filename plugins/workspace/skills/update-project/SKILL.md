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

## Step 0: Auto-Update Loop Handling

This step applies only when this invocation was triggered by a
ScheduleWakeup (the prompt is `/workspace:update-project` from a prior
wakeup). For manual invocations (user typed the command), skip to Step 1.

**Guard — skip if nothing changed:** Check whether the **immediately
preceding conversation turn** was also a `/workspace:update-project` run
(either manual or auto). If it was:

1. Call `ScheduleWakeup` with `delaySeconds: 270`,
   `prompt: "/workspace:update-project <name>"` (preserving the project token), and
   `reason: "no new activity since last auto-update — re-checking in 4.5m"`.
2. Return immediately — do not proceed to Step 1.

**Dispatch via background agent:** If there IS new activity since the
last update, do NOT run the update inline. Instead:

1. Resolve the project name from `$ARGUMENTS` (the wakeup prompt includes
   it). Fall back to conversation context if not present (the project
   loaded by `/workspace:resume-project` or referenced in earlier turns).
2. Review the conversation history since the last auto-update (or since
   resume-project if this is the first wakeup). Identify:
   - Checklist items completed
   - New checklist items discovered
   - Findings, test results, or analysis worth recording
   - New detail files created but not yet in the Reference Files table
3. If nothing substantive changed, treat this as "nothing changed" —
   re-schedule and return (same as the guard above).
4. Build a self-contained agent prompt:

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
   > Write tool for new files.

5. Dispatch using the Agent tool with `run_in_background: true` (the
   default). The agent runs without blocking the main session.
6. Call `ScheduleWakeup` with `delaySeconds: 270`,
   `prompt: "/workspace:update-project <name>"` (preserving the project token), and
   `reason: "auto-update dispatched to background agent — next check in 4.5m"`.
7. Return immediately.

**On agent completion notification:** When the background agent finishes
(you receive the completion notification), display this reminder to the
user:

> Project docs updated (prompt cache was about to expire). Consider
> running `/clear` and `/workspace:resume-project` to continue in a
> fresh session.

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

If nothing to update, say so. If a ScheduleWakeup loop is active,
proceed to Step 5. Otherwise stop.

## Step 4: Apply

Use the Edit tool for existing files. Use the Write tool for new detail
files. Edit each file individually — do not rewrite entire files.

Always set `last-active: <YYYY-MM-DD>` (today) in the frontmatter as
the first edit to CLAUDE.md, before applying checklist or progress
changes. This field drives the SessionStart ordering hook.

Summarize what was updated. If the session produced durable domain-level
knowledge (not just project status), suggest `/workspace:update-domain` —
this command never edits domain files itself.

## Step 5: Re-Schedule Auto-Update

If a ScheduleWakeup loop is active (the conversation includes a prior
ScheduleWakeup call for `/workspace:update-project`), re-schedule the
next wakeup after this manual update:

Call `ScheduleWakeup` with `delaySeconds: 270`,
`prompt: "/workspace:update-project <name>"` (preserving the project token), and
`reason: "project docs updated — next auto-check in 4.5m"`.

If this was a manual invocation and no prior ScheduleWakeup loop exists,
do NOT schedule one — the loop is only started by
`/workspace:resume-project`.
