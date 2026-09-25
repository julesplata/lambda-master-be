"""Generate seeds/coverage_report.md from the seed question files.

The report is the source of truth for what questions exist. Run it after
adding or editing seed questions:

    python seeds/generate_coverage.py

It validates every file against the API schema, checks for duplicate
(title, category) pairs (the bulk endpoint rejects those) and duplicate
(concept, format, category) triples (the dedup rule), checks that correct
answers are spread across option positions, then rewrites
seeds/coverage_report.md. Never edit coverage_report.md by hand.
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from app.schemas.question import BulkQuestionCreate  # noqa: E402

SEEDS_DIRECTORY = Path(__file__).resolve().parent
REPORT_PATH = SEEDS_DIRECTORY / "coverage_report.md"

# Bulk import stores options in file order, so an author habit like "correct
# answer first" becomes a pattern in the bank. Fail when one position holds more
# than this share of a file's correct answers. Files smaller than the minimum are
# too small for the share to mean anything and are only counted in the total.
MAX_CORRECT_POSITION_SHARE = 0.40
MIN_QUESTIONS_FOR_BALANCE_CHECK = 10


def load_seed_files() -> dict[str, list[dict]]:
    seed_files = {}
    for path in sorted(SEEDS_DIRECTORY.glob("*.json")):
        payload = json.loads(path.read_text())
        if isinstance(payload, dict) and "questions" in payload:
            seed_files[path.name] = payload["questions"]
    return seed_files


def validate(seed_files: dict[str, list[dict]]) -> list[str]:
    problems = []
    for filename, questions in seed_files.items():
        try:
            BulkQuestionCreate.model_validate({"questions": questions})
        except Exception as error:
            problems.append(f"{filename}: schema validation failed: {error}")
        for question in questions:
            missing = [
                field for field in ("concept", "format") if field not in question
            ]
            if missing:
                problems.append(f"{filename}: '{question['title']}' missing {missing}")
    return problems


def find_duplicates(seed_files: dict[str, list[dict]]) -> list[str]:
    problems = []
    title_counts = Counter()
    concept_counts = Counter()
    for questions in seed_files.values():
        for question in questions:
            title_counts[(question["title"], question["category"])] += 1
            key = (
                question.get("concept"),
                question.get("format"),
                question["category"],
            )
            concept_counts[key] += 1
    for (title, category), count in title_counts.items():
        if count > 1:
            problems.append(
                f"duplicate (title, category): ({title!r}, {category!r}) x{count}"
            )
    for (concept, question_format, category), count in concept_counts.items():
        if count > 1:
            problems.append(
                f"dedup violation: concept {concept!r} appears {count}x "
                f"as {question_format} in {category!r}"
            )
    return problems


def correct_position_problem(label: str, questions: list[dict]) -> str | None:
    positions = Counter(
        index
        for question in questions
        for index, option in enumerate(question["options"])
        if option.get("is_correct")
    )
    if not positions:
        return None
    position, count = positions.most_common(1)[0]
    share = count / sum(positions.values())
    if share <= MAX_CORRECT_POSITION_SHARE:
        return None
    return (
        f"{label}: {count} of {sum(positions.values())} correct answers ({share:.0%}) "
        f"are at option index {position}; shuffle the options "
        f"(limit {MAX_CORRECT_POSITION_SHARE:.0%})"
    )


def check_answer_positions(seed_files: dict[str, list[dict]]) -> list[str]:
    problems = []
    for filename, questions in seed_files.items():
        if len(questions) >= MIN_QUESTIONS_FOR_BALANCE_CHECK:
            problem = correct_position_problem(filename, questions)
            if problem:
                problems.append(problem)
    all_questions = [q for questions in seed_files.values() for q in questions]
    problem = correct_position_problem("all seed files", all_questions)
    if problem:
        problems.append(problem)
    return problems


def render_category_section(category: str, questions: list[dict]) -> list[str]:
    lines = [f"## {category} ({len(questions)} questions)", ""]
    format_counts = Counter(question["format"] for question in questions)
    difficulty_counts = Counter(question["difficulty"] for question in questions)
    lines.append(
        "Formats: "
        + ", ".join(f"{name}: {count}" for name, count in sorted(format_counts.items()))
    )
    lines.append(
        "Difficulty: "
        + ", ".join(
            f"{name}: {difficulty_counts[name]}"
            for name in ("beginner", "intermediate", "advanced")
        )
    )
    lines.append("")
    lines.append("| Concept | Format | Difficulty | Title | File |")
    lines.append("|---|---|---|---|---|")
    ordered = sorted(questions, key=lambda q: (q["concept"], q["format"]))
    for question in ordered:
        lines.append(
            f"| {question['concept']} | {question['format']} | {question['difficulty']} "
            f"| {question['title']} | {question['source_file']} |"
        )
    lines.append("")
    return lines


def render_cross_format_notes(questions: list[dict]) -> list[str]:
    concepts_by_format = defaultdict(set)
    for question in questions:
        concepts_by_format[question["format"]].add(question["concept"])
    situational_only = sorted(
        concepts_by_format["situational"] - concepts_by_format["recall"]
    )
    if not situational_only:
        return []
    lines = [
        "## Situational-only concepts",
        "",
        "These concepts exist only in situational form — candidates for a recall counterpart:",
        "",
    ]
    lines.extend(f"- {concept}" for concept in situational_only)
    lines.append("")
    return lines


def build_report(seed_files: dict[str, list[dict]]) -> str:
    all_questions = []
    for filename, questions in seed_files.items():
        for question in questions:
            all_questions.append({**question, "source_file": filename})

    lines = [
        "# Question Coverage Report",
        "",
        f"Generated by `seeds/generate_coverage.py` on {date.today().isoformat()}. "
        "Do not edit by hand — rerun the script after changing seed files.",
        "",
        f"**Total: {len(all_questions)} questions across {len(seed_files)} files.**",
        "",
    ]
    by_category = defaultdict(list)
    for question in all_questions:
        by_category[question["category"]].append(question)
    for category in sorted(by_category):
        lines.extend(render_category_section(category, by_category[category]))
    lines.extend(render_cross_format_notes(all_questions))
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    seed_files = load_seed_files()
    problems = (
        validate(seed_files)
        + find_duplicates(seed_files)
        + check_answer_positions(seed_files)
    )
    if problems:
        print("PROBLEMS FOUND:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    REPORT_PATH.write_text(build_report(seed_files))
    total = sum(len(questions) for questions in seed_files.values())
    print(f"OK: {total} questions in {len(seed_files)} files -> {REPORT_PATH.name}")


if __name__ == "__main__":
    main()
