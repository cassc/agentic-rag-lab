"""LLM-as-judge for answer correctness, plus a refusal check."""
from concurrent.futures import ThreadPoolExecutor
from lab.llm import chat_json

JUDGE = """You grade a candidate answer against a reference answer.
Correct = it states the key facts of the reference and nothing that contradicts it.
Extra correct detail is fine. Missing a key fact is wrong.
Return JSON: {"correct": true or false, "why": "one short sentence"}"""


def refused(answer):
    return "not in the sources" in answer.lower()


RUBRIC = """You grade a candidate answer against a reference answer.
Correct = it correctly answers what the QUESTION asks. Reference details the
question did not ask for are optional. If the question asks for two things,
both are needed. Any contradiction of the reference = wrong. Ignore style,
length, and units (5 s = 5000 ms).
Return JSON: {"correct": true or false, "why": "one short sentence"}"""


def judge(row, answer, prompt=JUDGE):
    if row.get("unanswerable"):
        return refused(answer)
    r = chat_json([{"role": "system", "content": prompt},
                   {"role": "user", "content":
                    f"Question: {row['q']}\nReference: {row['answer']}\nCandidate: {answer}"}])
    return bool(r["correct"])


def pmap(fn, items, workers=6):
    """Run fn over items in parallel threads (LLM calls are I/O bound)."""
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))
