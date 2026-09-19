import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class AgentClient:
    """One (base_url, model) pair. Every LLM agent in the system is one of these."""

    model: str
    client: OpenAI

    def complete(self, messages: list[dict], **kwargs):
        return self.client.chat.completions.create(model=self.model, messages=messages, **kwargs)


def baseten_client(model: str) -> AgentClient:
    return AgentClient(
        model=model,
        client=OpenAI(base_url="https://inference.baseten.co/v1", api_key=os.environ["BASETEN_API_KEY"]),
    )


def gemini_client(model: str = "gemini-2.5-flash") -> AgentClient:
    return AgentClient(
        model=model,
        client=OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.environ["GEMINI_API_KEY"],
        ),
    )


# VERIFY: current routable Gemini vision-capable slug (BUILD_PLAN.md section 4).
SCENE_AGENT = lambda: gemini_client("gemini-2.5-flash")
