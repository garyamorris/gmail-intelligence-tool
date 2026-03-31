# Product Spec: Content Studio for Audience-Aware Blogs + Code Repos

## Summary
Transform the current Gmail intelligence app into a **content studio** that can:

- generate one-off blog posts or multi-part series
- choose an audience and adapt tone, depth, and examples accordingly
- identify code-worthy sections and create companion code repositories/examples
- coordinate specialized agents for drafting, coding, review, and design feedback
- present the whole workflow as a polished, high-trust creator workspace

This is not just a writing tool. It is an orchestration system for producing publishable technical content bundles.

## Problem Statement
The current app is centered on inbox intelligence, but the desired workflow is broader:

1. start from an idea
2. choose an audience
3. generate a blog or series
4. create code examples that are referenced in the writing
5. review and refine with multiple specialized agents
6. package everything into a coherent content delivery workflow

The missing piece is orchestration across writing, code generation, review, and presentation.

## Goals
- Let a user move from topic idea to finished content bundle.
- Support both single posts and series.
- Make audience targeting a first-class input.
- Automatically generate or propose example repos when useful.
- Use specialized agents for drafting, coding, review, and editorial polish.
- Provide a premium UI that makes the system feel creative, structured, and reliable.

## Non-Goals
- Full CMS replacement
- Social network publishing automation in v1
- Autonomous publication without review
- Generic prompt playground

## Primary Users
- Technical founder / solo creator
- Developer advocating an idea with code examples
- Product marketer writing for different sophistication levels
- Technical editor managing a structured content pipeline

## Core User Journey
### 1) Start a content project
Inputs:
- topic / thesis
- format: blog post, series, guide, explainer, opinion piece, tutorial
- audience: beginner, practitioner, executive, technical lead, mixed audience
- goals: educate, persuade, compare, document, announce
- depth: shallow / medium / deep
- desired examples: none, pseudocode, runnable snippet, full repo

### 2) Plan the structure
System creates:
- title options
- angle options
- outline
- section-by-section intent
- proposed examples to build
- agent task plan

### 3) Generate drafts and code
Agents work in parallel where possible:
- Outline agent
- Drafting agent
- Research agent
- Code example agent
- Reviewer agent
- Designer / presentation agent

### 4) Review and refine
Specialized review passes:
- product/spec review
- editorial clarity review
- technical accuracy review
- code readability review
- UX/design review for how it will be presented in the app

### 5) Package output
Outputs can include:
- final article draft
- supporting repo(s)
- code snippets referenced in the text
- callouts for diagrams/screenshots
- launch checklist
- exportable content bundle

## Functional Requirements

### Content project creation
- User can create a content project from a topic.
- User can choose an audience before generation.
- User can select single post or multi-part series.
- User can specify whether code examples are required.

### Audience targeting
The system must adjust:
- tone
- terminology density
- assumed knowledge
- length of explanations
- code example complexity
- call-to-action style

Suggested audience presets:
- Beginner
- Builder / practitioner
- Technical lead
- Exec / decision maker
- Mixed audience

### Series support
- User can define a series with multiple posts.
- Each post in the series has its own angle and purpose.
- Posts can share a common research base and example repo set.

### Code example generation
- The system can generate one or more code repos.
- Code examples are linked to specific sections in the draft.
- The system should be able to create either:
  - minimal demo repos
  - runnable examples
  - architecture sketches
- Repo creation should be treated as a managed artifact, not an incidental side effect.

### Specialized agents
The system should support agent roles such as:
- strategist
- researcher
- drafter
- code builder
- reviewer
- editor
- designer
- publisher / packaging agent

### Review workflow
- Every generated draft should be reviewable before publishing.
- Review should surface both content and code issues.
- Reviewers can request changes, suggest rewrites, or approve.

### UI/UX
- The app should feel like a studio, not a dashboard.
- Must present:
  - project timeline/status
  - agent activity
  - draft revisions
  - linked repos/examples
  - audience settings
  - review status
- The interface should make complex workflows understandable at a glance.

## Proposed Information Architecture
Primary navigation:
- Projects
- Briefs / Ideas
- Drafts
- Repos / Examples
- Reviews
- Publish / Export
- Settings

Project detail view:
- Overview
- Outline
- Drafts
- Code examples
- Agents
- Reviews
- Assets

## Proposed System Architecture
### Existing system to reuse
The current app already has useful primitives:
- authenticated Google Cloud deployment patterns
- background intelligence / analysis patterns
- dashboard UI
- storage layer
- action and review-oriented endpoints

### New modules to add
- Content project model
- Audience model
- Series model
- Agent orchestration service
- Repo/example creation service
- Review pipeline service
- Content bundle export service
- Design system refresh for premium presentation

### Integration principle
Prefer adapting the current app rather than rewriting it.

## Data Model Sketch
### ContentProject
- id
- title
- topic
- format
- audience
- depth
- status
- created_at
- updated_at

### ContentArtifact
- id
- project_id
- kind: outline | draft | revision | repo | snippet | review | asset
- title
- body
- metadata
- status

### ExampleRepo
- id
- project_id
- repo_name
- purpose
- linked_sections
- status
- url

### AgentRun
- id
- project_id
- agent_role
- input
- output
- status
- created_at

## Success Metrics
- Time from idea to first draft reduced materially
- Users can reliably generate audience-appropriate drafts
- Code examples are coherent and match the text
- Review cycle catches obvious issues before publication
- The UI feels premium and easy to navigate

## MVP Scope
MVP should include:
1. content project creation
2. audience selection
3. outline generation
4. draft generation
5. code example tasking
6. basic agent review workflow
7. improved UI shell for project-centric workflow

## Risks
- Over-automating code generation without enough editorial control
- Generated examples drifting away from article intent
- UI becoming cluttered if too many agent states are surfaced at once
- Scope creep into full CMS/publishing platform

## Recommended Implementation Plan
### Phase 1
- Add content project model and new project-centric UI.
- Add audience presets and draft generation flow.
- Store outline, drafts, and linked example metadata.

### Phase 2
- Add agent orchestration and specialized review passes.
- Add repo/example creation support.
- Add revision tracking and artifact links.

### Phase 3
- Redesign interface into a studio-style experience.
- Add export/publish packaging.
- Add multi-post series support.

## Notes on Tone and Brand
The product should feel:
- sharp
- useful
- opinionated
- editorially aware
- visually premium

Not:
- generic
- overly technical
- cluttered
- gadget-like

## Open Questions
- Should repo creation happen in the same GitHub org as the app or in a user-selected org?
- Should content generation and code generation happen in one shared project or separate linked projects?
- Should the system support direct publishing to LinkedIn, blog CMS, or both?
- How much autonomy should agents have before requiring approval?
