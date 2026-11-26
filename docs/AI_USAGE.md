# How AI was used (DRAFT: edit to reflect your own experience before submitting)

## AI tools used
- Claude (Anthropic) for analysing the brief, designing the architecture, generating code and tests.
- OpenAI (`gpt-4o-mini`) inside the app for question interpretation.

## How AI was used during development
1. Gave the brief and CSV to Claude; it profiled the data and found three bad records before any code was written.
2. Chose the design together: intent routing + parameterised SQL rather than free-form text-to-SQL, for safety and testability.
3. Claude generated the modules (`db`, `analytics`, `nlu`, `service`, `main`, UI) and 22 tests; expected figures were computed independently with pandas.

## Problems encountered and how they were debugged
- **Dirty data** (returned order, zero quantity, missing price): quarantined into `rejected_records` with reasons.
- **Ambiguous revenue definition / discount semantics**: decided and documented the assumption.
- **Month comparison direction**: "Compare June vs May" returned a reversed change. Found by manually trying varied phrasings
  after tests passed; fixed by always ordering months chronologically and added a regression test.
- **Placeholder order bug risk** in the month-comparison query (`IN (?,?)` args must come before filter args): covered by tests.
- **Sandbox had no network**, so FastAPI and the real OpenAI call could not be exercised there; core logic was tested directly
  and the LLM replaced by an injected fake. Run `pytest` and one real question locally to confirm.

## What I would improve with another day
- Optional validated text-to-SQL mode (single `SELECT`, table whitelist, row limit) with an LLM self-check.
- LLM-written natural-language summaries constrained to the returned numbers; charts in the UI.
- Conversation memory for follow-ups ("and for South?"), richer filters (date ranges, units), evaluation set of 50 questions.
- Logging, rate limiting, auth, Docker.
