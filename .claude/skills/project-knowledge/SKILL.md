---
name: project-knowledge
description: |
  Use when you need information about Reels Studio — the internal web app that turns a topic into
  a 9:16 short video (Claude script, scene images, FFmpeg render) for Reels/TikTok/Shorts: its
  scope and MVP, architecture (Next.js + FastAPI + render worker + Postgres + Redis), data model,
  coding patterns, git workflow, testing, deployment, UI and video template, or the content domain
  (Vietnamese health/nutrition channel formula, script prompt contract, knowledge base, safety rules).
---

# Project Knowledge: Reels Studio

Reels Studio is an early-stage project. Only the render core and its CLI exist
([worker/](../../../worker/)); everything else in this documentation is agreed design not yet
built.

## References

- **[project.md](references/project.md)**: purpose, users, problem, MVP features, development
  phases, out of scope.
- **[architecture.md](references/architecture.md)**: stack and rationale, components, render
  pipeline, integrations, data flow, data model, sensitive data.
- **[patterns.md](references/patterns.md)**: code patterns, Git workflow, testing and
  verification, business rules.
- **[deployment.md](references/deployment.md)**: dev host, planned Docker Compose setup,
  environment variables, operations.
- **[ux-guidelines.md](references/ux-guidelines.md)**: UI language, screens, video visual
  template.
- **[content.md](references/content.md)**: channel audience, video formula, script generation
  contract, Knowledge Base, safety rules, monetization context.

## What to Read for a Task

- Starting any feature: project.md, architecture.md, patterns.md.
- Database or API changes: architecture.md (Data Model).
- Render pipeline or template work: architecture.md (Components), ux-guidelines.md (Video
  Template).
- Prompt, script generation, knowledge base, or safety checks: content.md.
- UI screens: ux-guidelines.md.
- Environment, Docker, or deployment: deployment.md.
- Branches, PRs, tests: patterns.md.
