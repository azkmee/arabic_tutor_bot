import random
from bot.config import TEST_TYPE_LABELS


def build_card(item, prog):
    """Build a review card message and return (text, test_type)."""
    arabic = item.get("arabic", "")
    trans = item.get("transliteration", "")
    eng = item.get("translation", "")
    root = item.get("root", "")
    plural = item.get("plural", "")
    itype = item.get("type", "word")
    level = prog.get("srs_level", 0)
    streak = prog.get("streak", 0)

    last_test = prog.get("last_test_type", "")
    weak = prog.get("weak_test_types", [])

    if itype == "grammar_rule":
        test_type = "grammar"
    else:
        options = ["meaning", "meaning"]
        if plural:
            options.append("plural")
        if root:
            options.append("root_derive")
        options.append("fill_blank")
        candidates = [t for t in weak if t in options] or options
        candidates = [t for t in candidates if t != last_test] or candidates
        test_type = random.choice(candidates)

    label = TEST_TYPE_LABELS.get(test_type, "💬 Review")
    stars = "⭐" * min(level, 8)
    streak_str = f"🔥 {streak} day streak" if streak >= 2 else ""

    lines = ["<b>مراجعة يومية</b> — Daily Review", "─" * 28, label, ""]

    if test_type == "meaning":
        lines += [f"<b>{arabic}</b>", f"<i>({trans})</i>" if trans else ""]
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
        ]
        lines += [
            "",
            f"<tg-spoiler>➡️  {arabic}  ({trans})</tg-spoiler>",
            "<i>Tap to reveal, then rate:</i>",
        ]

    elif test_type == "fill_blank":
        sentence = item.get("example_sentence", "")
        if sentence:
            blank = sentence.replace(arabic, "________")
            lines += [
                blank,
                "",
                f"<tg-spoiler>➡️  {arabic}  ({eng})</tg-spoiler>",
                "<i>Tap to reveal, then rate:</i>",
            ]
        else:
            lines += [
                f"<b>{arabic}</b>  ({trans})",
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

    lines += ["", "─" * 28, f"SRS level {level}/8  {stars}  {streak_str}"]

    return "\n".join(l for l in lines if l is not None), test_type


def build_paragraph_card(paragraph):
    """Build a reading comprehension card from a paragraph document."""
    arabic = paragraph.get("text_arabic", "")
    english = paragraph.get("text_english", "")
    words = paragraph.get("words_used", [])
    difficulty = paragraph.get("difficulty", "short")

    label = "📖 Reading Comprehension" if difficulty == "short" else "📖 Extended Reading"
    lines = [
        "<b>مراجعة يومية</b> — Daily Review",
        "─" * 28,
        label,
        "",
        arabic,
        "",
        f"<tg-spoiler>➡️  {english}</tg-spoiler>",
        "<i>Tap to reveal translation, then rate:</i>",
        "",
        "─" * 28,
        f"Words used: {', '.join(words)}" if words else "",
    ]

    return "\n".join(l for l in lines if l is not None)
