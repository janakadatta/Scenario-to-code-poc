import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv(Path(__file__).resolve().parent / ".env")

model = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    api_key=os.environ["GOOGLE_API_KEY"],
)

print("Calling Gemini directly (no MCP, no agent)...")
try:
    response = model.invoke("Say hello in one sentence.")
    print("SUCCESS:")
    print(response.content)
except Exception as e:
    print("FAILED with this exact error:")
    print(repr(e))
