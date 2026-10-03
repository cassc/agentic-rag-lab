"""OpenTelemetry tracing for the agent loop: one trace per run, one span per
LLM call and per tool call. Attribute names follow the OpenTelemetry GenAI
semantic conventions (gen_ai.*), so any OTel backend understands them.

Spans go to memory here. For a real backend (Jaeger, Langfuse, Arize, Tempo),
add an OTLP exporter - see lessons/14_observability/README.md.
"""
from functools import wraps
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from lab import loop
from lab.llm import complete, model

exporter = InMemorySpanExporter()
provider = TracerProvider(resource=Resource({"service.name": "agent-runtime"}))
provider.add_span_processor(SimpleSpanProcessor(exporter))
tracer = provider.get_tracer("lab")


def llm(messages, **kw):
    """Drop-in for lab.llm.complete."""
    with tracer.start_as_current_span("chat") as s:
        s.set_attribute("gen_ai.request.model", model())
        r = complete(messages, **kw)
        s.set_attribute("gen_ai.usage.input_tokens", r.usage.prompt_tokens)
        s.set_attribute("gen_ai.usage.output_tokens", r.usage.completion_tokens)
        s.set_attribute("gen_ai.usage.cached_tokens",
                        getattr(r.usage, "prompt_cache_hit_tokens", 0) or 0)
        return r


def tool(name, fn):
    @wraps(fn)
    def wrapped(**args):
        with tracer.start_as_current_span(f"execute_tool {name}") as s:
            s.set_attribute("gen_ai.tool.name", name)
            return fn(**args)  # an exception marks the span as an error, then goes on up
    return wrapped


def run(system, question, tools, **attrs):
    """loop.run inside a root span. attrs: tenant, session id, ... for filtering later."""
    with tracer.start_as_current_span("invoke_agent", attributes=attrs) as s:
        r = loop.run(system, question, {n: (tool(n, fn), spec) for n, (fn, spec) in tools.items()},
                     llm=llm)
        if r["answer"].startswith("Stopped"):
            s.set_status(StatusCode.ERROR, "step limit")
        return r


def ms(span):
    return (span.end_time - span.start_time) / 1e6
