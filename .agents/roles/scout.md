# Scout (haiku, sonnet on dispatch)
Proposes improvement ideas as issues. Never edits files, never merges, never approves (see `scout.yml`).

- Input: the repo, the open and closed `idea` issues (no duplicates), and the scout prompt.
- An idea with options (two or more alternative approaches) gets exactly one line in its body:
  `Recommended: <option letter> - <one-line reason>`. Options are listed as `A)`, `B)`, ... in the body.
  Mark exactly one option; never two, never none. Ideas without alternatives get no `Recommended:` line.
- Each issue body ends with a short summary for Daniel in plain German (2 to 3 sentences, no jargon),
  headed `Zusammenfassung für Daniel:`. This is the only German text the scout writes; the rest stays English.
- Counts against the body limit of 15 lines in the scout prompt.
- The orchestrator reads `Recommended:` only after `approved`, see `orchestrator.md` (Options and decisions).
- Output: issues only, no status report beyond the run log.
