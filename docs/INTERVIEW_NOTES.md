# Interview cheat-sheet (concepts named in the brief)

- **Generative AI**: models that produce new content (text, code) from a prompt. Here: OpenAI turns a question into a JSON plan.
- **Agentic AI**: an LLM that plans, calls tools, observes results and loops toward a goal. This project is a *single-step
  tool-use pipeline*, not a full agent. To make it agentic: let the LLM choose among tools (`run_query`, `compare_months`,
  `check_data_quality`), inspect results, and retry or ask clarifying questions.
- **RAG** (Retrieval-Augmented Generation): retrieve relevant documents (usually via embeddings + a vector DB) and give them to the LLM
  as context so answers are grounded. Here the "retrieval" is a deterministic SQL query and the catalog of valid values.
- **Vectorless RAG**: retrieval without embeddings/vector DBs: SQL, keyword/BM25 search, or LLM navigation of document structure
  (e.g. table-of-contents trees). This project is effectively vectorless: structured data is retrieved by SQL.
- **LangChain**: framework for chains, tools, retrievers, agents (LangGraph for stateful agents). **Google ADK**: Google's
  agent development kit (agents, tools, multi-agent orchestration). **Dify**: low-code platform for building LLM apps/workflows.
- **Why not pure text-to-SQL?** Risk of wrong joins/hallucinated columns and injection; intent routing is safer and testable.
  If asked to extend: validate SQL (single SELECT, whitelist tables/columns, LIMIT), run read-only, show SQL to the user.
