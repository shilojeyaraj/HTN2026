"""Run the brain through rescue scenarios, collect decision traces,
and evaluate performance.

Usage:
    python training/collect_traces.py --count 50 --output training_traces.jsonl
    python training/collect_traces.py --count 100 --complexity 3 --output traces.jsonl
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from brain.backboard_client import brain
from brain.tools import SYSTEM_PROMPT, VERBS
from training.scenario_generator import (
    generate_scenario,
    scenario_to_brain_input,
    evaluate_decision,
    to_training_jsonl,
)


async def run_scenario(scenario: dict) -> tuple[list, dict]:
    """Run the brain through a single scenario and return tool calls + evaluation."""
    rover_pose = (0.0, 0.0, 0.0)
    user_content = scenario_to_brain_input(scenario, rover_pose)

    def execute_tool(name: str, args: dict) -> dict:
        # Simulated tool execution — return realistic results
        s = scenario["sensor_readings"]

        if name == "forward":
            dets = s["detections"]
            ahead = [d for d in dets if abs(d["bearing_deg"]) < 30 and d["distance_m"] < 0.3]
            if ahead:
                return {"status": "stopped_by_obstacle", "distance_m": ahead[0]["distance_m"]}
            return {"status": "completed", "distance_m": args.get("distance_m", 0.5)}

        if name == "backward":
            return {"status": "completed", "distance_m": args.get("distance_m", 0.5)}

        if name == "turn":
            return {"status": "completed", "degrees": args.get("degrees", 0)}

        if name == "stop":
            return {"status": "completed"}

        if name == "speak":
            return {"status": "completed"}

        if name == "look_around":
            return {"scene": scenario["scene_description"]}

        if name == "check_map":
            return {"obstacles_nearby": s["detections"][:3], "sounds_nearby": [], "heat_nearby": []}

        if name == "check_safety":
            dets = s["detections"]
            ahead = [d for d in dets if abs(d["bearing_deg"]) < 30 and d["distance_m"] < 0.4]
            if ahead and args.get("action") == "forward":
                return {"status": "VETO", "action": args["action"]}
            return {"status": "OK", "action": args.get("action", "")}

        if name == "search_knowledge":
            return {"results": "rescue protocol retrieved"}

        if name == "log_finding":
            return {"status": "logged"}

        if name == "analyze_patterns":
            return {"insights": "pattern analysis complete"}

        if name == "get_obstacles":
            return {"detections": s["detections"]}

        if name == "get_state":
            return {"pose": rover_pose, "velocity": (0, 0), "goal": None}

        if name == "get_temperature":
            return s["temperature"]

        if name == "get_audio":
            return s["audio"]

        if name == "get_gyro":
            return s["gyro"]

        return {"status": "error", "detail": f"unknown verb {name}"}

    try:
        results = await brain._run_tools(
            content=user_content,
            system_prompt=SYSTEM_PROMPT,
            tools=VERBS,
            execute_tool=execute_tool,
            memory="Auto",
        )
        tool_calls = [{"tool": r["name"], "args": r["arguments"], "result": r["result"]} for r in results]
        evaluation = evaluate_decision(scenario, tool_calls, rover_pose)
        return tool_calls, evaluation
    except Exception as e:
        print(f"  [ERROR] {e}")
        return [], {"score": 0.0, "criteria": {}, "error": str(e)}


async def collect_traces(count: int, complexity: int, output_path: str, seed_base: int = 0):
    """Run the brain through multiple scenarios and collect traces."""
    print(f"Collecting {count} traces (complexity {complexity})...")
    print(f"Output: {output_path}")
    print()

    traces = []
    scores = []

    with open(output_path, "w") as f:
        for i in range(count):
            scenario = generate_scenario(complexity=complexity, seed=seed_base + i)
            print(f"  [{i+1}/{count}] {scenario['id']} — {scenario['environment_type']}", end="")

            tool_calls, evaluation = await run_scenario(scenario)
            score = evaluation.get("score", 0.0)
            scores.append(score)

            trace = to_training_jsonl(scenario, tool_calls, evaluation)
            traces.append(trace)
            f.write(json.dumps(trace) + "\n")
            f.flush()

            good = "GOOD" if trace["good"] else "SKIP"
            print(f" → score={score} ({good}) [{evaluation.get('num_tool_calls', 0)} calls]")

    avg_score = sum(scores) / len(scores) if scores else 0
    good_count = sum(1 for t in traces if t["good"])

    print(f"\n{'=' * 60}")
    print(f"COLLECTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Total scenarios: {count}")
    print(f"  Average score: {avg_score:.3f}")
    print(f"  Good traces (score >= 0.6): {good_count}/{count} ({good_count/count*100:.0f}%)")
    print(f"  Output: {output_path}")

    return traces


def main():
    ap = argparse.ArgumentParser(description="Collect brain decision traces for training")
    ap.add_argument("--count", type=int, default=50, help="number of scenarios to run")
    ap.add_argument("--complexity", type=int, default=2, help="scenario complexity 1-5")
    ap.add_argument("--output", default="training/training_traces.jsonl", help="output JSONL file")
    ap.add_argument("--seed", type=int, default=0, help="random seed base")
    args = ap.parse_args()

    asyncio.run(collect_traces(args.count, args.complexity, args.output, args.seed))


if __name__ == "__main__":
    main()
