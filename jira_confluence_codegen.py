import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI


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
    raise RuntimeError(
        f"Missing required environment variables in .env: {', '.join(missing)}"
    )

OUTPUT_DIR = Path(__file__).resolve().parent / "generated_code"
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Model + MCP server configuration
# ---------------------------------------------------------------------------
model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    api_key=os.environ["GOOGLE_API_KEY"],
)

# mcp-atlassian is a pre-built, open-source MCP server (same idea as the
# pre-built sqlite MCP server used in the sqlite-langchain project). It
# exposes Jira AND Confluence tools from a single process, so we only need
# one stdio connection - not two.
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
        # Keep the agent read-only against your real Jira/Confluence data
        # while this is still a POC. Remove this line once you deliberately
        # want the agent to be able to create/edit issues or pages.
        "READ_ONLY_MODE": "true",
    },
)


# ---------------------------------------------------------------------------
# Prompt template for backend code generation
# ---------------------------------------------------------------------------
CODEGEN_PROMPT = """\
You are a backend engineer generating code that follows a company's coding
standards exactly.

Step 1: Fetch the Jira issue "{issue_key}" and extract its acceptance
criteria (look in the description and in any "Acceptance Criteria" custom
field or comments).

Step 2: Fetch the Confluence page titled "{standards_page_title}" in space
"{confluence_space}" and extract the backend coding standards described
there (naming conventions, project structure, error handling, logging,
testing expectations, etc.).

Step 3: Using the acceptance criteria from Step 1 and strictly following the
standards from Step 2, generate the backend code that implements the ticket.

Return ONLY the final code, in a single fenced code block, with a one-line
comment at the top naming the target file path. Do not include any
explanation outside the code block.
"""


async def process_query(agent, query: str) -> str:
    response = await agent.ainvoke({"messages": query})
    return response["messages"][-1].content


def extract_code_block(text: str) -> str:
    """Pull the contents out of the first fenced code block, if present."""
    if "```" not in text:
        return text
    parts = text.split("```")
    # parts[1] looks like "python\n<code>" - drop the language tag line
    body = parts[1]
    lines = body.splitlines()
    if lines and lines[0].strip().isalpha():
        lines = lines[1:]
    return "\n".join(lines).strip()


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            agent = create_agent(model, tools)

            print("Jira/Confluence Backend Code Generator (type 'exit' to quit)")
            print("Enter a Jira issue key (e.g. PROJ-123) to generate code for it.\n")

            while True:
                issue_key = input("Jira issue key: ").strip()
                if issue_key.lower() == "exit":
                    break
                if not issue_key:
                    continue

                standards_page_title = input(
                    "Confluence coding standards page title "
                    "[Backend Coding Standards]: "
                ).strip() or "Backend Coding Standards"
                confluence_space = input(
                    "Confluence space key [ENG]: "
                ).strip() or "ENG"

                query = CODEGEN_PROMPT.format(
                    issue_key=issue_key,
                    standards_page_title=standards_page_title,
                    confluence_space=confluence_space,
                )

                print("\nFetching acceptance criteria + coding standards, generating code...\n")
                response = await process_query(agent, query)

                code = extract_code_block(response)
                out_file = OUTPUT_DIR / f"{issue_key}_generated.py"
                out_file.write_text(code)

                print(f"Generated code saved to: {out_file}")
                print("\n--- Preview ---\n")
                print(code[:1000])
                print("\n---------------\n")


if __name__ == "__main__":
    asyncio.run(main())
