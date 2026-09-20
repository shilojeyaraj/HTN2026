"""Fine-tune a rescue decision model on collected traces using Baseten.

Takes the good decision traces from collect_traces.py and fine-tunes
a Qwen3 model to improve rescue decision-making. Uses the same training
infrastructure as the command parser (training/train.py) but with rescue
scenario data.

Usage:
    python training/train_rescue.py --input training/training_traces.jsonl
    python training/train_rescue.py --input traces.jsonl --epochs 3 --lr 2e-4
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def traces_to_dataset(input_path: str, output_path: str = "training/rescue_dataset.jsonl"):
    """Convert collected traces into a SFT training dataset.

    Format: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
    """
    system_prompt = (
        "You are a rescue rover making decisions in a disaster scenario. "
        "Given the scene description and sensor readings, decide which tools to call. "
        "Call tools that follow rescue protocols: search knowledge for guidance, "
        "speak to victims, check sensors for hazards, and move to explore."
    )

    count = 0
    with open(input_path) as infile, open(output_path, "w") as outfile:
        for line in infile:
            trace = json.loads(line)
            if not trace["good"]:
                continue

            user_msg = trace["input"]
            assistant_msg = json.dumps([{"tool": tc["tool"], "args": tc["args"]} for tc in trace["tool_calls"]])

            example = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": assistant_msg},
                ]
            }
            outfile.write(json.dumps(example) + "\n")
            count += 1

    print(f"Created {count} training examples from {input_path} → {output_path}")
    return output_path


def main():
    ap = argparse.ArgumentParser(description="Fine-tune rescue decision model on Baseten")
    ap.add_argument("--input", default="training/training_traces.jsonl", help="input traces JSONL")
    ap.add_argument("--output", default="training/rescue_dataset.jsonl", help="output dataset JSONL")
    ap.add_argument("--epochs", type=int, default=3, help="training epochs")
    ap.add_argument("--lr", type=float, default=2e-4, help="learning rate")
    ap.add_argument("--batch-size", type=int, default=4, help="batch size")
    args = ap.parse_args()

    # Step 1: Convert traces to training dataset
    dataset_path = traces_to_dataset(args.input, args.output)

    # Step 2: Print Baseten training instructions
    print(f"\n{'=' * 60}")
    print("BASETEN TRAINING INSTRUCTIONS")
    print(f"{'=' * 60}")
    print(f"""
1. Upload the dataset to Baseten:
   baseten train push --dataset {dataset_path}

2. Start training (uses training/train.py config):
   baseten train push --config training/config.py

   Or modify training/config.py to point to rescue_dataset.jsonl
   and adjust:
   - epochs: {args.epochs}
   - learning_rate: {args.lr}
   - batch_size: {args.batch_size}

3. Watch training logs:
   baseten train job logs --job-id <id> --tail

4. Deploy the improved checkpoint:
   baseten train checkpoint deploy --job-id <id>

5. Update the model ID in .env:
   BASETEN_PARSER_MODEL_ID=<new-model-id>

6. Re-run collect_traces.py to measure improvement:
   python training/collect_traces.py --count 50 --output run2.jsonl

7. Compare scores:
   Run 1 avg score vs Run 2 avg score → improvement metric
""")


if __name__ == "__main__":
    main()
