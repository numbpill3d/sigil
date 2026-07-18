# Why not RAG?

Most "agent memory" is retrieval-augmented generation: chunk text, embed it,
store vectors, cosine-similarity the query, stuff the top chunks in the
prompt. It works, but it has structural problems SIGIL avoids by making
memory a graph instead of a vector index.

## 1. You can't see or edit what the agent remembers

RAG recall is opaque: a chunk surfaces because of a cosine score you can't
inspect or argue with. In SIGIL, context is a link-walk — you can run
`sigil walk --explain` and see exactly which notes were included and why
(score, hop, source). Edit a `[[link]]` in Obsidian and the agent's context
changes. The memory substrate is a thing you own.

## 2. Forgetting is a feature, not a bug

Vector stores keep everything at equal weight until you manually prune.
SIGIL decays notes by `half_life` and lets you tombstone (`status: dead`)
anything you want gone. Memories age; that's realistic.

## 3. Provenance and conflict are first-class

In RAG, two contradicting sources just both get retrieved and the model
winges. SIGIL stamps every belief with provenance and resolves conflicts by
tier (human > agent > ingested), logging disagreements. The vault is an
audit trail, not a bag of embeddings.

## 4. Autonomy needs a control surface

Semi-autonomous agents need a place to record intent, limits, and decisions.
A vector store can't be a kill-switch. The SIGIL vault is both memory and the
leash: `intent.md` gates every write, proposals require human approval, and a
markdown edit stops the agent.

## The cost

SIGIL trades universal semantic recall for transparent, editable,
auditable, bounded memory. If you need "find the paragraph semantically
similar to this query across 10M docs," use RAG. If you need an agent whose
mind you can read, edit, and trust, use a vault.
