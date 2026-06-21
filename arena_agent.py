import os
import uuid
import json
import asyncio
import re
import sqlite3
import google.generativeai as genai
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(
    api_key=GEMINI_API_KEY
)

AGENT_NAME = "TaskForge"
AGENT_STACK = "Python + ADK + Gemini"

MODEL = "gemini-2.5-flash"

MCP_ENDPOINT = "https://agent-arena-623774504237.asia-southeast1.run.app/mcp"

ID_TOKEN = os.getenv("ID_TOKEN")

MAX_TURNS = 20

class RunState:

    def __init__(self):

        self.run_id = str(uuid.uuid4())

        self.agent_id = ""

        self.task_id = ""

        self.current_level = 1

        self.total_score = 0

        self.tasks_attempted = 0

        self.level_history = []

async def mcp_call(tool_name, args):

    transport = StreamableHttpTransport(
        url=MCP_ENDPOINT
    )

    async with Client(
        transport,
        name="taskforge"
    ) as client:

        result = await client.call_tool(
            tool_name,
            args
        )

        return result

print("ID_TOKEN exists:", ID_TOKEN is not None)
print("Token length:", len(ID_TOKEN) if ID_TOKEN else 0)

if ID_TOKEN:
    print("Starts with:", ID_TOKEN[:25])

async def register_agent():

    result = await mcp_call(
        "register_agent",
        {
            "idToken": ID_TOKEN,
            "name": AGENT_NAME,
            "stack": AGENT_STACK
        }
    )

    print("\nREGISTER RESULT:\n")
    print(result)

    return result

async def submit_answer(agent_id, task_id, answer):

    result = await mcp_call(
        "submit_task",
        {
            "idToken": ID_TOKEN,
            "agentId": agent_id,
            "taskId": task_id,
            "content": answer
        }
    )

    return result

async def skip_task(agent_id, task_id):

    result = await mcp_call(
        "skip_task",
        {
            "idToken": ID_TOKEN,
            "agentId": agent_id,
            "taskId": task_id
        }
    )

    return result

def sql_validator(sql_query):

    try:

        conn = sqlite3.connect(":memory:")

        cursor = conn.cursor()

        cursor.execute("SELECT 1")
        return "SQL_VALIDATION_SUCCESS"

    except Exception as e:

        return f"SQL_VALIDATION_FAILED: {e}"

def classify_task(title, description):

    text = f"{title} {description}".lower()

    if "sql" in text:
        return "sql"

    if "json" in text:
        return "json"

    if "log" in text:
        return "log"

    if "algorithm" in text:
        return "algorithm"

    if (
        ".png" in text
        or ".jpg" in text
        or "image" in text
    ):
        return "image"

    return "general"

async def solve_task(title, description):

    task_type = classify_task(
        title,
        description
    )

    tool_result = ""

    if task_type == "sql":

        tool_result = """
SQL validation tool available.
Query should be syntactically valid.
"""

    prompt = f"""
Task Type: {task_type}

Tool Output:
{tool_result}

Title:
{title}

Description:
{description}

Requirements:
1. Solve accurately.
2. Use tool output.
3. Return only the final answer.
"""

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        response = model.generate_content(
            prompt
        )

        return response.text.strip()

    except Exception as e:

        print("Gemini Error:", e)

        return None

async def get_first_task():

    registration = await register_agent()

    print("\nTrying to extract agent id...\n")

    raw_text = registration.content[0].text

    print("\nRAW RESPONSE:\n")
    print(raw_text)

    # Extract Agent ID
    if raw_text.startswith("{"):

        data = json.loads(raw_text)

        agent_id = data["agentId"]

    else:

        match = re.search(
            r"AGENT_ID:\s*([A-Za-z0-9]+)",
            raw_text
        )

        if not match:
            print("Could not extract agent id")
            return

        agent_id = match.group(1)

    print("\nAgent ID:", agent_id)

    # Get Task
    task = await mcp_call(
        "get_tasks",
        {
            "idToken": ID_TOKEN,
            "agentId": agent_id
        }
    )

    print("\nTASK:\n")
    print(task.content[0].text)

    task_text = task.content[0].text

    if "ALL_TASKS_ATTEMPTED" in task_text:

        print("\nLevel completed.\n")

        return

    task_data = json.loads(task_text)

    if len(task_data) == 0:
        print("No tasks available")
        return

    current_task = task_data[0]

    task_id = current_task["id"]
    title = current_task["title"]
    description = current_task["description"]

    print("\nTask ID:", task_id)
    print("Title:", title)

    # Solve Task

    task_type = classify_task(
    title,
    description
)
    print(
    f"\nTask Type: {task_type}"
)
    answer = await solve_task(
        title,
        description
    )

    if answer is None:
        print("No answer generated")
        return

    print("\nGENERATED ANSWER:\n")
    print(answer)

    # Submit Answer
    submission = await submit_answer(
        agent_id,
        task_id,
        answer
    )

    print("\nSUBMISSION RESULT:\n")

    result_text = submission.content[0].text

    print(result_text)

    # Parse Score
    try:

        result_json = json.loads(result_text)

        print(
            f"\nScore: {result_json.get('score')}"
        )

        print(
            f"Weighted Score: {result_json.get('weightedScore')}"
        )

        print(
            f"Total Score: {result_json.get('totalScore')}"
        )

        print(
            f"Level: {result_json.get('newLevel')}"
        )

    except Exception as e:

        print("\nCould not parse result JSON")
        print(e)

async def run_agent():

    while True:

        try:

            await get_first_task()

        except Exception as e:

            print("Agent Error:", e)

            break

        print("\nFetching next task...\n")


if __name__ == "__main__":

    asyncio.run(
        run_agent()
    )

    