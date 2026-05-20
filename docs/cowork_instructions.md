# Arabic Tutor — Cowork Routine

This is the prompt the Claude Desktop "cowork" routine should follow on each
scheduled run. All generation happens here in the Desktop conversation
(funded by your Claude subscription). The MCP tools and the Render API
endpoints listed below are dumb write sinks — Python only, no LLM calls —
so they do **not** consume any Anthropic API quota.

There are two submit paths and they are interchangeable; pick whichever is
convenient for the machine you're on:

- **MCP** (local, when the MCP server is registered in Claude Desktop):
  call `add_words`, `add_passages`, etc. directly.
- **HTTP** (when running off-laptop): POST to the Render service. Every
  cowork endpoint requires the header `X-Cowork-Token: <COWORK_SECRET>`.

If you submit via MCP, you do not need the token.

---

## Pass 1 — Vocabulary enrichment

1. Call `get_pending_words()` (MCP) or `GET /api/cowork/raw-passages` is
   NOT this one — that's pass 2. For words, only MCP currently exposes a
   "pending" view; use MCP for this pass.
2. For each pending raw word, produce a full enrichment record. Required
   fields: `arabic`, `transliteration`, `translation`, `type` (one of
   `noun`, `verb`, `adjective`, `adverb`, `preposition`, `particle`,
   `phrase`, `grammar_rule`). Add `root`, `plural`, `gender`,
   `example_sentence`, `example_translation`, `tags` whenever they apply.
3. Add `mcq_options` for every applicable test type. Each value is a list
   of exactly 3 plausible-but-wrong strings — never duplicating the
   correct answer or another distractor; same part-of-speech as the
   answer; same morphological category where possible (e.g. for `plural`,
   distractors are valid Arabic plural patterns).

   ```jsonc
   {
     "arabic": "كِتَاب",
     "transliteration": "kitāb",
     "translation": "book",
     "type": "noun",
     "root": "ك ت ب",
     "plural": "كُتُب",
     "gender": "masculine",
     "example_sentence": "أَقْرَأُ كِتَابًا جَدِيدًا.",
     "example_translation": "I am reading a new book.",
     "mcq_options": {
       "meaning":     ["pen", "school", "lesson"],
       "plural":      ["كَاتِب", "كُتَّاب", "مَكْتَب"],
       "root_derive": ["قَلَم", "دَفْتَر", "مَكْتَبَة"],
       "fill_blank":  ["قَلَم", "دَرْس", "مَجَلَّة"]
     }
   }
   ```

4. Dedup: skip any `arabic` already in `vocabulary_items` (call
   `search_words(query)` if uncertain).
5. Submit:
   - MCP: `add_words([... ])`
   - HTTP: `POST /api/cowork/vocabulary` with the same JSON array as body.

The DB layer creates the matching `item_progress` doc and flips any
matching pending `raw_words` to processed.

---

## Pass 2 — Imported passages (enrich what the user pasted)

1. Call `get_pending_passages()` (MCP) or `GET /api/cowork/raw-passages`.
   Each item is `{id, text, source, created_at}`.
2. For each:
   - Add full tashkeel to every Arabic word — including the title and the
     comprehension questions. Diacritization is non-negotiable; the UI
     trusts cowork to provide it.
   - Split into sentences. Each sentence becomes a `lines[]` entry.
   - Gloss every Arabic token in the sentence under `words[]` — including
     particles (e.g. `فِي`, `إِلَى`, `وَ`). Use the existing
     `vocabulary_items` translation when available; otherwise infer.
   - Write `english` for each line (sentence translation).
   - Compose a 2–4-word `title` and 2–3 short Arabic
     `comprehension_questions` (also fully diacritized).
3. Set `raw_passage_id` to the staging doc's `id` so the staging entry
   flips to processed.

   ```jsonc
   {
     "raw_passage_id": "65f9e7b2c1a0d4e3b7f1d9a4",
     "title": "فِي المَكْتَبَة",
     "difficulty": "short",
     "lines": [
       {
         "arabic": "ذَهَبَ أَحْمَدُ إِلَى المَكْتَبَةِ.",
         "english": "Ahmad went to the library.",
         "words": [
           {"arabic": "ذَهَبَ",   "translation": "went"},
           {"arabic": "أَحْمَدُ",  "translation": "Ahmad"},
           {"arabic": "إِلَى",     "translation": "to"},
           {"arabic": "المَكْتَبَةِ", "translation": "the library"}
         ]
       },
       {
         "arabic": "اِسْتَعَارَ كِتَابًا جَدِيدًا.",
         "english": "He borrowed a new book.",
         "words": [
           {"arabic": "اِسْتَعَارَ", "translation": "borrowed"},
           {"arabic": "كِتَابًا",    "translation": "a book"},
           {"arabic": "جَدِيدًا",    "translation": "new"}
         ]
       }
     ],
     "comprehension_questions": [
       "إِلَى أَيْنَ ذَهَبَ أَحْمَدُ؟",
       "مَاذَا اِسْتَعَارَ؟"
     ]
   }
   ```

4. Submit:
   - MCP: `add_passages([...])`
   - HTTP: `POST /api/cowork/passages` with the JSON array as body.

---

## Pass 3 — Generated passages (drive from due vocab)

1. Call `get_vocab_for_passage(limit=20)` (MCP) or
   `GET /api/cowork/vocab-for-passage?limit=20`. Each item carries
   `reason: "due" | "weak" | "recent"` so you can prioritize coverage.
2. Draft 1–3 short, **fully-diacritized** passages that weave in at
   least 6 of those words — bias toward `due` and `weak` items.
3. Output the same `lines` shape as pass 2. Omit `raw_passage_id` (these
   aren't from staging).
4. Submit via the same `add_passages` / `POST /api/cowork/passages`.

---

## Output spec (canonical)

### Vocab item

```jsonc
{
  "arabic": "<word with tashkeel preferred>",
  "transliteration": "<romanized>",
  "translation": "<english gloss>",
  "type": "noun|verb|adjective|adverb|preposition|particle|phrase|grammar_rule",
  "root": "<optional>",
  "plural": "<optional>",
  "gender": "masculine|feminine",
  "example_sentence": "<optional>",
  "example_translation": "<optional>",
  "tags": ["MSA", "beginner"],
  "mcq_options": {
    "meaning":     ["<wrong>", "<wrong>", "<wrong>"],
    "plural":      ["<wrong>", "<wrong>", "<wrong>"],
    "root_derive": ["<wrong>", "<wrong>", "<wrong>"],
    "fill_blank":  ["<wrong>", "<wrong>", "<wrong>"],
    "grammar":     ["<wrong>", "<wrong>", "<wrong>"]
  }
}
```

Only include `mcq_options` keys whose test type applies (e.g. no `plural`
for verbs). Each present key must have exactly 3 entries.

### Passage

```jsonc
{
  "raw_passage_id": "<set only when enriching a raw_passages doc>",
  "title": "<short, fully diacritized>",
  "difficulty": "short|long",
  "lines": [
    {
      "arabic": "<sentence with full tashkeel>",
      "english": "<sentence translation>",
      "words": [
        {"arabic": "<token with tashkeel>", "translation": "<gloss>"}
      ]
    }
  ],
  "comprehension_questions": ["<question 1>", "<question 2>"]
}
```

Every Arabic token in `lines[].arabic` must also appear in `lines[].words`
(particles included).

### HTTP auth header

When submitting via the Render API:

```
X-Cowork-Token: <COWORK_SECRET>
Content-Type: application/json
```

A 401 means the token is missing or wrong; a 503 means
`COWORK_SECRET` is unset on the server (cowork endpoints are disabled).

---

## Token-cost reminder

Generation runs in this Desktop conversation, on subscription-funded
tokens. Neither the MCP tools nor the Render endpoints make any LLM call
of their own. If you ever find yourself wanting to call the Anthropic API
or an `anthropic` SDK from inside the bot codebase to enrich content,
**stop** — that would silently start drawing on paid API quota, defeating
the reason this routine lives in cowork.
