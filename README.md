# mcp-jira-langchain

POC for automating part of the software delivery workflow using MCP,
LangChain, and Gemini. It's grown through a few iterations - all three
scripts still work, each is a stage in how this evolved.

## The three scripts, in the order they were built

### 1. `jira_confluence_codegen.py` - the original
Pulls a Jira ticket's acceptance criteria + our Confluence coding standards,
generates a single Python file that satisfies both. Read-only against
Jira/Confluence.

### 2. `full_pipeline_codegen.py` - adds document upload
Same idea, but you can also upload a PDF/DOCX design doc (including one
with an ER/HLD/LLD diagram as an image inside it - Gemini's vision
describes the diagram in text first). Generates a full multi-file Java 25 /
Spring Boot / MongoDB project instead of one Python file, following the
Java skill file in `skills/java_spring_boot_mongo/SKILL.md`. Still
read-only against Jira/Confluence.

### 3. `solution_pipeline.py` - the current direction
This is the one that matches where the project actually needs to go, per
direction from the lead. The flow reverses: instead of starting from an
existing Jira ticket, it starts from a **business scenario stored in
Confluence** and works forward:

1. Reads the business scenario from Confluence.
2. Generates design docs from it - ERD, sequence diagram, HLD, LLD - as
   Mermaid diagrams (text-based diagram syntax, not images).
3. Publishes those design docs back to a new Confluence page.
4. Drafts a Jira ticket (summary, description, acceptance criteria) from
   the scenario + design docs, and **actually creates it in Jira**.
5. Generates the Java Spring Boot MongoDB code from that new ticket, same
   as script #2's final stage.

**This one needs write access to Jira and Confluence** (it has to create
things, not just read them) - `READ_ONLY_MODE` is intentionally left off
for this script only. The other two scripts are untouched and still
read-only.

## Why Mermaid instead of draw.io

Draw.io diagrams are stored as precise XML (exact shape positions, IDs,
connectors) - an LLM generating that reliably from scratch isn't practical.
Mermaid is plain text that describes a diagram's structure (entities,
relationships, flow) without needing exact coordinates, which is what an
LLM is actually good at generating. If draw.io specifically is a hard
requirement (rather than "some diagram format"), that's a follow-up
conversation - possibly a conversion step from Mermaid, or accepting that
these are a first draft an architect redraws in draw.io by hand.

## What you need before running any of them

- Python 3.11+ and `uv` (https://docs.astral.sh/uv/)
- A Gemini API key
- A Jira/Confluence Cloud API token
- For `solution_pipeline.py` specifically: a token with **write** scopes
  (or a classic/unscoped token), since it creates a Jira issue and a
  Confluence page for real

## Setting it up

```bash
uv sync
```

Fill in `.env`:

```
GOOGLE_API_KEY=...
JIRA_URL=https://your-site.atlassian.net
JIRA_USERNAME=your.email@example.com
JIRA_API_TOKEN=...
CONFLUENCE_URL=https://your-site.atlassian.net/wiki
CONFLUENCE_USERNAME=your.email@example.com
CONFLUENCE_API_TOKEN=...
```

## Running the current pipeline

```bash
uv run solution_pipeline.py
```

It'll ask for: the Confluence page with the business scenario, the
Confluence page with coding standards, the Jira project key to create the
ticket in, and the issue type. It handles the rest end to end.

## Still open / not built yet

- **No automatic trigger** - this is a manually-run script. The lead
  confirmed manual trigger is fine for the POC stage; an actual "runs on
  its own" version would need a webhook or polling, which is a real step
  up in infrastructure (a script that runs continuously somewhere, not
  just on my laptop when I run it).
- **Token optimization is basic** - summarizes long text before reuse and
  caches static content (the skill file). Room to do more here as real
  usage patterns emerge.
- **Personal Atlassian account, free-tier Gemini key** - fine for a POC,
  not for anything touching real project data. Free-tier Gemini also has a
  very low daily request cap, worth a paid tier before this goes further.
