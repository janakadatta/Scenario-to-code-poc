"""
Full pipeline: Jira ticket + Confluence coding standards + an uploaded
design document (PDF/DOCX, possibly containing HLD/LLD/ER diagrams) + the
Java Spring Boot MongoDB skill file -> a generated multi-file Java project.

This supersedes jira_confluence_codegen.py's single-file Python output with
a full Spring Boot project structure, and adds:
  - document upload support (with diagram understanding)
  - an explicit business-requirements-extraction step
  - token optimization (summarization + caching) so large inputs don't
    silently balloon cost every run
"""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from document_ingestion import ingest_document
from token_optimizer import summarize_if_needed, cached, estimate_tokens

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

SKILL_FILE_PATH = Path(__file__).resolve().parent / "skills" / "java-spring-boot" / "SKILL.md"
CONFLUENCE_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h - standards docs rarely change hour to hour


# ---------------------------------------------------------------------------
# Model + MCP server configuration
# ---------------------------------------------------------------------------
model = ChatGoogleGenerativeAI(model="gemini-3.6-flash", api_key=os.environ["GOOGLE_API_KEY"])
# A cheaper/faster model for the summarization pass specifically. Using the
# same model for both "compress this text" and "write production code" is
# wasteful - summarization doesn't need the strongest reasoning available.
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
        "READ_ONLY_MODE": "true",
    },
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
BUSINESS_REQUIREMENTS_PROMPT = """\
You are a business analyst. From the following design document content,
extract a structured Business Requirements Summary:

1. Entities: name each entity/data object, its fields, and its type.
2. Relationships: how entities relate to each other (one-to-many, etc).
3. Endpoints / operations needed: what operations the backend must expose
   (create, read, update, delete, search, etc), phrased as business
   capabilities, not technical endpoints yet.
4. Business rules / constraints: any validation rules, required fields,
   uniqueness constraints, workflow rules, or non-functional requirements
   (auth, rate limits, etc) mentioned or implied.

Be exhaustive about rules and constraints specifically - these are the
easiest thing to lose and the most costly to miss in generated code.

Document content:
{document_content}
"""

CODEGEN_PROMPT = """\
You are a Principal Java Backend Architect. Generate a complete, multi-file
Java 25 Spring Boot backend project using MongoDB, strictly following the
rules in the skill file below. Also incorporate the Jira ticket's
acceptance criteria and the team's general coding standards.

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

=== Business requirements (extracted from the uploaded design document) ===
{business_requirements}

=== Jira acceptance criteria for ticket {issue_key} ===
(Fetch this using the Jira tool available to you.)

=== Team coding standards from Confluence page "{standards_page_title}" in space "{confluence_space}" ===
(Fetch this using the Confluence tool available to you.)

Return your ENTIRE response as a single JSON object and nothing else - no
prose, no markdown code fences around the JSON itself. The JSON shape must
be exactly:

{{
  "files": {{
    "pom.xml": "<file content>",
    "src/main/java/.../SomeController.java": "<file content>",
    "src/main/java/.../SomeService.java": "<file content>",
    "...": "..."
  }},
  "notes": "<any assumptions you made, in plain text>"
}}

Include, at minimum: pom.xml, an application.yml/properties file with a
placeholder Mongo connection string (never a hardcoded real one), one
@Document class per entity, one repository, one service, one controller,
one DTO + MapStruct mapper per entity, a global exception handler, and at
least one JUnit 5 test per service class.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_skill_rules() -> str:
    return SKILL_FILE_PATH.read_text()


def extract_business_requirements(document_content: str) -> tuple[str, dict]:
    """Token-optimization step 1: compress the raw document down before it
    ever reaches the main (more expensive) generation call."""
    optimized_text, stats = summarize_if_needed(document_content, summarizer_model)
    response = summarizer_model.invoke(
        BUSINESS_REQUIREMENTS_PROMPT.format(document_content=optimized_text)
    )
    return response.content, stats


def parse_generated_files(raw_response: str) -> dict:
    """The model is asked for pure JSON, but strip code fences defensively
    in case it wraps the response anyway."""
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    print("Java Spring Boot (MongoDB) Backend Generator")
    print("Reads: an uploaded design document + a Jira ticket + Confluence standards\n")

    doc_path = input("Path to design document (PDF or DOCX): ").strip()
    issue_key = input("Jira issue key: ").strip()
    standards_page_title = input(
        "Confluence coding standards page title [Backend Coding Standards]: "
    ).strip() or "Backend Coding Standards"
    confluence_space = input("Confluence space key: ").strip()

    print("\nReading document and describing any diagrams (this calls Gemini vision"
          " once per image found, so it can take a bit for image-heavy files)...")
    ingested = ingest_document(doc_path, model)
    doc_content = ingested.combined_context()
    print(f"Extracted {estimate_tokens(doc_content)} estimated tokens of content "
          f"({len(ingested.diagram_descriptions)} diagram(s) described).")

    print("\nExtracting business requirements (with token optimization)...")
    business_requirements, opt_stats = extract_business_requirements(doc_content)
    if opt_stats["summarized"]:
        print(f"  Document was summarized before extraction: "
              f"~{opt_stats['original_tokens_est']} -> ~{opt_stats['final_tokens_est']} tokens "
              f"({opt_stats['reduction_pct']}% reduction) across {opt_stats['chunks']} chunk(s).")
    else:
        print(f"  Document was small enough (~{opt_stats['original_tokens_est']} tokens) "
              f"to skip summarization.")

    # The skill file doesn't change between runs - cache it rather than
    # re-reading/re-hashing needlessly, and to make the "what changed"
    # story simple to explain: this cache exists for anything static.
    skill_rules, from_cache = cached(
        "skill_rules", str(SKILL_FILE_PATH), ttl_seconds=CONFLUENCE_CACHE_TTL_SECONDS,
        compute_fn=load_skill_rules,
    )
    print(f"  Skill file loaded ({'from cache' if from_cache else 'freshly read'}).")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            agent = create_agent(model, tools)

            prompt = CODEGEN_PROMPT.format(
                skill_rules=skill_rules,
                business_requirements=business_requirements,
                issue_key=issue_key,
                standards_page_title=standards_page_title,
                confluence_space=confluence_space,
            )

            print("\nGenerating Java Spring Boot project (this fetches the Jira ticket "
                  "and Confluence page, then writes the full project)...")
            response = await agent.ainvoke({"messages": prompt})
            raw_output = response["messages"][-1].content

            try:
                parsed = parse_generated_files(raw_output)
            except json.JSONDecodeError:
                # Save the raw output so nothing is lost even if parsing
                # failed - easier to debug a malformed-JSON response than
                # to have it silently vanish.
                fallback_path = OUTPUT_DIR / f"{issue_key}_raw_response.txt"
                fallback_path.write_text(raw_output)
                print(f"\nCould not parse the model's response as JSON. "
                      f"Raw response saved to: {fallback_path}")
                return

            project_dir = write_project_files(f"{issue_key}_java_project", parsed["files"])
            print(f"\nGenerated {len(parsed['files'])} files under: {project_dir}")
            if parsed.get("notes"):
                print(f"\nModel's notes/assumptions:\n{parsed['notes']}")


if __name__ == "__main__":
    asyncio.run(main())
