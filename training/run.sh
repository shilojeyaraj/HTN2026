#!/bin/bash
set -e
pip install trl peft transformers datasets accelerate
python train.py
