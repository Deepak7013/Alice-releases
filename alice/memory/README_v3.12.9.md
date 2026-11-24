# ALICE v3.12.9 Memory Library

The v3.12.9 memory layer has two complementary stores:

1. `alice_workspace/conversations/history.jsonl` — durable chat history.
2. `alice_workspace/library/alice_knowledge.sqlite3` — durable learned knowledge.

Every user chat turn is retained in the conversation history. The learning layer extracts durable user-provided facts, preferences and explicit remember/instruction statements into the SQLite library. Matching knowledge is retrieved locally and supplied to ALICE's reasoning prompt. Memory-list questions are answered locally without a provider call.

Credentials and permission-escalation instructions are never promoted into durable knowledge. Existing protected workspace data is preserved by the upgrade system.
