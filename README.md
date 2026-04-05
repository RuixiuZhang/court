# Court — Multi-Agent Courtroom Trial Simulation

An LLM-powered American civil courtroom trial simulation system where 16 AI agents assume different courtroom roles (judge, attorneys, witnesses, jury) to autonomously conduct a full trial and generate DPO (Direct Preference Optimization) training datasets.

## Features

- **16 Autonomous Agents**: Judge controls trial pace, attorneys argue adversarially, witnesses respond to examinations, 8 jurors vote independently
- **Full Trial Pipeline**: Opening statements → Evidence examination → Closing arguments → Jury deliberation → Final verdict
- **Judge-Agent Driven**: Judge autonomously advances the trial via 6 JSON skill commands (call to speak, direct examination, cross examination, jury poll, etc.)
- **DPO Dataset Generation**: Automatically records winning/losing side arguments and outputs standard DPO triplet format for preference alignment fine-tuning
- **Diverse Jury Panel**: 8 jurors with distinct personality traits (contract literalist, privacy advocate, business innovator, moral absolutist, etc.)
- **Anti-Role-Hijacking**: Hard truncation mechanisms prevent role confusion; witnesses strictly maintain their side's position

## Architecture

```
__main__.py / benchmark.py    ← Entry: launch benchmark
    └─ trial.py               ← Core: 5-phase state machine driving the trial
        ├─ examination.py     ← Examination: direct & cross examination (3-round Q&A)
        ├─ jury.py            ← Jury: multi-threaded parallel voting
        ├─ api.py             ← HTTP client: connection pooling + retry
        ├─ prompts.py         ← Prompt registry: role profiles + judge skills + juror personalities
        ├─ config.py          ← Config: model assignment + context limits
        └─ utils.py           ← Utilities: JSON parsing + context management
```

## Quick Start

### Prerequisites

- Python 3.10+
- [LM Studio](https://lmstudio.ai/) running locally with Qwen-series models loaded
- `requests` library

### Installation

```bash
pip install requests
```

### Configuration

Edit `config.py` to set the LM Studio endpoint and model instances:

```python
BASE_API_URL = "http://192.168.2.1:1234/api/v1/chat"

MODEL_INSTANCES = [
    "qwen3-4b-instance-1",
    "qwen3-4b-instance-2",
    # ... 16 model instances total
]
```

### Usage

```bash
python -m court
```

This runs a complete trial and appends the DPO data to `dpo_dataset.jsonl`.

## DPO Data Format

Each trial produces one JSONL record:

```json
{
  "prompt": "Case background description",
  "chosen": ["List of winning side arguments"],
  "rejected": ["List of losing side arguments"],
  "chosen_score": 0.85,
  "rejected_score": -1.12,
  "metadata": {
    "verdict": "plaintiff/defendant",
    "jury_tally": {"plaintiff": 5, "defendant": 3},
    "total_tokens": 12345,
    "duration_s": 180.5
  }
}
```

Scoring formula: winner gets +1.0, loser gets -1.0, with a verbosity penalty of min(0.1 × ln(tokens/500), 0.5).

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_CONTEXT_CHARS` | 3200 | Judge context window size |
| `RESPONSE_EXCERPT_CHARS` | 320 | Trial transcript excerpt length |
| `MAX_CASE_BG_CHARS` | 1200 | Max case background characters |
| `MAX_JUDGE_TURNS` | 100 | Hard limit on trial rounds |

## Dependencies

- `requests` — HTTP client (connection pooling + auto-retry)
- Python standard library: `json`, `time`, `math`, `concurrent.futures`

## License

MIT
