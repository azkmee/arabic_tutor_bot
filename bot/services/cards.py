import random
import re
from bot.config import TEST_TYPE_LABELS, LEECH_THRESHOLD
from bot.db import _stats_totals

# Arabic diacritics (tashkeel + Quranic small marks + dagger alif).
_ARABIC_DIACRITICS = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)
_AL_PREFIX = re.compile(r"^\u0627\u0644")
_LEADING_ARABIC = re.compile(r"^([\u0600-\u06FF\u0750-\u077F]+)(.*)$")


def _strip_diacritics(s: str) -> str:
    return _ARABIC_DIACRITICS.sub("", s)


def _blank_word_in_sentence(sentence: str, word: str) -> str:
    """Replace `word` in `sentence` with a blank, tolerating Arabic diacritic
    differences and an optional definite-article (الـ) prefix on the sentence
    token.
    """
    target = _AL_PREFIX.sub("", _strip_diacritics(word))
    if not target:
        return sentence

    parts = re.split(r"(\s+)", sentence)
    replaced = False
    out = []
    for tok in parts:
        if replaced or not tok or tok.isspace():
            out.append(tok)
            continue
        m = _LEADING_ARABIC.match(tok)
        if not m:
            out.append(tok)
            continue
        core, rest = m.group(1), m.group(2)
        normalized = _AL_PREFIX.sub("", _strip_diacritics(core))
        if normalized == target:
            out.append("________" + rest)
            replaced = True
        else:
            out.append(tok)
    return "".join(out) if replaced else sentence

# Probability of rendering a card as MCQ when distractors are available.
# Tunable: start 50/50 so reveal-vs-MCQ comparisons stay meaningful while
# both formats are alive.
MCQ_PROBABILITY = 0.5


def _pick_test_type(item, prog):
    """Pick a test type using weighted selection based on test_type_stats."""
    itype = item.get("type", "noun")

    if itype == "grammar_rule":
        return "grammar"

    # Build available test types based on word data
    options = ["meaning"]
    if item.get("plural"):
        options.append("plural")
    if item.get("root"):
        options.append("root_derive")
    if item.get("example_sentence"):
        options.append("fill_blank")

    # Weight by weakness: test_type_stats drives selection
    stats = prog.get("test_type_stats", {})
    last_test = prog.get("last_test_type", "")

    # Calculate weights: lower accuracy = higher weight
    weights = []
    for tt in options:
        if tt == last_test and len(options) > 1:
            weights.append(0)  # avoid repeating same test
            continue
        c, w = _stats_totals(stats.get(tt))
        total = c + w
        if total == 0:
            weights.append(3)  # untested types get high priority
        else:
            accuracy = c / total
            # Lower accuracy = higher weight (1-5 scale)
            weights.append(max(1, round(5 * (1 - accuracy))))

    if sum(weights) == 0:
        return random.choice(options)

    return random.choices(options, weights=weights, k=1)[0]


# Answer field per test type — used to score MCQ on the server and to compose
# the option list (correct answer is always this field; distractors live on
# the vocab item under mcq_options[test_type]).
ANSWER_FIELD = {
    "meaning": "translation",
    "plural": "plural",
    "root_derive": "arabic",
    "fill_blank": "arabic",
    "grammar": "translation",
}


def _mcq_distractors(item, test_type):
    options_doc = item.get("mcq_options") or {}
    distractors = options_doc.get(test_type) or []
    distractors = [d for d in distractors if isinstance(d, str) and d.strip()]
    return distractors


def pick_format(item, test_type):
    """Return "mcq" if distractors are present and the coin flips that way."""
    distractors = _mcq_distractors(item, test_type)
    if len(distractors) >= 3 and random.random() < MCQ_PROBABILITY:
        return "mcq"
    return "reveal"


def build_mcq_options(item, test_type):
    """Shuffle 3 distractors + correct answer; return (options, correct)."""
    correct = (item.get(ANSWER_FIELD[test_type]) or "").strip()
    distractors = _mcq_distractors(item, test_type)[:3]
    if not correct or len(distractors) < 3:
        return [], ""
    options = distractors + [correct]
    random.shuffle(options)
    return options, correct


def build_card(item, prog):
    """Build a review card message and return (text, test_type)."""
    arabic = item.get("arabic", "")
    trans = item.get("transliteration", "")
    eng = item.get("translation", "")
    root = item.get("root", "")
    plural = item.get("plural", "")
    level = prog.get("srs_level", 0)
    streak = prog.get("streak", 0)
    lapse_count = prog.get("lapse_count", 0)

    test_type = _pick_test_type(item, prog)

    label = TEST_TYPE_LABELS.get(test_type, "💬 Review")
    stars = "⭐" * min(level, 8)
    streak_str = f"🔥 {streak}" if streak >= 2 else ""
    leech_str = "🩸 Leech" if lapse_count >= LEECH_THRESHOLD else ""
    status_parts = [s for s in [f"SRS {level}/8", stars, streak_str, leech_str] if s]

    lines = ["<b>مراجعة يومية</b> — Daily Review", "─" * 28, label, ""]

    if test_type == "meaning":
        lines += [f"<b>{arabic}</b>"]
        if trans:
            lines.append(f"<i>({trans})</i>")
        lines += [
            "",
            f"<tg-spoiler>➡️  {eng}</tg-spoiler>",
            "<i>Tap to reveal, then rate yourself below:</i>",
        ]

    elif test_type == "plural":
        lines += [f"<b>{arabic}</b>  —  {eng}", "", "What is the plural (جمع)?"]
        if plural:
            lines += [
                "",
                f"<tg-spoiler>➡️  {plural}</tg-spoiler>",
                "<i>Tap to reveal, then rate:</i>",
            ]

    elif test_type == "root_derive":
        lines += [
            f"Root: <b>{root}</b>",
            "",
            f"Derive the word that means: <b>{eng}</b>",
            "",
            f"<tg-spoiler>➡️  {arabic}  ({trans})</tg-spoiler>",
            "<i>Tap to reveal, then rate:</i>",
        ]

    elif test_type == "fill_blank":
        sentence = item.get("example_sentence", "")
        example_trans = item.get("example_translation", "")
        if sentence:
            blank = _blank_word_in_sentence(sentence, arabic)
            lines += [blank, ""]
            reveal = f"➡️  {arabic}  ({eng})"
            if example_trans:
                reveal += f"\n📝 {example_trans}"
            lines += [
                f"<tg-spoiler>{reveal}</tg-spoiler>",
                "<i>Tap to reveal, then rate:</i>",
            ]
        else:
            # Fallback to meaning if no example sentence
            lines += [
                f"<b>{arabic}</b>",
                "",
                f"<tg-spoiler>➡️  {eng}</tg-spoiler>",
                "<i>Tap to reveal, then rate:</i>",
            ]

    elif test_type == "grammar":
        rule_desc = item.get("translation", "")
        example = item.get("example_sentence", "")
        lines += ["📐 Grammar rule:", f"<b>{arabic}</b>", f"<i>{rule_desc}</i>"]
        if example:
            lines += [
                "",
                f"Example: <tg-spoiler>{example}</tg-spoiler>",
                "<i>Tap to reveal, then rate:</i>",
            ]

    lines += ["", "─" * 28, "  ".join(status_parts)]

    return "\n".join(l for l in lines if l is not None), test_type


def build_paragraph_card(paragraph):
    """Build a reading comprehension card from a paragraph document."""
    # Support both field naming conventions for backward compat
    arabic = paragraph.get("text_arabic") or paragraph.get("arabic_text", "")
    english = paragraph.get("text_english", "")
    title = paragraph.get("title", "")
    questions = paragraph.get("comprehension_questions", [])

    lines = [
        "<b>مراجعة يومية</b> — Daily Review",
        "─" * 28,
        "📖 Reading Comprehension",
        "",
    ]
    if title:
        lines += [f"<b>{title}</b>", ""]
    lines.append(arabic)

    if english:
        lines += ["", f"<tg-spoiler>➡️  {english}</tg-spoiler>"]

    if questions:
        lines += ["", "<b>أسئلة:</b>"]
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")

    lines += ["", "─" * 28]

    return "\n".join(l for l in lines if l is not None)
