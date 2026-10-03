"""A small LLM gateway: one interface over several providers.

- fallback chain: try providers in order; move on when one fails
- retries with backoff + jitter, only for errors worth a retry
- circuit breaker: after N failures in a row, skip that provider for a while
- structured output: validate against a pydantic model, send errors back to repair
- streaming: yield text as it arrives; failover only before the first token
- one option name for all providers: think=False maps to each provider's own switch
- chaos knobs (fail, hang) to simulate an outage - these are fake, the rest is real
"""
import os
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
import openai
from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

# Worth a retry or a fallback. A 400 or 401 is our bug: fail at once.
RETRYABLE = (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError,
             openai.InternalServerError, TimeoutError, ConnectionError)


class AllProvidersFailed(Exception):
    pass


@dataclass
class Provider:
    name: str
    base_url: str
    key_env: str
    model: str
    no_think: dict  # this provider's request field that turns thinking off
    fail: float = 0.0  # chaos: share of calls that fail fast (like a 503)
    hang: float = 0.0  # chaos: seconds a call hangs, then times out
    fails: int = field(default=0, repr=False)  # breaker: failures in a row
    open_until: float = field(default=0.0, repr=False)  # breaker: skip until this time

    @cached_property
    def client(self):
        return openai.OpenAI(base_url=self.base_url, api_key=os.environ[self.key_env],
                             timeout=60, max_retries=0)  # the gateway owns retries

    def call(self, messages, think=True, **kw):
        if not think:
            kw["extra_body"] = self.no_think
        if self.hang:
            time.sleep(self.hang)
            raise TimeoutError(f"{self.name}: timed out after {self.hang}s")
        if random.random() < self.fail:
            raise ConnectionError(f"{self.name}: 503")
        return self.client.chat.completions.create(model=self.model, messages=messages, **kw)


def provider(name, **chaos):
    base = {"deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY",
                         {"thinking": {"type": "disabled"}}),
            "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
                           {"reasoning": {"enabled": False}})}
    models = {"flash": ("deepseek", "deepseek-flash"), "pro": ("deepseek", "deepseek-v4-pro"),
              "flash-backup": ("openrouter", "deepseek/deepseek-v4-flash")}
    host, model = models[name]
    url, key, no_think = base[host]
    return Provider(name, url, key, model, no_think, **chaos)


class Gateway:
    def __init__(self, chain, retries=0, breaker=None, cooldown=30, backoff=0.2):
        self.chain, self.retries, self.backoff = chain, retries, backoff
        self.breaker, self.cooldown = breaker, cooldown  # breaker = failures before opening
        self.used, self.errors, self.wasted = Counter(), Counter(), 0.0  # wasted = s in failed calls

    def complete(self, messages, **kw):
        for p in self.chain:
            if time.time() < p.open_until:
                self.errors[f"{p.name} skipped (breaker open)"] += 1
                continue
            for attempt in range(1 + self.retries):
                t = time.time()
                try:
                    r = p.call(messages, **kw)
                    p.fails = 0
                    self.used[p.name] += 1
                    return r
                except RETRYABLE as e:
                    self.errors[f"{p.name} {type(e).__name__}"] += 1
                    self.wasted += time.time() - t
                    p.fails += 1
                    if self.breaker and p.fails >= self.breaker:
                        p.open_until = time.time() + self.cooldown
                        break
                    if attempt < self.retries:  # jitter: clients must not retry in step
                        time.sleep(self.backoff * 2 ** attempt * random.uniform(0.5, 1.5))
        raise AllProvidersFailed(dict(self.errors))

    def chat(self, messages, **kw):
        return self.complete(messages, **kw).choices[0].message.content

    def structured(self, messages, schema, repairs=2, **kw):
        """Returns (object, repairs used). Invalid output goes back with the error."""
        msgs = list(messages)
        for i in range(repairs + 1):
            text = self.chat(msgs, **kw)
            try:
                return schema.model_validate_json(re.sub(r"^```\w*\n|\n```$", "", text.strip())), i
            except ValidationError as e:
                msgs += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"Invalid: {e}\nReturn only the fixed JSON."}]
        raise ValueError(f"no valid output after {repairs} repairs")

    def stream(self, messages, **kw):
        """Yield text pieces. After the first piece the user has seen output,
        so we cannot switch provider without them noticing."""
        for chunk in self.complete(messages, stream=True, **kw):
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
