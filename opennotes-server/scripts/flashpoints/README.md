# Conversation Flashpoint Detection

Scripts for training and optimizing the conversation flashpoint detection model using DSPy.

## Overview

This module uses the [Conversations Gone Awry (CGA)](https://convokit.cornell.edu/documentation/awry_cmv.html) corpus from ConvoKit to train a DSPy-optimized prompt for detecting early warning signs that conversations may derail into conflict.

The CGA-CMV corpus contains ~19,500 conversations and ~116,000 utterances from ChangeMyView discussions, annotated for whether they eventually derailed into personal attacks or rule violations.

### Scoring Approach

The detector outputs a continuous **derailment score** (0-100) rather than a binary classification:
- **0**: No risk of derailment
- **50**: Threshold for flagging (configurable)
- **100**: Certain derailment

This enables ROC-style safety-at-audit-budget evaluation and fine-grained risk ranking.

### Why GEPA over MIPRO?

We use DSPy's [GEPA optimizer](https://dspy.ai/deep-dive/optimizers/gepa/) with **comparative/contrastive training**:

- **Paired training**: Each training example pairs a derailing conversation with a non-derailing one, teaching the model to assign higher scores to derailing conversations
- **ScoreWithFeedback**: Rich textual feedback guides GEPA reflection on escalation signals
- **Sample-efficient**: Works well with smaller training sets
- **Reflective optimization**: Uses a separate reflection LM (gpt-5.2) for iterative improvement

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
- `flashpoints_train.jsonl` (20% of data) — single examples with `will_derail` labels
- `flashpoints_dev.jsonl` (30% of data)
- `flashpoints_test.jsonl` (50% of data)
- `flashpoints_paired_train.jsonl` — paired/contrastive examples for comparative training
- `flashpoints_paired_dev.jsonl`

The reversed allocation (smaller train, larger test) follows DSPy best practices to avoid overfitting during prompt optimization.

### 2. Optimize Prompt

Run GEPA optimization with comparative training:

```bash
# Default settings (gpt-5-mini, comparative training with paired examples)
uv run python scripts/flashpoints/optimize_prompt.py

# With custom model
uv run python scripts/flashpoints/optimize_prompt.py --model openai/gpt-5.1

# Heavy optimization for better results (takes longer)
uv run python scripts/flashpoints/optimize_prompt.py --auto heavy

# Add BootstrapFinetune as a second pass after GEPA
uv run python scripts/flashpoints/optimize_prompt.py --finetune

# Evaluate with safety-at-audit-budget curves
uv run python scripts/flashpoints/optimize_prompt.py --safety-curves

# Custom FPR thresholds for safety curves
uv run python scripts/flashpoints/optimize_prompt.py --safety-curves --fpr-levels 0.005 0.01 0.02 0.05
```

**Options:**
| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `openai/gpt-5-mini` | LLM for the detector |
| `--reflection-model` | `openai/gpt-5.2` | LLM for GEPA reflection |
| `--auto` | `medium` | Optimization level: light, medium, heavy |
| `--output` | `data/flashpoints/optimized_detector.json` | Where to save the optimized model |
| `--finetune` | off | Run BootstrapFinetune as second pass after GEPA |
| `--safety-curves` | off | Print safety-at-audit-budget curves after evaluation |
| `--fpr-levels` | `0.005 0.01 0.02 0.03 0.05` | FPR thresholds for safety curves |

The optimized detector is saved to `data/flashpoints/optimized_detector.json` and should be committed to git.

### 3. Evaluate

Evaluate an existing optimized model without re-running optimization:

```bash
uv run python scripts/flashpoints/optimize_prompt.py \
    --eval-only data/flashpoints/optimized_detector.json \
    --max-test 500 \
    --verbose \
    --safety-curves
```

**Safety-at-audit-budget evaluation** replaces fixed-threshold F1 by reporting True Positive Rate (TPR) at fixed False Positive Rate (FPR) thresholds (e.g., "at 1% FPR, we catch 85% of derailing conversations").

## Module Structure

```
scripts/flashpoints/
  __init__.py
  extract_cga_dataset.py   # Download and process CGA corpus (single + paired examples)
  dspy_dataset.py          # Load JSONL into DSPy Examples (single + paired loaders)
  flashpoint_module.py     # DSPy Signature, Module, comparative metric, TrainerProgram
  optimize_prompt.py       # GEPA optimization with comparative training + BootstrapFinetune
  README.md                # This file

data/flashpoints/
  flashpoints_train.jsonl         # Training examples (generated, gitignored)
  flashpoints_dev.jsonl           # Validation examples (generated, gitignored)
  flashpoints_test.jsonl          # Test examples (generated, gitignored)
  flashpoints_paired_train.jsonl  # Paired/contrastive training (generated, gitignored)
  flashpoints_paired_dev.jsonl    # Paired/contrastive validation (generated, gitignored)
  optimized_detector.json         # Optimized DSPy program (committed to git)
```

## How It Works

1. **FlashpointSignature**: Defines inputs (context, message) and output (derailment_score 0-100, reasoning)
2. **FlashpointDetector**: Wraps the signature in a ChainOfThought module for step-by-step reasoning
3. **FlashpointTrainerProgram**: Wrapper that runs the detector on both halves of a paired example (derailing + non-derailing) for comparative scoring
4. **comparative_flashpoint_metric**: Returns `ScoreWithFeedback` with rich textual guidance on escalation signals for GEPA reflection
5. **GEPA Optimizer**: Iteratively improves the prompt using comparative feedback from paired examples, with a separate reflection LM
6. **BootstrapFinetune** (optional): Second pass that finetunes weights using bootstrapped demonstrations from the GEPA-optimized model
7. **Safety-at-audit-budget**: Evaluates TPR at fixed FPR thresholds instead of fixed-threshold F1

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
