---
name: socraticode
description: SocratiCode — codebase intelligence, semantic search, and impact analysis. Uses a local vector database (Qdrant) and embedding engine (Ollama) to provide deep semantic understanding of the codebase.
license: AGPL-3.0-only
metadata:
  author: giancarloerra
  version: "1.8.16"
---

# SocratiCode

Codebase intelligence engine for semantic search and structural analysis.

## MCP Tools

The following tools are available via the SocratiCode MCP server:

- `codebase_search`: Semantic search + BM25 keyword search.
- `codebase_index`: (Re)index the codebase in the background.
- `codebase_impact`: Analyze the blast radius of changing a specific symbol.
- `codebase_graph_query`: Visualize file-level dependencies.
- `codebase_flow`: Trace execution flow from an entry point.

## Configuration

- `.socraticode.json`: Root project configuration (projectId, linkedProjects).
- `.socraticodeignore`: Files/folders to exclude from the index.

## Usage Stance

Use SocratiCode when:
- Navigating large, unfamiliar codebases.
- Finding entry points for features (e.g., "where is auth?").
- Analyzing the impact of refactors or symbol changes.
- Mapping dependencies between modules.

Prefer `codebase_search` over recursive grep for high-level conceptual lookups.

