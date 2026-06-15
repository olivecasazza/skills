_: { pkgs, riglib, ... }: {
  config.riglets.socraticode = {
    meta = {
      description = "SocratiCode — codebase intelligence, semantic search, and impact analysis";
      intent = "investigator";
      whenToUse = [
        "When navigating unfamiliar codebases"
        "To find entry points for features conceptually"
        "To analyze the blast radius of a symbol change"
      ];
      keywords = [ "codebase" "intelligence" "semantic" "search" "impact" ];
      status = "stable";
      version = "1.8.16";
    };

    # The SocratiCode binary is run via npx/node.
    tools = [
      pkgs.nodejs
      pkgs.docker
    ];

    # MCP registration handled in salt's AI catalog, but we document the tool
    # usage here for the agent.
    docs = riglib.writeFileTree {
      "SKILL.md" = ''
        # SocratiCode

        Codebase intelligence engine for semantic search and structural analysis.
        Uses a local vector database (Qdrant) and embedding engine (Ollama) to
        provide deep semantic understanding.

        ## Core Tools (via MCP)

        - `codebase_search`: Semantic + BM25 keyword search for high-level concepts.
        - `codebase_index`: (Re)index the codebase in the background.
        - `codebase_impact`: Analyze the blast radius of changing a specific symbol.
        - `codebase_graph_query`: Visualize file-level dependencies.
        - `codebase_flow`: Trace execution flow from an entry point.

        ## Local Automation

        - `just index`: Trigger indexing.
        - `just search "<query>"`: Search the codebase.

        ## Configuration

        - `.socraticode.json`: Project ID and linked projects.
        - `.socraticodeignore`: Exclusion patterns (skip secrets, node_modules).
      '';
    };
  };
}
