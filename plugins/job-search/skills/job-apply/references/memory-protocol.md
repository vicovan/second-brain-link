# Memory protocol — remember, use, improve

Shared by every skill in this plugin (and shipped identically in every plugin; keep the copies
identical). The tool is `memory.py` in this plugin's library skill; memory lives in the user's
brain under `_memory/` as plain notes they can read, edit and delete. Design:
`second-brain-link-docs/docs-memory/SBL-MEMORY-ARCHITECTURE.md`.

Run `memory.py` from inside the brain (Studio's working folder), or pass `--brain "<brain root>"`.
`<scope>` is this plugin's id; `<tags>` are the tags listed in your skill's memory block.

## 1. Recall first — every run, before anything else
```
memory.py recall --scope <scope> --tags <tags>
```
Apply every item it returns. Then tell the user in ONE line which remembered items changed what
you are doing, with their ids — e.g. *"From memory: skipping roles that need relocation
(m-20300101-7f3a1c), cover letters under 200 words (m-20300102-02be44)."* If nothing applied, say nothing about memory.
**Never ask the user something memory already answers.** Memory wins over this skill's defaults;
the user's words in THIS conversation win over memory (and are then saved — step 2).

## 2. Capture what the user tells you — at once
A stated preference, a rule ("never…", "always…", "exclude…", "keep…"), a fact about themselves, or
a correction of something you did → save it immediately, then act on it:
```
memory.py list --scope <scope> --json          # is there already an item that means the same?
memory.py observe --scope <scope> --kind preference|rule|fact|correction --source user \
  --text "<one self-contained sentence>" --tags <tags> --evidence "chat|<their words>" \
  [--match <id> | --new] [--supersedes <id of the item it replaces>]
```
- Write the text so it stands alone next month: *who/what, the rule, and why if they gave one.*
- Something true for EVERY agent (location, relocation, languages, non-competes) → `--scope shared`.
- It is active at once. Tell them in a few words: *"Remembered."*

## 3. Capture outcomes — whenever one lands
A reply, a rejection (with its stated reason), an interview, an investor's answer, a rating, a gate
or a form that failed, a reviewer's verdict → one `--source outcome` observation with the evidence
(numbers where you have them: *"0 of 4 director roles at 1,000+ person companies replied"*). Check
`list --json` first and `--match` the item it strengthens — reinforcing is how the agent learns.

## 4. Reflect — at the end of every run
Name at most **three** things this run taught that are not already in memory and would change a
future run. For each: `list --json`, then either `--match` an existing item or `--new`, always
`--source agent`. By default (the user's choice) an inference is **saved and used at once**, flagged
as inferred so the user can see, edit or remove it in Studio's Memory manager; only a brain set to
review-first (`memory.py policy review`) holds it until approved. Because it acts at once, keep it
to what the run actually showed — never a guess. Close with one line: *"Learned: …"* (omit when
nothing).

## 5. When the user steers memory
*"Forget that"* / *"that's wrong"* → `memory.py forget <id>` (or `retire <id> --reason "…"`).
*"Reword it: …"* → `memory.py approve <id> --edit "…"`. In review-first brains, *"approve m-… /
reject m-… because …"* → `memory.py approve <id>` / `memory.py reject <id> --reason "…"`. When they ask what
you remember → `memory.py list --scope <scope>` (and `shared`, `brain`).

## Never
- Store secrets (passwords, card, account or ID numbers) — `memory.py` refuses them anyway.
- Save an inference as `--source user` or `outcome` — it must stay flagged as inferred.
- Write facts about OTHER people or companies as anything but `--source agent`.
- Write memory anywhere else (not `_notes/`, not the plugin's lessons file by hand, not CLAUDE.md).
