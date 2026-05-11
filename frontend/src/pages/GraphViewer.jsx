import { useEffect, useMemo, useState } from "react";
import {
  CircleAlert,
  Focus,
  GitBranch,
  ListTree,
  Loader2,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  getFaultGraph,
  getFaultList,
  getGraph,
  getGraphStats,
  searchGraph,
} from "../api/client.js";
import GraphCanvas from "../components/GraphCanvas.jsx";

const TYPE_OPTIONS = [
  "all",
  "Fault",
  "Symptom",
  "Component",
  "Subsystem",
  "VehicleSystem",
  "Repair",
];

const STATUS_OPTIONS = ["all", "approved", "pending_review", "rejected", "unknown"];

const STAT_LABELS = [
  "VehicleSystem",
  "Subsystem",
  "Component",
  "Fault",
  "Symptom",
  "Repair",
  "relationships",
];

export default function GraphViewer() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [faultList, setFaultList] = useState([]);
  const [stats, setStats] = useState({});
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [mode, setMode] = useState("browse");
  const [loading, setLoading] = useState(false);
  const [faultListLoading, setFaultListLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadStats() {
    try {
      setStats(await getGraphStats());
    } catch {
      setStats({});
    }
  }

  async function loadFaults(query = "") {
    setFaultListLoading(true);
    try {
      setFaultList(await getFaultList(query, 250));
    } catch {
      setFaultList([]);
    } finally {
      setFaultListLoading(false);
    }
  }

  async function handleLoadFullGraph() {
    const relationshipCount = Number(stats.relationships || 0);
    if (
      relationshipCount > 1000 &&
      !window.confirm(
        `Full graph has ${relationshipCount} relationships and may be slow. Load it anyway?`
      )
    ) {
      return;
    }

    setError("");
    setLoading(true);
    setMode("full");
    setSelectedNode(null);

    try {
      setGraph(await getGraph());
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenFaultGraph(faultId, selected = null) {
    if (!faultId) {
      return;
    }

    setError("");
    setLoading(true);
    setMode("focused");
    setType("all");
    setStatus("all");

    try {
      const data = await getFaultGraph(faultId);
      setGraph(data);
      setSelectedNode(
        data.nodes.find((node) => node.id === faultId) || selected || null
      );
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleNodeClick(node) {
    setSelectedNode(node);
    if (node?.type === "Fault" && mode === "full") {
      handleOpenFaultGraph(node.id, node);
    }
  }

  function handleSearchResultClick(result) {
    setSelectedNode(result);
    if (result.type === "Fault") {
      handleOpenFaultGraph(result.id, result);
    }
  }

  useEffect(() => {
    loadStats();
    loadFaults();
  }, []);

  useEffect(() => {
    const trimmed = searchQuery.trim();
    let cancelled = false;

    const timeout = window.setTimeout(async () => {
      if (!cancelled) {
        loadFaults(trimmed);
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [searchQuery]);

  useEffect(() => {
    const trimmed = searchQuery.trim();
    if (!trimmed) {
      setSearchResults([]);
      setSearchLoading(false);
      return undefined;
    }

    let cancelled = false;
    setSearchLoading(true);

    const timeout = window.setTimeout(async () => {
      try {
        const results = await searchGraph(trimmed);
        if (!cancelled) {
          setSearchResults(results);
        }
      } catch {
        if (!cancelled) {
          setSearchResults([]);
        }
      } finally {
        if (!cancelled) {
          setSearchLoading(false);
        }
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [searchQuery]);

  const filteredGraph = useMemo(() => {
    const nodes = graph.nodes.filter((node) => {
      const typeOk = type === "all" || node.type === type;
      const statusOk = status === "all" || node.status === status;
      return typeOk && statusOk;
    });
    const ids = new Set(nodes.map((node) => node.id));

    return {
      nodes,
      edges: graph.edges.filter(
        (edge) => ids.has(edge.source) && ids.has(edge.target)
      ),
    };
  }, [graph, type, status]);

  const hasSearch = searchQuery.trim().length > 0;
  const hasGraph = filteredGraph.nodes.length > 0;
  const emptyGraph = mode !== "browse" && !loading && !error && !hasGraph;

  return (
    <div className="page graph-page">
      <header className="graph-topbar">
        <div className="graph-title">
          <GitBranch size={22} />
          <div>
            <h1>Knowledge Graph</h1>
            <span className={`mode-pill ${mode}`}>
              {mode === "focused" ? "Focused graph" : mode === "full" ? "Full graph" : "Browse by fault"}
            </span>
          </div>
        </div>

        <div className="graph-actions">
          <div className="graph-search">
            <Search size={18} />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search faults, symptoms, components, repairs"
            />
            {searchQuery && (
              <button
                className="icon-button ghost"
                type="button"
                onClick={() => setSearchQuery("")}
                aria-label="Clear search"
              >
                <X size={16} />
              </button>
            )}
            {hasSearch && (
              <div className="search-popover">
                <div className="search-popover-head">
                  <span>Matches</span>
                  {searchLoading && <Loader2 size={15} className="spin" />}
                </div>
                {!searchLoading && searchResults.length === 0 && (
                  <p className="muted">No matches</p>
                )}
                {searchResults.map((result) => (
                  <button
                    key={`${result.type}-${result.id}`}
                    className="search-result"
                    type="button"
                    onClick={() => handleSearchResultClick(result)}
                  >
                    <span>{result.label}</span>
                    <small>{result.type}</small>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button type="button" onClick={handleLoadFullGraph} disabled={loading}>
            <RefreshCw size={18} className={loading && mode === "full" ? "spin" : ""} />
            Full graph
          </button>
        </div>
      </header>

      <section className="graph-stats" aria-label="Graph statistics">
        {STAT_LABELS.map((label) => (
          <div className="stat-card" key={label}>
            <span>{label}</span>
            <strong>{stats[label] ?? 0}</strong>
          </div>
        ))}
      </section>

      <section className="graph-workspace">
        <FaultBrowser
          faults={faultList}
          loading={faultListLoading}
          selectedId={selectedNode?.id}
          onOpenFault={handleOpenFaultGraph}
        />

        <div className="graph-main">
          <div className="graph-filterbar">
            <select value={type} onChange={(event) => setType(event.target.value)}>
              {TYPE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "All types" : option}
                </option>
              ))}
            </select>
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "All statuses" : option}
                </option>
              ))}
            </select>
            {mode === "focused" && (
              <span className="focused-chip">
                <Focus size={15} />
                {selectedNode?.type === "Fault" ? selectedNode.label : "Focused"}
              </span>
            )}
          </div>

          {error && (
            <p className="error graph-message">
              <CircleAlert size={18} />
              {error}
            </p>
          )}
          {loading && (
            <div className="notice graph-message">
              <Loader2 size={18} className="spin" />
              Loading graph data...
            </div>
          )}
          {emptyGraph && (
            <div className="empty-state graph-message">
              <h2>No graph data found</h2>
              <p>
                Import data into Neo4j, or keep the staging JSON files in
                <code> data/staging </code>.
              </p>
            </div>
          )}

          {hasGraph ? (
            <GraphCanvas graph={filteredGraph} onNodeClick={handleNodeClick} />
          ) : (
            <div className="graph-start-panel">
              <ListTree size={34} />
              <h2>Select a fault to view a focused graph</h2>
              <p>
                The page now loads a compact list first, then renders only the
                selected fault, its symptoms, affected components, repairs, and
                parent system path.
              </p>
            </div>
          )}
        </div>

        <aside className="node-inspector graph-detail-panel">
          {selectedNode ? (
            <NodeDetails
              node={selectedNode}
              graph={graph}
              onOpenFaultGraph={() => handleOpenFaultGraph(selectedNode.id, selectedNode)}
              loading={loading}
            />
          ) : (
            <div className="detail-empty">
              <GitBranch size={28} />
              <p>Select a fault or node</p>
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}

function FaultBrowser({ faults, loading, selectedId, onOpenFault }) {
  return (
    <aside className="fault-browser">
      <div className="fault-browser-head">
        <div>
          <h2>Fault list</h2>
          <p>Open one small graph at a time</p>
        </div>
        {loading && <Loader2 size={17} className="spin" />}
      </div>
      <div className="fault-list">
        {!loading && faults.length === 0 && (
          <p className="muted">No faults match the current search.</p>
        )}
        {faults.map((fault) => (
          <button
            key={fault.id}
            type="button"
            className={`fault-list-item ${selectedId === fault.id ? "active" : ""}`}
            onClick={() => onOpenFault(fault.id, fault)}
          >
            <span>{fault.label}</span>
            <small>
              {fault.summary?.system || "Unknown system"}
              {" · "}
              {fault.summary?.symptom_count ?? 0} symptoms
            </small>
          </button>
        ))}
      </div>
    </aside>
  );
}

function NodeDetails({ node, graph, onOpenFaultGraph, loading }) {
  const metadataEntries = Object.entries(node.metadata || {});
  const nodesById = useMemo(
    () => new Map((graph?.nodes || []).map((item) => [item.id, item])),
    [graph?.nodes]
  );
  const connectedEdges = useMemo(
    () =>
      (graph?.edges || []).filter(
        (edge) => edge.source === node.id || edge.target === node.id
      ),
    [graph?.edges, node.id]
  );

  return (
    <>
      <div className="detail-head">
        <span className={`graph-type-badge ${node.type?.toLowerCase()}`}>
          {node.type}
        </span>
        {node.status && <span className={`graph-status ${node.status}`}>{node.status}</span>}
      </div>
      <h2>{node.label}</h2>
      <dl className="detail-list">
        <dt>ID</dt>
        <dd>{node.id}</dd>
        <dt>Label</dt>
        <dd>{node.label}</dd>
        <dt>Type</dt>
        <dd>{node.type}</dd>
        <dt>Status</dt>
        <dd>{node.status || "unknown"}</dd>
      </dl>
      {node.type === "Fault" && (
        <button type="button" onClick={onOpenFaultGraph} disabled={loading}>
          <Focus size={17} />
          Open focused graph
        </button>
      )}
      {node.type === "Fault" && (
        <FaultRulePanel node={node} edges={connectedEdges} nodesById={nodesById} />
      )}
      <RelationshipPanel edges={connectedEdges} nodesById={nodesById} />
      <div className="metadata-panel">
        <h3>Metadata</h3>
        {metadataEntries.length === 0 ? (
          <p className="muted">No metadata</p>
        ) : (
          <pre>{JSON.stringify(node.metadata, null, 2)}</pre>
        )}
      </div>
    </>
  );
}

function FaultRulePanel({ node, edges, nodesById }) {
  const symptomEdges = edges.filter(
    (edge) => edge.type === "HAS_SYMPTOM" && edge.source === node.id
  );
  const componentEdges = edges.filter(
    (edge) => edge.type === "AFFECTS" && edge.source === node.id
  );
  const repairEdges = edges.filter(
    (edge) => edge.type === "FIXED_BY" && edge.source === node.id
  );

  return (
    <section className="expert-panel">
      <h3>Luật hệ chuyên gia</h3>
      <div className="rule-line">
        <strong>IF</strong>
        <div>
          {symptomEdges.length === 0 ? (
            <span className="muted">No symptom rule in current graph</span>
          ) : (
            symptomEdges.map((edge) => (
              <span className="rule-chip" key={edge.id}>
                {nodeLabel(nodesById, edge.target)}
                {edge.cf != null && <small>CF {Number(edge.cf).toFixed(2)}</small>}
                {edge.metadata?.priority && <small>P{edge.metadata.priority}</small>}
              </span>
            ))
          )}
        </div>
      </div>
      <div className="rule-line">
        <strong>THEN</strong>
        <div>
          <span className="rule-chip fault-rule">{node.label}</span>
        </div>
      </div>
      {(componentEdges.length > 0 || repairEdges.length > 0) && (
        <div className="rule-line">
          <strong>LINK</strong>
          <div>
            {componentEdges.map((edge) => (
              <span className="rule-chip" key={edge.id}>
                AFFECTS {nodeLabel(nodesById, edge.target)}
              </span>
            ))}
            {repairEdges.map((edge) => (
              <span className="rule-chip" key={edge.id}>
                FIXED_BY {nodeLabel(nodesById, edge.target)}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function RelationshipPanel({ edges, nodesById }) {
  return (
    <section className="expert-panel">
      <h3>Quan hệ trực tiếp</h3>
      {edges.length === 0 ? (
        <p className="muted">No direct relationships in current graph</p>
      ) : (
        <ul className="relationship-list">
          {edges.map((edge) => (
            <li key={edge.id}>
              <span className={`relationship-type ${edge.type?.toLowerCase()}`}>
                {edge.type}
              </span>
              <span>
                {nodeLabel(nodesById, edge.source)}
                {" -> "}
                {nodeLabel(nodesById, edge.target)}
              </span>
              {edge.cf != null && <small>CF {Number(edge.cf).toFixed(2)}</small>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function nodeLabel(nodesById, nodeId) {
  return nodesById.get(nodeId)?.label || nodeId;
}
