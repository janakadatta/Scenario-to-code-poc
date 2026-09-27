import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from document_ingestion import ingest_document
from token_optimizer import summarize_if_needed

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)

if not os.environ.get("GOOGLE_API_KEY"):
    raise RuntimeError("Missing GOOGLE_API_KEY in .env")

SKILL_FILE_PATH = Path(__file__).resolve().parent / "skills" / "java-spring-boot" / "SKILL.md"
CODING_STANDARDS_PATH = Path(__file__).resolve().parent / "coding_standards.md"

DESIGN_DOCS_DIR = Path(__file__).resolve().parent / "generated_design_docs"
DESIGN_DOCS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = Path(__file__).resolve().parent / "generated_projects"
OUTPUT_DIR.mkdir(exist_ok=True)

model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    api_key=os.environ["GOOGLE_API_KEY"],
    max_output_tokens=8192,
)
summarizer_model = ChatGoogleGenerativeAI(model="gemini-3.6-flash-lite", api_key=os.environ["GOOGLE_API_KEY"])


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
DESIGN_DOCS_PROMPT = """\
You are a solution architect. Based on the business scenario below, produce
design documentation as Mermaid diagrams (text-based diagram syntax, NOT
images) plus supporting written docs.

Business scenario:
{scenario}

Return your response as PLAIN TEXT using EXACTLY these section markers,
each on its own line, with nothing else outside them (no JSON, no code
fences around the whole thing, no commentary before or after):

===ERD_MERMAID===
<a Mermaid 'erDiagram' block covering every entity, its fields, and relationships - just the diagram code itself, no markdown code fence>
===SEQUENCE_MERMAID===
<a Mermaid 'sequenceDiagram' block covering the main flow(s) described in the scenario - just the diagram code itself, no markdown code fence>
===HLD===
<a written High-Level Design: components/services involved, how they interact, in plain text with a short Mermaid 'flowchart' block for the architecture diagram>
===LLD===
<a written Low-Level Design: key classes/modules, their responsibilities, and the main API operations needed>
===END===
"""

CODEGEN_PROMPT = """\
You are a Principal Java Backend Architect. Generate a complete, multi-file
Java 25 Spring Boot backend project using MongoDB.

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
Every other rule in the skill file applies exactly as written, with
Testcontainers using the MongoDB module instead of a relational one.

=== Team coding standards ===
{coding_standards}

=== Business scenario ===
{scenario}

=== Design docs generated from the scenario above ===
{design_docs}

Return your response as PLAIN TEXT using EXACTLY this format, repeated once
per file, with nothing else outside these markers (no JSON, no extra
commentary mixed into the file blocks):

===FILE: <relative/path/to/File.java>===
<the complete file content, exactly as it should be saved - no markdown code fence around it>
===ENDFILE===

Repeat the ===FILE: ...=== / ===ENDFILE=== block for every file. Include,
at minimum: pom.xml, an application.yml with a placeholder Mongo connection
string, one @Document class per entity, one repository, one service, one
controller, one DTO + MapStruct mapper per entity, a global exception
handler, and at least one JUnit 5 test per service class.

After every file block, add:
===NOTES===
<any assumptions you made, in plain text>
===END===
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def extract_text(content) -> str:
    """The Gemini client sometimes returns response.content as a plain
    string, and sometimes as a list of content parts (depending on
    library version/response mode). Normalize either shape to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts)
    return str(content)


def get_finish_reason(response) -> str | None:
    if hasattr(response, "response_metadata"):
        return response.response_metadata.get("finish_reason")
    return None


def parse_delimited_sections(text: str) -> dict[str, str]:
    """Splits text on ===MARKER=== lines into {marker_lower: content}.
    Used for the design docs response - no JSON, so no escaping to get
    wrong on multi-line Mermaid content."""
    parts = re.split(r"===([A-Z_]+)===", text)
    sections = {}
    for i in range(1, len(parts), 2):
        name = parts[i].strip().lower()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[name] = content
    return sections


def parse_generated_files(text: str) -> dict:
    """Parses the ===FILE: path=== / ===ENDFILE=== blocks from the codegen
    response into {path: content}, plus any ===NOTES=== section."""
    files = {}
    file_pattern = re.compile(r"===FILE:\s*(.+?)\s*===\n(.*?)===ENDFILE===", re.DOTALL)
    for match in file_pattern.finditer(text):
        path = match.group(1).strip()
        content = match.group(2).strip("\n")
        files[path] = content

    notes = ""
    notes_match = re.search(r"===NOTES===\n(.*?)(?:===END===|\Z)", text, re.DOTALL)
    if notes_match:
        notes = notes_match.group(1).strip()

    return {"files": files, "notes": notes}


def design_docs_as_markdown(sections: dict[str, str]) -> str:
    return f"""# Design Documentation

## Entity-Relationship Diagram

```mermaid
{sections.get('erd_mermaid', '(not generated)')}
```

## Sequence Diagram

```mermaid
{sections.get('sequence_mermaid', '(not generated)')}
```

## High-Level Design

{sections.get('hld', '(not generated)')}

## Low-Level Design

{sections.get('lld', '(not generated)')}
"""


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
def main():
    print("Demo Pipeline: business scenario file -> design diagrams -> Java Spring Boot (MongoDB) code\n")

    scenario_doc_path = input("Path to business vision document (PDF, DOCX, TXT, or MD): ").strip()

    print(f"\n[1/3] Reading {scenario_doc_path}...")
    ingested = ingest_document(scenario_doc_path, model)
    scenario_text = ingested.combined_context()
    if ingested.diagram_descriptions:
        print(f"  Found and described {len(ingested.diagram_descriptions)} diagram(s) in the document.")

    scenario_text, opt_stats = summarize_if_needed(scenario_text, summarizer_model)
    if opt_stats["summarized"]:
        print(f"  Scenario summarized: ~{opt_stats['original_tokens_est']} -> "
              f"~{opt_stats['final_tokens_est']} tokens ({opt_stats['reduction_pct']}% reduction).")

    doc_stem = Path(scenario_doc_path).stem.replace(" ", "_")

    print("\n[2/3] Generating ERD, sequence diagram, HLD, LLD...")
    response = model.invoke(DESIGN_DOCS_PROMPT.format(scenario=scenario_text))
    raw_design_text = extract_text(response.content)
    sections = parse_delimited_sections(raw_design_text)

    if not sections.get("erd_mermaid") or not sections.get("sequence_mermaid"):
        fallback_path = DESIGN_DOCS_DIR / f"{doc_stem}_raw_response.txt"
        fallback_path.write_text(raw_design_text)
        print(f"  Response was missing expected sections. Finish reason: {get_finish_reason(response)}")
        print(f"  Raw response saved to: {fallback_path} - open it to see what the model actually returned.")
        return

    design_docs_md = design_docs_as_markdown(sections)
    design_doc_path = DESIGN_DOCS_DIR / f"{doc_stem}_design.md"
    design_doc_path.write_text(design_docs_md)
    print(f"  Saved to: {design_doc_path}")
    print("  Open this file in VS Code (or any Markdown previewer that supports Mermaid) to see the diagrams rendered.")

    print("\n[3/3] Generating Java Spring Boot (MongoDB) backend code...")
    skill_rules = SKILL_FILE_PATH.read_text()
    coding_standards = CODING_STANDARDS_PATH.read_text()
    response = model.invoke(CODEGEN_PROMPT.format(
        skill_rules=skill_rules,
        coding_standards=coding_standards,
        scenario=scenario_text,
        design_docs=design_docs_md,
    ))
    raw_code_text = extract_text(response.content)
    parsed = parse_generated_files(raw_code_text)

    if not parsed["files"]:
        fallback_path = OUTPUT_DIR / f"{doc_stem}_raw_response.txt"
        fallback_path.write_text(raw_code_text)
        finish_reason = get_finish_reason(response)
        print(f"  No files could be parsed from the response.")
        print(f"  Raw response length: {len(raw_code_text)} characters.")
        print(f"  Finish reason reported by the model: {finish_reason}")
        print(f"  Raw response saved to: {fallback_path}")
        if finish_reason == "MAX_TOKENS":
            print("  The response was cut off before finishing - the project is too large "
                  "for one response. Next step would be generating fewer files per call.")
        return

    project_dir = write_project_files(f"{doc_stem}_java_project", parsed["files"])
    print(f"\nDone. Generated {len(parsed['files'])} files under: {project_dir}")
    if parsed.get("notes"):
        print(f"\nModel's notes/assumptions:\n{parsed['notes']}")


if __name__ == "__main__":
    main()