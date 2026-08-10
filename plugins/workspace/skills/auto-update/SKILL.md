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

Invoke `/loop 5m /workspace:update-project` via the Skill tool.
