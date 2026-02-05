# Conversation Flashpoint Detection

Scripts for training and optimizing the conversation flashpoint detection model using DSPy.

## Overview

This module uses the [Conversations Gone Awry (CGA)](https://convokit.cornell.edu/documentation/awry_cmv.html) corpus from ConvoKit to train a DSPy-optimized prompt for detecting early warning signs that conversations may derail into conflict.

The CGA-CMV corpus contains ~19,500 conversations and ~116,000 utterances from ChangeMyView discussions, annotated for whether they eventually derailed into personal attacks or rule violations.

### Why GEPA over MIPRO?

We use DSPy's [GEPA optimizer](https://dspy.ai/deep-dive/optimizers/gepa/) instead of MIPRO for several reasons:

- **Sample-efficient**: Works well with smaller training sets (we use 200 train, 50 dev examples)
- **Structured outputs**: Better at handling bool + reasoning output schemas
- **Multi-step reasoning**: Excels at ChainOfThought tasks like flashpoint detection
- **Reflective optimization**: Uses feedback from errors to improve prompts iteratively

## Prerequisites

Ensure dependencies are installed:

```bash
cd opennotes-server
uv sync --extra flashpoints-dataset
```

Required packages (in `pyproject.toml`):
- `convokit>=3.5.0` - Cornell Conversational Analysis Toolkit (optional extra: `flashpoints-dataset`)
- `dspy>=2.6.0` - Stanford NLP's DSPy framework

## Usage

### 1. Extract Dataset

Download and process the CGA-CMV corpus into DSPy-compatible training examples:

```bash
cd opennotes-server
uv run python scripts/flashpoints/extract_cga_dataset.py
```

This creates train/dev/test splits in `data/flashpoints/`:
- `flashpoints_train.jsonl` (20% of data)
- `flashpoints_dev.jsonl` (30% of data)
- `flashpoints_test.jsonl` (50% of data)

The reversed allocation (smaller train, larger test) follows DSPy best practices to avoid overfitting during prompt optimization.

### 2. Optimize Prompt

Run GEPA optimization to find the best prompt instructions:

```bash
# Default settings (gpt-5-mini, medium optimization)
uv run python scripts/flashpoints/optimize_prompt.py

# With custom model
uv run python scripts/flashpoints/optimize_prompt.py --model openai/gpt-5.1

# Heavy optimization for better results (takes longer)
uv run python scripts/flashpoints/optimize_prompt.py --auto heavy

# Use a different reflection model for GEPA
uv run python scripts/flashpoints/optimize_prompt.py --reflection-model openai/gpt-5.1
```

**Options:**
| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `openai/gpt-5-mini` | LLM for the detector |
| `--reflection-model` | `openai/gpt-5.1` | LLM for GEPA reflection |
| `--auto` | `medium` | Optimization level: light, medium, heavy |
| `--output` | `data/flashpoints/optimized_detector.json` | Where to save the optimized model |

The optimized detector is saved to `data/flashpoints/optimized_detector.json` and should be committed to git.

### 3. Evaluate

Evaluate an existing optimized model without re-running optimization:

```bash
uv run python scripts/flashpoints/optimize_prompt.py \
    --eval-only data/flashpoints/optimized_detector.json \
    --max-test 500 \
    --verbose
```

**Quality Gate:** F1 score must be >= 0.75 (optimizing for recall to catch more derailments).

## Module Structure

```
scripts/flashpoints/
  __init__.py
  extract_cga_dataset.py   # Download and process CGA corpus
  dspy_dataset.py          # Load JSONL into DSPy Examples
  flashpoint_module.py     # DSPy Signature and Module definitions
  optimize_prompt.py       # GEPA optimization script
  README.md                # This file

data/flashpoints/
  flashpoints_train.jsonl  # Training examples (generated, gitignored)
  flashpoints_dev.jsonl    # Validation examples (generated, gitignored)
  flashpoints_test.jsonl   # Test examples (generated, gitignored)
  optimized_detector.json  # Optimized DSPy program (committed to git)
```

## How It Works

1. **FlashpointSignature**: Defines inputs (context, message) and outputs (will_derail, reasoning)
2. **FlashpointDetector**: Wraps the signature in a ChainOfThought module for step-by-step reasoning
3. **GEPA Optimizer**: Iteratively improves the prompt using feedback from incorrect predictions

The detector analyzes conversation context and a current message to predict whether the conversation shows signs of heading toward:
- Personal attacks
- Rule-violating behavior
- Moderator intervention
- Hostile escalation

## References

- [ConvoKit Documentation](https://convokit.cornell.edu/)
- [Conversations Gone Awry Corpus](https://convokit.cornell.edu/documentation/awry_cmv.html)
- [DSPy Documentation](https://dspy.ai/)
- [GEPA Optimizer](https://dspy.ai/deep-dive/optimizers/gepa/)
- [Original Research Paper](https://www.cs.cornell.edu/~cristian/Conversations_gone_awry.html) - "Conversations Gone Awry: Detecting Early Signs of Conversational Failure" (Zhang et al., 2018)
