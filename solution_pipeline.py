"""
Full solution pipeline:

1. Read a business vision document that you provide manually (a local
   PDF/DOCX/TXT/MD file - for this POC stage, no automatic pull from
   Confluence; you supply the file yourself).
2. Generate design docs from it: ERD, sequence diagram, HLD, LLD - all as
   Mermaid text diagrams (diagram-as-code, not images - so this stays
   pure text in/out for the LLM, same constraint as before).
3. Publish those design docs to a new Confluence page, so solution
   architects can actually see/use them.
4. Draft a Jira issue (summary, description, acceptance criteria) from the
   scenario + design docs, and actually CREATE it in Jira.
5. Generate the Java 25 / Spring Boot / MongoDB backend code from that
   newly created ticket's acceptance criteria, the team's coding standards,
   and the Java skill file - same final stage as full_pipeline_codegen.py.

IMPORTANT: unlike jira_confluence_codegen.py and full_pipeline_codegen.py,
this script runs with WRITE access to Jira and Confluence - READ_ONLY_MODE is intentionally not set here.
"""

import asyncio
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from document_ingestion import ingest_document
from token_optimizer import summarize_if_needed, cached

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)
print("Environment variables loaded from .env file")

REQUIRED_VARS = [
    "GOOGLE_API_KEY",
    "JIRA_URL",
    "JIRA_USERNAME",
    "JIRA_API_TOKEN",
    "CONFLUENCE_URL",
    "CONFLUENCE_USERNAME",
    "CONFLUENCE_API_TOKEN",
]
missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing:
    raise RuntimeError(f"Missing required environment variables in .env: {', '.join(missing)}")

OUTPUT_DIR = Path(__file__).resolve().parent / "generated_projects"
OUTPUT_DIR.mkdir(exist_ok=True)
DESIGN_DOCS_DIR = Path(__file__).resolve().parent / "generated_design_docs"
DESIGN_DOCS_DIR.mkdir(exist_ok=True)

SKILL_FILE_PATH = Path(__file__).resolve().parent / "skills" / "java-spring-boot" / "SKILL.md"
CACHE_TTL_SECONDS = 60 * 60 * 24


# ---------------------------------------------------------------------------
# Model + MCP server configuration (WRITE ACCESS - see module docstring)
# ---------------------------------------------------------------------------
model = ChatGoogleGenerativeAI(model="gemini-3.6-flash", api_key=os.environ["GOOGLE_API_KEY"])
summarizer_model = ChatGoogleGenerativeAI(model="gemini-3.6-flash-lite", api_key=os.environ["GOOGLE_API_KEY"])

server_params = StdioServerParameters(
    command="uvx",
    args=["mcp-atlassian"],
    env={
        "JIRA_URL": os.environ["JIRA_URL"],
        "JIRA_USERNAME": os.environ["JIRA_USERNAME"],
        "JIRA_API_TOKEN": os.environ["JIRA_API_TOKEN"],
        "CONFLUENCE_URL": os.environ["CONFLUENCE_URL"],
        "CONFLUENCE_USERNAME": os.environ["CONFLUENCE_USERNAME"],
        "CONFLUENCE_API_TOKEN": os.environ["CONFLUENCE_API_TOKEN"],
        # No READ_ONLY_MODE here on purpose - this pipeline must be able to
    },
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
DESIGN_DOCS_PROMPT = """\
You are a solution architect. Based on the business scenario below, produce
design documentation as Mermaid diagrams (text-based diagram syntax, NOT
images) plus supporting written docs.

Business scenario:
{scenario}

Return your ENTIRE response as a single JSON object, nothing else:
{{
  "erd_mermaid": "<a Mermaid 'erDiagram' block covering every entity, its\
 fields, and relationships>",
  "sequence_mermaid": "<a Mermaid 'sequenceDiagram' block covering the main\
 flow(s) described in the scenario>",
  "hld": "<a written High-Level Design: components/services involved, how\
 they interact, in plain text with a short Mermaid 'flowchart' block for\
 the architecture diagram>",
  "lld": "<a written Low-Level Design: key classes/modules, their\
 responsibilities, and the main API operations needed>"
}}
"""

TICKET_DRAFT_PROMPT = """\
You are a business analyst turning design documentation into a Jira ticket.

Business scenario:
{scenario}

Design docs (ERD, sequence diagram, HLD, LLD):
{design_docs}

Return your ENTIRE response as a single JSON object, nothing else:
{{
  "summary": "<short Jira issue title>",
  "description": "<full description: context, what needs to be built,\
 referencing the entities/flows from the design docs>",
  "acceptance_criteria": ["<Given/When/Then style criterion>", "..."]
}}
"""

CREATE_ISSUE_INSTRUCTION = """\
Using your Jira issue-creation tool, create a new issue in project
"{project_key}" of type "{issue_type}" with:

Summary: {summary}

Description (include this exactly, with an "Acceptance Criteria" section
listing each item below as a bullet):
{description}

Acceptance Criteria:
{acceptance_criteria}

After creating it, reply with ONLY the created issue's key in the exact
format ISSUEKEY, e.g. KAN-5 - nothing else.
"""

PUBLISH_DESIGN_DOCS_INSTRUCTION = """\
Using your Confluence page-creation tool, create a new page in space
"{space_key}" titled "{page_title}" with the following content (preserve
the Mermaid code fences as-is; Confluence will render them if a Mermaid
macro/app is installed, otherwise they'll show as code blocks - either way
the content is preserved):

{content}

Confirm once created.
"""

CODEGEN_PROMPT = """\
You are a Principal Java Backend Architect. Generate a complete, multi-file
Java 25 Spring Boot backend project using MongoDB, strictly following the
rules in the skill file below.

=== Skill file (follow exactly, with ONE explicit override below) ===
{skill_rules}

=== Database override (this is NOT part of the skill file above - it is a
project-specific instruction layered on top of it) ===
The skill file above specifies Spring Data JPA. This project's required
database is MongoDB, not a relational database. Apply every rule in the
skill file that references JPA/entities as its Spring Data MongoDB
equivalent instead - for example:
- "@Entity" -> "@Document"
- "JpaRepository" -> "MongoRepository"
- "Never expose JPA entities directly" -> "Never expose @Document classes directly"
- No relational joins/foreign keys - model relationships as embedded
  sub-documents or referenced IDs, whichever fits the data
Every other rule in the skill file (DTO pattern, MapStruct, validation,
security, testing, logging, SOLID, etc.) applies exactly as written, with
Testcontainers using the MongoDB module instead of a relational one.

=== Design docs (for context on the intended data model and flows) ===
{design_docs}

=== Jira acceptance criteria for ticket {issue_key} ===
(Fetch this using the Jira tool available to you.)

=== Team coding standards from Confluence page "{standards_page_title}" in space "{standards_space_key}" ===
(Fetch this using the Confluence tool available to you.)

Return your ENTIRE response as a single JSON object and nothing else:
{{
  "files": {{
    "pom.xml": "<file content>",
    "src/main/java/.../SomeController.java": "<file content>",
    "...": "..."
  }},
  "notes": "<any assumptions you made, in plain text>"
}}

Include, at minimum: pom.xml, an application.yml with a placeholder Mongo
connection string, one @Document class per entity, one repository, one
service, one controller, one DTO + MapStruct mapper per entity, a global
exception handler, and at least one JUnit 5 test per service class.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_skill_rules() -> str:
    return SKILL_FILE_PATH.read_text()


def parse_json_response(raw_response: str) -> dict:
    text = raw_response.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[len("json"):]
    return json.loads(text.strip())


def write_project_files(project_name: str, files: dict[str, str]) -> Path:
    project_dir = OUTPUT_DIR / project_name
    for relative_path, content in files.items():
        file_path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
    return project_dir


def design_docs_as_markdown(design_docs: dict) -> str:
    return f"""# Design Documentation

## Entity-Relationship Diagram

```mermaid
{design_docs['erd_mermaid']}
```

## Sequence Diagram

```mermaid
{design_docs['sequence_mermaid']}
```

## High-Level Design

{design_docs['hld']}

## Low-Level Design

{design_docs['lld']}
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("Solution Pipeline: business scenario -> design docs -> Jira ticket -> Java code\n")

    scenario_doc_path = input(
        "Path to business vision document (PDF, DOCX, TXT, or MD): "
    ).strip()
    standards_page_title = input(
        "Confluence coding standards page title [Backend Coding Standards]: "
    ).strip() or "Backend Coding Standards"
    standards_space_key = input("Confluence space key for the standards page: ").strip()
    jira_project_key = input("Jira project key to create the ticket in (e.g. KAN): ").strip()
    issue_type = input("Jira issue type [Task]: ").strip() or "Task"

    # --- Stage 1: read the business vision document you provided ---
    # No Jira/Confluence connection needed for this step, so it happens
    # before the MCP session even starts.
    print(f"\n[1/5] Reading {scenario_doc_path}...")
    ingested = ingest_document(scenario_doc_path, model)
    scenario_text = ingested.combined_context()
    if ingested.diagram_descriptions:
        print(f"  Found and described {len(ingested.diagram_descriptions)} diagram(s) in the document.")

    # Token optimization: compress before it's reused across the next three
    # LLM calls, instead of paying for the full text three times over.
    scenario_text, opt_stats = summarize_if_needed(scenario_text, summarizer_model)
    if opt_stats["summarized"]:
        print(f"  Scenario summarized: ~{opt_stats['original_tokens_est']} -> "
              f"~{opt_stats['final_tokens_est']} tokens "
              f"({opt_stats['reduction_pct']}% reduction).")

    # --- Stage 2: generate design docs ---
    # Also no Jira/Confluence needed - this is a direct model call.
    print("\n[2/5] Generating ERD, sequence diagram, HLD, LLD...")
    response = model.invoke(DESIGN_DOCS_PROMPT.format(scenario=scenario_text))
    design_docs = parse_json_response(response.content)
    design_docs_md = design_docs_as_markdown(design_docs)

    doc_stem = Path(scenario_doc_path).stem.replace(" ", "_")
    design_doc_path = DESIGN_DOCS_DIR / f"{doc_stem}_design.md"
    design_doc_path.write_text(design_docs_md)
    print(f"  Saved locally to: {design_doc_path}")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            agent = create_agent(model, tools)

            # --- Stage 3: publish design docs to Confluence ---
            print("\n[3/5] Publishing design docs to Confluence...")
            publish_title = f"{doc_stem} - Design Docs"
            response = await agent.ainvoke({
                "messages": PUBLISH_DESIGN_DOCS_INSTRUCTION.format(
                    space_key=standards_space_key,
                    page_title=publish_title,
                    content=design_docs_md,
                )
            })
            print(f"  {response['messages'][-1].content}")

            # --- Stage 4: draft and create the Jira ticket ---
            print("\n[4/5] Drafting and creating the Jira ticket...")
            response = model.invoke(
                TICKET_DRAFT_PROMPT.format(scenario=scenario_text, design_docs=design_docs_md)
            )
            ticket_draft = parse_json_response(response.content)

            ac_formatted = "\n".join(f"- {c}" for c in ticket_draft["acceptance_criteria"])
            response = await agent.ainvoke({
                "messages": CREATE_ISSUE_INSTRUCTION.format(
                    project_key=jira_project_key,
                    issue_type=issue_type,
                    summary=ticket_draft["summary"],
                    description=ticket_draft["description"],
                    acceptance_criteria=ac_formatted,
                )
            })
            agent_reply = response["messages"][-1].content.strip()
            match = re.search(r"[A-Z][A-Z0-9]+-\d+", agent_reply)
            if not match:
                print(f"  Could not confirm the created issue key from the agent's reply: {agent_reply}")
                print("  Check Jira directly to find the new ticket, then note its key for the next step.")
                issue_key = input("  Enter the issue key to continue with code generation: ").strip()
            else:
                issue_key = match.group(0)
                print(f"  Created Jira issue: {issue_key}")

            # --- Stage 5: generate the backend code from the new ticket ---
            print(f"\n[5/5] Generating Java Spring Boot (MongoDB) code from {issue_key}...")
            skill_rules, from_cache = cached(
                "skill_rules", str(SKILL_FILE_PATH), ttl_seconds=CACHE_TTL_SECONDS,
                compute_fn=load_skill_rules,
            )
            response = await agent.ainvoke({
                "messages": CODEGEN_PROMPT.format(
                    skill_rules=skill_rules,
                    design_docs=design_docs_md,
                    issue_key=issue_key,
                    standards_page_title=standards_page_title,
                    standards_space_key=standards_space_key,
                )
            })
            raw_output = response["messages"][-1].content

            try:
                parsed = parse_json_response(raw_output)
            except json.JSONDecodeError:
                fallback_path = OUTPUT_DIR / f"{issue_key}_raw_response.txt"
                fallback_path.write_text(raw_output)
                print(f"  Could not parse the model's response as JSON. "
                      f"Raw response saved to: {fallback_path}")
                return

            project_dir = write_project_files(f"{issue_key}_java_project", parsed["files"])
            print(f"\nDone. Generated {len(parsed['files'])} files under: {project_dir}")
            if parsed.get("notes"):
                print(f"\nModel's notes/assumptions:\n{parsed['notes']}")


if __name__ == "__main__":
    asyncio.run(main())
