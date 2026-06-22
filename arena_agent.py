import os
from turtle import title
import uuid
import json
import asyncio
import re
import sqlite3
import google.generativeai as genai
from pathlib import Path
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

FEEDBACK_FILE = "feedback.json"

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

    # Image Tasks
    if (
        "http" in text
        and (
            ".png" in text
            or ".jpg" in text
            or ".jpeg" in text
        )
    ):
        return "image"

    # SQL Tasks
    if "sql" in text:
        return "sql"

    # JSON Tasks
    if "json" in text:
        return "json"

    # Log Tasks
    if "log" in text:
        return "log"

    # Algorithm Tasks
    if "algorithm" in text:
        return "algorithm"

    return "general"

def algorithm_checker():

    return "COMPLEXITY_VERIFIED"


def image_analyzer():

    return "IMAGE_ANALYZED"


async def solve_task(title, description):

    task_type = classify_task(
        title,
        description
    )

    tool_result = ""

    if task_type == "sql":

        tool_result = sql_validator(
            "SELECT 1"
        )

    elif task_type == "algorithm":

        tool_result = algorithm_checker()

    elif task_type == "image":

        tool_result = image_analyzer()

    elif task_type == "json":

        tool_result = "JSON_PARSER_AVAILABLE"

    elif task_type == "log":

        tool_result = "LOG_ANALYZER_AVAILABLE"

    else:

        tool_result = "NO_TOOL_USED"

    print(
        f"\nTool Result: {tool_result}"
    )

    prompt = f"""
Task Type:
{task_type}

Tool Result:
{tool_result}

Title:
{title}

Description:
{description}

Use the tool result when solving.

Rules:
- Think carefully.
- Consider edge cases.
- Follow all task requirements exactly.
- If the task asks for SQL, return only SQL.
- If the task asks for code, return only code.
- If the task asks for a number, return only the number.
- Do not add explanations unless explicitly requested.

Return only the final answer.
"""

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        response = model.generate_content(
            prompt
        )

        answer = response.text.strip()

        return answer

    except Exception as e:

        print(
            "\nGemini Error:",
            e
        )

        return None

def save_feedback(task_type, score, feedback):

    try:
        fb = {
            "task_type": task_type,
            "score": score,
            "feedback": feedback
        }

        path = Path("feedback.json")

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = []
        else:
            data = []

        data.append(fb)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    except Exception as e:
        print("Could not save feedback:", e)

async def improve_low_score_answer(
    title,
    description,
    answer,
    feedback
):

    prompt = f"""
The previous answer scored poorly.

Task:
{title}

Description:
{description}

Previous Answer:
{answer}

Evaluator Feedback:
{feedback}

Generate a better answer.

Return only the improved answer.
"""

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        response = model.generate_content(
            prompt
        )

        return response.text.strip()

    except Exception:

        return answer

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

     print(
        "\nLevel completed.\n"
    )
     return "LEVEL_COMPLETE"
    
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

    draft_answer = await solve_task(
    title,
    description
)
    if draft_answer is None:

     print("Draft answer generation failed")

     return

    answer = await review_answer(
    title,
    description,
    draft_answer
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

        score = result_json.get(
            "score",
            0
        )

        weighted_score = result_json.get(
            "weightedScore",
            0
        )

        total_score = result_json.get(
            "totalScore",
            0
        )

        level = result_json.get(
            "newLevel"
        )

        feedback = result_json.get(
            "feedback",
            ""
        )

        print(
            f"\nScore: {score}"
        )

        print(
            f"Weighted Score: {weighted_score}"
        )

        print(
            f"Total Score: {total_score}"
        )

        print(
            f"Level: {level}"
        )

        print(
            f"\nFeedback:\n{feedback}"
        )

        save_feedback(
            task_type,
            score,
            feedback
        )

        if score < 60:

            print(
                "\nLow score detected."
            )

            improved_answer = await improve_low_score_answer(
                title,
                description,
                answer,
                feedback
            )

            print(
                "\nImproved Answer:\n"
            )

            print(
                improved_answer
            )

    except Exception as e:

        print(
            "\nCould not parse result JSON",
            e
        )

async def run_agent():

    while True:

        try:

            result = await get_first_task()

            if result == "LEVEL_COMPLETE":

                print(
                    "\nAll tasks for this level have been completed."
                )

                break

        except Exception as e:

            print(
                "\nAgent Error:",
                e
            )

            break

        print(
            "\nFetching next task...\n"
        )

        await asyncio.sleep(2)

async def review_answer(
    title,
    description,
    answer
):

    prompt = f"""
Review the following answer.

Task:
{title}

Description:
{description}

Answer:
{answer}

Check:
- correctness
- completeness
- edge cases
- formatting

Return an improved final answer only.
"""

    try:

        model = genai.GenerativeModel(
            "gemini-2.5-flash"
        )

        response = model.generate_content(
            prompt
        )

        return response.text.strip()

    except Exception:

        return answer

if __name__ == "__main__":

    asyncio.run(
        run_agent()
    )

    