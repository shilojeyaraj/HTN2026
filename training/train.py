"""Fine-tune Qwen3-1.7B with LoRA SFT on the command-to-verb dataset.

Baseten runs this via: baseten train push --config config.py
Saves to BT_CHECKPOINT_DIR, then deploy with:
    baseten train checkpoint deploy --job-id <job_id>
"""

import os

import datasets
import torch
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

MODEL_NAME = "Qwen/Qwen3-1.7B"
DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.jsonl")
OUTPUT_DIR = os.getenv("BT_CHECKPOINT_DIR", "./checkpoints")

dataset = datasets.load_dataset("json", data_files=DATASET_PATH, split="train")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.bfloat16,
    device_map="auto",
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
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=8,
    gradient_accumulation_steps=2,
    learning_rate=2e-4,
    logging_steps=10,
    save_strategy="epoch",
    gradient_checkpointing=True,
    warmup_steps=10,
    lr_scheduler_type="cosine",
    bf16=True,
)

trainer = SFTTrainer(
    model=model,
    args=sft_config,
    train_dataset=dataset,
    processing_class=tokenizer,
    peft_config=lora_config,
)

trainer.train()
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Training complete. Model saved to {OUTPUT_DIR}")
