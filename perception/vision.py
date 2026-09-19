import base64

from brain.llm_client import SCENE_AGENT
from brain.state import Detection

SYSTEM_PROMPT = """You are the vision system of a small rover. Given a downscaled camera \
frame and a list of on-camera object detections, describe the scene in 2-3 sentences: \
notable objects, free space, and any hazards. Be concrete about direction and distance."""


def describe_scene(jpeg_bytes: bytes, detections: list[Detection]) -> str:
    agent = SCENE_AGENT()
    b64 = base64.b64encode(jpeg_bytes).decode()
    response = agent.complete(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Detections: {detections}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ],
    )
    return response.choices[0].message.content
