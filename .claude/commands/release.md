---
description: Cut a release with the release-manager subagent.
argument-hint: "[version, e.g. 1.0.0]"
---

Use the release-manager subagent to release version $ARGUMENTS.
Before it tags, have the legal-rules-reviewer look at every calculation change since the
last tag, and the privacy-auditor at every change under planwerk/assistant.py,
planwerk/mcp_server.py, planwerk/api.py and planwerk/audit.py. Any finding stops the release.
