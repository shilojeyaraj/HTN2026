"""Fine-tune the rescue decision model locally on CPU (Baseten-ready).

This runs the same training code that would run on Baseten's H100, but
locally on CPU for demo purposes. The training pipeline is identical —
same model (Qwen3-1.7B), same LoRA config, same SFT trainer. When Baseten
access is available, the same code runs on H100 via:
    baseten train push --config training/config.py

Usage:
    python training/train_local.py --input training/training_traces.jsonl
    python training/train_local.py --input traces.jsonl --epochs 1 --batch-size 2
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def traces_to_dataset(input_path: str, output_path: str = "training/rescue_dataset.jsonl"):
    """Convert collected traces into SFT training dataset format."""
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
            if not trace.get("good", False):
                continue

            user_msg = trace.get("input", "")
            assistant_msg = json.dumps([{"tool": tc["tool"], "args": tc["args"]} for tc in trace.get("tool_calls", [])])

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
    return output_path, count


def train_local(dataset_path: str, epochs: int = 1, batch_size: int = 2, output_dir: str = "./checkpoints/rescue"):
    """Run LoRA SFT training locally on CPU.

    Uses the same model (Qwen3-1.7B) and LoRA config as the Baseten training.
    On CPU this is slow (~30 min for 50 examples, 1 epoch) but demonstrates
    the full training pipeline. On Baseten H100, the same code runs in ~3 min.
    """
    import torch
    import datasets
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    MODEL_NAME = "Qwen/Qwen3-1.7B"

    print(f"Loading model: {MODEL_NAME}")
    print(f"Device: CPU (Baseten H100 ready — same code, faster)")
    print(f"Dataset: {dataset_path}")
    print(f"Epochs: {epochs}, Batch size: {batch_size}")
    print()

    dataset = datasets.load_dataset("json", data_files=dataset_path, split="train")
    print(f"Training examples: {len(dataset)}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load in float32 for CPU (bf16 not supported on CPU)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float32,
        device_map="cpu",
        use_cache=False,
    )

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        task_type="CAUSAL_LM",
    )

    sft_config = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=5,
        save_strategy="epoch",
        gradient_checkpointing=True,
        warmup_steps=5,
        lr_scheduler_type="cosine",
        bf16=False,  # CPU doesn't support bf16
        fp16=False,  # CPU doesn't support fp16
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=lora_config,
    )

    print("Starting training...")
    print("(On Baseten H100: same code, ~10x faster)")
    print()

    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    print(f"\nTraining complete. Model saved to {output_dir}")
    print(f"\nTo deploy on Baseten (when access is available):")
    print(f"  baseten train push --config training/config.py")
    print(f"  baseten train checkpoint deploy --job-id <id>")
    print(f"  # Update .env: BASETEN_PARSER_MODEL_ID=<new-id>")


def main():
    ap = argparse.ArgumentParser(description="Train rescue model locally (Baseten-ready)")
    ap.add_argument("--input", default="training/training_traces.jsonl", help="input traces JSONL")
    ap.add_argument("--output", default="training/rescue_dataset.jsonl", help="output dataset JSONL")
    ap.add_argument("--epochs", type=int, default=1, help="training epochs (keep low for CPU)")
    ap.add_argument("--batch-size", type=int, default=2, help="batch size (low for CPU)")
    ap.add_argument("--checkpoint-dir", default="./checkpoints/rescue", help="output checkpoint dir")
    args = ap.parse_args()

    # Step 1: Convert traces to dataset
    dataset_path, count = traces_to_dataset(args.input, args.output)

    if count == 0:
        print("No good traces found. Run collect_traces.py first:")
        print("  python training/collect_traces.py --count 50 --output training/training_traces.jsonl")
        return

    # Step 2: Train locally
    train_local(dataset_path, args.epochs, args.batch_size, args.checkpoint_dir)


if __name__ == "__main__":
    main()
