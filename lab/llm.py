"""Any OpenAI-compatible chat API (DeepSeek by default). Set LLM_* in .env."""
import json
import os
from functools import cache
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


@cache
def client():
    return OpenAI(base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
                  api_key=os.getenv("LLM_API_KEY") or os.environ["DEEPSEEK_API_KEY"],
                  timeout=60, max_retries=2)


def model():
    return os.getenv("LLM_MODEL", "deepseek-flash")


def complete(messages, **kw):
    """Full response object (tool calls, usage). Use chat() for plain text."""
    return client().chat.completions.create(model=model(), messages=messages, **kw)


def chat(messages, **kw):
    return complete(messages, **kw).choices[0].message.content


def chat_json(messages, **kw):
    """Ask for a JSON object (the prompt must mention JSON) and parse it."""
    return json.loads(chat(messages, response_format={"type": "json_object"},
                           temperature=0, **kw))
