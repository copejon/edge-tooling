---
name: auto-update
description: Start a 5-minute loop that keeps project docs updated during idle
---

# Auto-Update Project Docs

Schedule `/workspace:update-project` to run every 5 minutes while the
session is idle.

## Step 1: Check for Existing Loop

Run CronList. If any job's prompt contains `update-project`, tell the
user it's already running (show the job ID) and stop.

## Step 2: Schedule

Resolve the current project name (from conversation context or
`$ARGUMENTS`). Call CronCreate with cron `*/5 * * * *`, prompt
`/workspace:update-project <project-name>`, recurring `true`.

If CronCreate succeeds, confirm: scheduled every 5 minutes, auto-expires
after 7 days, cancel with CronDelete (show the job ID).

If CronCreate fails, report the error and stop — do not claim success.

Do NOT run `/workspace:update-project` immediately — the first fire
should happen after 5 minutes, when the user has had time to work.
