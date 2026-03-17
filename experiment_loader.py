"""
experiment_loader.py
====================
Dataset loaders for the AiTM paper replication experiments.

Provides load functions for the three benchmark datasets:
    - MMLU       (Hendrycks et al., 2020)  — multiple choice, biology + physics
    - HumanEval  (Chen et al., 2021)       — 164 hand-written coding problems
    - MBPP       (Austin et al., 2021)     — 974 programming tasks (sanitized split)

Each loader returns a list of dicts.  Every dict is guaranteed to have a
`_prompt` key containing the string to pass verbatim to user.initiate_chat().

Usage
-----
    from experiment_loader import load_mmlu, load_humaneval, load_mbpp

    tasks = load_mmlu("data/mmlu/test", subjects=["biology"], n=20)
    tasks = load_humaneval("data/test-00000-of-00001.parquet", n=20)
    tasks = load_mbpp("data/sanitized-mbpp.json", n=20)

Dataset file locations (defaults)
----------------------------------
  data/mmlu/test/                      directory of per-subject CSVs (no header)
                                       columns (positional): question, A, B, C, D, answer
  data/test-00000-of-00001.parquet     HumanEval from HuggingFace
                                       fields: task_id, prompt, canonical_solution, test, entry_point
  data/sanitized-mbpp.json             sanitized MBPP from Google Research
                                       fields: task_id, prompt, entry_point, canonical_solution, test
                                       NOTE: same shape as HumanEval, NOT the raw mbpp.jsonl schema
"""

import os
import json
import random
from pathlib import Path

import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# MMLU
# ──────────────────────────────────────────────────────────────────────────────

# Subjects used in the AiTM paper (Section 4.1: "biology and physics domains")
# Matches any CSV whose filename contains one of these fragments, picking up
# college_biology, high_school_biology, college_physics, high_school_physics, etc.
AITM_MMLU_SUBJECTS = ["biology", "physics"]


def load_mmlu(mmlu_dir: str, mode: str = "aitm", subjects: list | None = None,
              n: int = 0, seed: int = 42) -> list[dict]:
    """
    Load MMLU from a directory of per-subject CSVs (Hendrycks test split).

    Files are named like `college_biology_test.csv` with no header row.
    Column layout (positional): question, A, B, C, D, answer

    Args:
        mmlu_dir:  Path to directory containing per-subject CSV files.
        mode:      "aitm"   (default) loads only biology + physics CSVs,
                            matching the exact subjects used in the AiTM paper.
                   "full"   loads every CSV in the directory.
                   "custom" loads only CSVs matching the `subjects` fragments.
        subjects:  Used only when mode="custom". List of filename fragments,
                   e.g. ["chemistry", "mathematics"].
        n:         Max samples to return (0 = all).
        seed:      Random seed for sampling.

    Returns:
        List of dicts with keys:
            task_id, question, choices, answer, subject, _prompt
    """
    mmlu_dir = Path(mmlu_dir)
    csv_files = sorted(mmlu_dir.glob("*_test.csv"))
    if not csv_files:
        csv_files = sorted(mmlu_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in MMLU directory: {mmlu_dir}")

    if mode == "aitm":
        filter_subjects = AITM_MMLU_SUBJECTS
    elif mode == "full":
        filter_subjects = None
    elif mode == "custom":
        if not subjects:
            raise ValueError("mode='custom' requires a non-empty subjects list.")
        filter_subjects = subjects
    else:
        raise ValueError(f"Unknown mode '{mode}'. Choose from: aitm, full, custom")

    if filter_subjects:
        csv_files = [f for f in csv_files if any(s in f.stem for s in filter_subjects)]
        if not csv_files:
            raise ValueError(f"No MMLU files matched subjects: {filter_subjects}")

    rows = []
    for csv_path in csv_files:
        subject = csv_path.stem.replace("_test", "").replace("_", " ")
        df = pd.read_csv(csv_path, header=None,
                         names=["question", "A", "B", "C", "D", "answer"])
        for idx, row in df.iterrows():
            prompt = (
                f"The following is a multiple choice question about {subject}.\n\n"
                f"Question: {row['question']}\n"
                f"A. {row['A']}\n"
                f"B. {row['B']}\n"
                f"C. {row['C']}\n"
                f"D. {row['D']}\n\n"
                "Answer with only the letter of the correct choice (A, B, C, or D)."
            )
            rows.append({
                "task_id":  f"mmlu/{subject.replace(' ', '_')}/{idx}",
                "question": row["question"],
                "choices":  [row["A"], row["B"], row["C"], row["D"]],
                "answer":   str(row["answer"]).strip(),
                "subject":  subject,
                "_prompt":  prompt,
            })

    if n and n < len(rows):
        random.seed(seed)
        rows = random.sample(rows, n)

    print(f"[loader] MMLU: {len(rows)} tasks  ({mmlu_dir})")
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# HumanEval
# ──────────────────────────────────────────────────────────────────────────────

def load_humaneval(path: str, n: int = 0, seed: int = 42) -> list[dict]:
    """
    Load HumanEval.

    Accepts:
        data/test-00000-of-00001.parquet   HuggingFace download
        data/HumanEval.jsonl               OpenAI repo
        data/HumanEval.jsonl.gz            OpenAI repo, gzipped

    Args:
        path:  Path to the HumanEval file.
        n:     Max samples to return (0 = all).
        seed:  Random seed for sampling.

    Returns:
        List of dicts with keys:
            task_id, prompt, canonical_solution, test, entry_point, _prompt
    """
    path = Path(path)
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
        raw = df.to_dict(orient="records")
    else:
        import gzip
        opener = gzip.open if path.suffix == ".gz" else open
        raw = []
        with opener(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    raw.append(json.loads(line))

    rows = []
    for item in raw:
        prompt_text = (
            "Complete the following Python function. "
            "Return ONLY the completed function body, no explanation.\n\n"
            f"{item['prompt']}"
        )
        rows.append({
            "task_id":            item["task_id"],
            "prompt":             item["prompt"],
            "canonical_solution": item.get("canonical_solution", ""),
            "test":               item.get("test", ""),
            "entry_point":        item.get("entry_point", ""),
            "_prompt":            prompt_text,
        })

    if n and n < len(rows):
        random.seed(seed)
        rows = random.sample(rows, n)

    print(f"[loader] HumanEval: {len(rows)} tasks  ({path})")
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# MBPP
# ──────────────────────────────────────────────────────────────────────────────

def load_mbpp(path: str, n: int = 0, seed: int = 42) -> list[dict]:
    """
    Load MBPP — handles both the sanitized and raw schemas automatically.

    Sanitized (sanitized-mbpp.json, Google Research — a JSON array):
        task_id, prompt, entry_point, canonical_solution, test
        Same shape as HumanEval — this is the default file to use.

    Raw (mbpp.jsonl):
        task_id (int), text, code, test_list (list of assert strings)

    The correct schema is detected by checking for the presence of "prompt".

    Args:
        path:  Path to the MBPP jsonl file.
        n:     Max samples to return (0 = all).
        seed:  Random seed for sampling.

    Returns:
        List of dicts with keys (sanitized schema):
            task_id, prompt, canonical_solution, test, entry_point, _prompt
        Or (raw schema):
            task_id, text, code, test_list, _prompt
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Detect format: JSON array (sanitized .json) vs JSONL (raw .jsonl)
    if content.startswith("["):
        raw = json.loads(content)          # sanitized-mbpp.json — a JSON array
    else:
        raw = [json.loads(l) for l in content.splitlines() if l.strip()]  # raw .jsonl

    rows = []
    for item in raw:
        if "prompt" in item:
            # Sanitized schema — same shape as HumanEval
            prompt_text = (
                "Complete the following Python function. "
                "Return ONLY the completed function body, no explanation.\n\n"
                f"{item['prompt']}"
            )
            rows.append({
                "task_id":            str(item["task_id"]),
                "prompt":             item["prompt"],
                "canonical_solution": item.get("canonical_solution", ""),
                "test":               item.get("test", ""),
                "entry_point":        item.get("entry_point", ""),
                "_prompt":            prompt_text,
            })
        else:
            # Raw schema fallback
            tests_str = "\n".join(item.get("test_list", []))
            prompt_text = (
                "Write a Python function to solve the following task. "
                "Return ONLY the function code, no explanation.\n\n"
                f"Task: {item['text']}\n\n"
                f"Your function must pass these tests:\n{tests_str}"
            )
            rows.append({
                "task_id":   str(item["task_id"]),
                "text":      item["text"],
                "code":      item.get("code", ""),
                "test_list": item.get("test_list", []),
                "_prompt":   prompt_text,
            })

    if n and n < len(rows):
        random.seed(seed)
        rows = random.sample(rows, n)

    print(f"[loader] MBPP: {len(rows)} tasks  ({path})")
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE: load all three at once
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATHS = {
    "mmlu":      os.path.join(BASE_DIR, "data", "mmlu", "test"),
    "humaneval": os.path.join(BASE_DIR, "data", "test-00000-of-00001.parquet"),
    "mbpp":      os.path.join(BASE_DIR, "data", "sanitized-mbpp.json"),
}


def load_dataset(name: str, path: str | None = None, n: int = 20,
                 seed: int = 42, subjects: list | None = None,
                 mmlu_mode: str = "aitm") -> list[dict]:
    """
    Load a single dataset by name.

    Args:
        name:     One of "mmlu", "humaneval", "mbpp".
        path:     Override the default file path.
        n:        Max samples (0 = all).
        seed:     Random seed.
        subjects: MMLU only — used when mmlu_mode="custom".
        mmlu_mode: MMLU only — "aitm" (bio+physics), "full", or "custom".

    Returns:
        List of task dicts, each with a `_prompt` key.
    """
    resolved = path or DEFAULT_PATHS.get(name)
    if resolved is None:
        raise ValueError(f"Unknown dataset '{name}'. Choose from: mmlu, humaneval, mbpp")
    if not Path(resolved).exists():
        raise FileNotFoundError(f"Dataset path does not exist: {resolved}")

    if name == "mmlu":
        return load_mmlu(resolved, mode=mmlu_mode, subjects=subjects, n=n, seed=seed)
    elif name == "humaneval":
        return load_humaneval(resolved, n=n, seed=seed)
    elif name == "mbpp":
        return load_mbpp(resolved, n=n, seed=seed)
    else:
        raise ValueError(f"Unknown dataset '{name}'. Choose from: mmlu, humaneval, mbpp")


def load_all(n: int = 20, seed: int = 42,
             mmlu_subjects: list | None = None) -> dict[str, list[dict]]:
    """
    Load all three datasets using default paths.

    Returns:
        Dict mapping dataset name -> list of task dicts.
        Skips any dataset whose default path does not exist (with a warning).
    """
    datasets = {}
    for name, path in DEFAULT_PATHS.items():
        if not Path(path).exists():
            print(f"[loader] WARN: {name} not found at {path}, skipping.")
            continue
        kwargs = {"n": n, "seed": seed}
        if name == "mmlu" and mmlu_subjects:
            kwargs["subjects"] = mmlu_subjects
        datasets[name] = load_dataset(name, path, **kwargs)
    return datasets
