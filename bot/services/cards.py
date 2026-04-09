import random
from bot.config import TEST_TYPE_LABELS, LEECH_THRESHOLD


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
        st = stats.get(tt, {})
        total = st.get("correct", 0) + st.get("wrong", 0)
        if total == 0:
            weights.append(3)  # untested types get high priority
        else:
            accuracy = st.get("correct", 0) / total
            # Lower accuracy = higher weight (1-5 scale)
            weights.append(max(1, round(5 * (1 - accuracy))))

    if sum(weights) == 0:
        return random.choice(options)

    return random.choices(options, weights=weights, k=1)[0]


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
            blank = sentence.replace(arabic, "________")
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
