import { useEffect, useMemo, useState } from "react";
import {
  CircleAlert,
  Focus,
  GitBranch,
  ListTree,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
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

const TYPE_LABELS = {
  all: "Tất cả hạng mục",
  VehicleSystem: "Hệ thống xe",
  Subsystem: "Phân hệ",
  Component: "Bộ phận",
  Fault: "Lỗi",
  Symptom: "Triệu chứng",
  Repair: "Sửa chữa",
};

const STATUS_LABELS = {
  all: "Tất cả trạng thái",
  approved: "Đã xác minh",
  pending_review: "Chờ xác minh",
  rejected: "Từ chối",
  unknown: "Chưa rõ",
};

const RELATIONSHIP_LABELS = {
  HAS_SYMPTOM: "Dấu hiệu",
  AFFECTS: "Ảnh hưởng đến",
  FIXED_BY: "Giải pháp sửa chữa",
  PART_OF: "Thuộc hệ thống",
  RELATED_TO: "Liên quan đến",
};

const STAT_DISPLAY_LABELS = {
  VehicleSystem: "Hệ thống xe",
  Subsystem: "Phân hệ",
  Component: "Bộ phận",
  Fault: "Lỗi",
  Symptom: "Triệu chứng",
  Repair: "Sửa chữa",
  relationships: "Quan hệ",
};

const SYSTEM_LABELS = {
  SYS_ENGINE: "Động cơ",
  SYS_BRAKE: "Hệ thống phanh",
  SYS_ELECTRICAL: "Hệ thống điện",
  SYS_TRANSMISSION: "Hộp số",
  SYS_COOLING: "Hệ thống làm mát",
  SYS_FUEL: "Hệ thống nhiên liệu",
  SYS_SUSPENSION_STEERING: "Treo và lái",
  SYS_HVAC: "Điều hòa",
  SYS_EXHAUST_EMISSION: "Khí xả và phát thải",
};

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
  const [faultBrowserCollapsed, setFaultBrowserCollapsed] = useState(false);
  const [detailCollapsed, setDetailCollapsed] = useState(false);

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
        `Sơ đồ đầy đủ có ${relationshipCount} quan hệ và có thể tải chậm. Bạn vẫn muốn mở?`
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

  function selectById(nodeId) {
    if (!nodeId) return;
    const target = graph.nodes.find((n) => n.id === nodeId);
    if (target) {
      setSelectedNode(target);
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
            <h1>Sơ đồ tri thức</h1>
            <span className={`mode-pill ${mode}`}>
              {mode === "focused"
                ? "Sơ đồ chi tiết"
                : mode === "full"
                  ? "Sơ đồ đầy đủ"
                  : "Duyệt theo lỗi"}
            </span>
          </div>
        </div>

        <div className="graph-actions">
          <div className="graph-search">
            <Search size={18} />
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Tìm lỗi, triệu chứng, bộ phận, sửa chữa"
            />
            {searchQuery && (
              <button
                className="icon-button ghost"
                type="button"
                onClick={() => setSearchQuery("")}
                aria-label="Xóa tìm kiếm"
              >
                <X size={16} />
              </button>
            )}
            {hasSearch && (
              <div className="search-popover">
                <div className="search-popover-head">
                  <span>Kết quả phù hợp</span>
                  {searchLoading && <Loader2 size={15} className="spin" />}
                </div>
                {!searchLoading && searchResults.length === 0 && (
                  <p className="muted">Không có kết quả phù hợp</p>
                )}
                {searchResults.map((result) => (
                  <button
                    key={`${result.type}-${result.id}`}
                    className="search-result"
                    type="button"
                    onClick={() => handleSearchResultClick(result)}
                  >
                    <span>{displayLabel(result)}</span>
                    <small>{TYPE_LABELS[result.type] || result.type}</small>
                  </button>
                ))}
              </div>
            )}
          </div>

          <button type="button" onClick={handleLoadFullGraph} disabled={loading}>
            <RefreshCw size={18} className={loading && mode === "full" ? "spin" : ""} />
            Sơ đồ đầy đủ
          </button>
        </div>
      </header>

      <section className="graph-stats" aria-label="Thống kê sơ đồ">
        {STAT_LABELS.map((label) => (
          <div className="stat-card" key={label}>
            <span>{STAT_DISPLAY_LABELS[label] || label}</span>
            <strong>{stats[label] ?? 0}</strong>
          </div>
        ))}
      </section>

      <section className={`graph-workspace ${faultBrowserCollapsed ? "fault-collapsed" : ""}`}>
        <FaultBrowser
          faults={faultList}
          loading={faultListLoading}
          selectedId={selectedNode?.id}
          onOpenFault={handleOpenFaultGraph}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          collapsed={faultBrowserCollapsed}
          onToggleCollapse={() => setFaultBrowserCollapsed((value) => !value)}
        />

        <div className={`graph-main ${detailCollapsed ? "detail-collapsed" : ""}`}>
          <div className="graph-filterbar">
            <select value={type} onChange={(event) => setType(event.target.value)}>
              {TYPE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {TYPE_LABELS[option] || option}
                </option>
              ))}
            </select>
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {STATUS_LABELS[option] || option}
                </option>
              ))}
            </select>
            {mode === "focused" && (
              <span className="focused-chip">
                <Focus size={15} />
                {selectedNode?.type === "Fault" ? displayLabel(selectedNode) : "Đang xem chi tiết"}
              </span>
            )}
            <button
              type="button"
              className="secondary-toggle"
              onClick={() => setDetailCollapsed((v) => !v)}
              aria-pressed={detailCollapsed}
            >
              {detailCollapsed ? "Mở chi tiết" : "Thu chi tiết"}
            </button>
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
              Đang tải dữ liệu sơ đồ...
            </div>
          )}
          {emptyGraph && (
            <div className="empty-state graph-message">
              <h2>Chưa tìm thấy dữ liệu sơ đồ</h2>
              <p>
                Hãy nhập dữ liệu vào Neo4j hoặc giữ các tệp JSON staging trong
                <code> data/staging </code>.
              </p>
            </div>
          )}

          {hasGraph ? (
            <GraphCanvas
              graph={filteredGraph}
              selectedNodeId={selectedNode?.id}
              onNodeClick={handleNodeClick}
            />
          ) : (
            <div className="graph-start-panel">
              <ListTree size={34} />
              <h2>Chọn một lỗi để xem sơ đồ chi tiết</h2>
              <p>
                Danh sách bên trái giúp mở nhanh lỗi, triệu chứng, bộ phận bị
                ảnh hưởng, hướng sửa chữa và đường dẫn hệ thống liên quan.
              </p>
            </div>
          )}
        </div>

        {!detailCollapsed && (
          <aside className="node-inspector graph-detail-panel">
          {selectedNode ? (
            <NodeDetails
              node={selectedNode}
              graph={graph}
              onOpenFaultGraph={() => handleOpenFaultGraph(selectedNode.id, selectedNode)}
              loading={loading}
              onSelectNode={selectById}
            />
          ) : (
            <div className="detail-empty">
              <GitBranch size={28} />
              <p>Chọn một lỗi hoặc hạng mục</p>
            </div>
          )}
          </aside>
        )}
      </section>
    </div>
  );
}

function FaultBrowser({
  faults,
  loading,
  selectedId,
  onOpenFault,
  searchQuery,
  onSearchChange,
  collapsed,
  onToggleCollapse,
}) {
  if (collapsed) {
    return (
      <aside className="fault-browser collapsed">
        <button
          className="collapse-button"
          type="button"
          onClick={onToggleCollapse}
          aria-label="Mở danh sách lỗi"
        >
          <PanelLeftOpen size={18} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="fault-browser">
      <div className="fault-browser-head">
        <div>
          <h2>Danh sách lỗi</h2>
          <p>Mở từng sơ đồ nhỏ để đọc rõ hơn</p>
        </div>
        <button
          className="collapse-button"
          type="button"
          onClick={onToggleCollapse}
          aria-label="Thu gọn danh sách lỗi"
        >
          <PanelLeftClose size={18} />
        </button>
        {loading && <Loader2 size={17} className="spin" />}
      </div>
      <label className="fault-search">
        <Search size={17} />
        <input
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Tìm trong danh sách lỗi"
        />
      </label>
      <div className="fault-list">
        {!loading && faults.length === 0 && (
          <p className="muted">Không có lỗi phù hợp với từ khóa hiện tại.</p>
        )}
        {faults.map((fault) => (
          <button
            key={fault.id}
            type="button"
            className={`fault-list-item ${selectedId === fault.id ? "active" : ""}`}
            onClick={() => onOpenFault(fault.id, fault)}
          >
            <span className="fault-card-title">{displayLabel(fault)}</span>
            <span className="fault-card-meta">
              <span>{displaySystem(fault.summary?.system)}</span>
              <span>{fault.summary?.symptom_count ?? 0} dấu hiệu</span>
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}

function NodeDetails({ node, graph, onOpenFaultGraph, loading, onSelectNode }) {
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
          {TYPE_LABELS[node.type] || node.type}
        </span>
        {node.status && (
          <span className={`graph-status ${node.status}`}>
            {STATUS_LABELS[node.status] || node.status}
          </span>
        )}
      </div>
      <h2>{displayLabel(node)}</h2>
      <section className="expert-panel info-panel">
        <h3>Thông tin lỗi</h3>
        <dl className="detail-list">
          <dt>Mã</dt>
          <dd>{node.id}</dd>
          <dt>Tên</dt>
          <dd>{displayLabel(node)}</dd>
          <dt>Loại</dt>
          <dd>{TYPE_LABELS[node.type] || node.type}</dd>
          <dt>Trạng thái</dt>
          <dd>{STATUS_LABELS[node.status] || "Chưa rõ"}</dd>
        </dl>
      </section>
      {node.type === "Fault" && (
        <button className="detail-cta" type="button" onClick={onOpenFaultGraph} disabled={loading}>
          <Focus size={17} />
          Mở sơ đồ chi tiết
        </button>
      )}
      {node.type === "Fault" && (
        <FaultRulePanel
          node={node}
          edges={connectedEdges}
          nodesById={nodesById}
          onSelectNode={onSelectNode}
        />
      )}
      <RelationshipPanel edges={connectedEdges} nodesById={nodesById} />
      {node.type === "Fault" && (
        <RepairPanel edges={connectedEdges} nodesById={nodesById} />
      )}
    </>
  );
}

function FaultRulePanel({ node, edges, nodesById, onSelectNode }) {
  const symptomEdges = edges.filter(
    (edge) => edge.type === "HAS_SYMPTOM" && edge.source === node.id
  );
  const componentEdges = edges.filter(
    (edge) => edge.type === "AFFECTS" && edge.source === node.id
  );

  return (
    <section className="expert-panel">
      <h3>Luật chẩn đoán</h3>
      <div className="rule-line">
        <strong>NẾU</strong>
        <div>
          {symptomEdges.length === 0 ? (
            <span className="muted">Chưa có dấu hiệu trong sơ đồ hiện tại</span>
          ) : (
            symptomEdges.map((edge) => (
              <button
                type="button"
                className="rule-chip clickable"
                key={edge.id}
                onClick={() => onSelectNode?.(edge.target)}
                title="Chọn dấu hiệu trong sơ đồ"
              >
                {nodeLabel(nodesById, edge.target)}
                {edge.metadata?.priority && <small>P{edge.metadata.priority}</small>}
              </button>
            ))
          )}
        </div>
      </div>
      <div className="rule-line">
        <strong>THÌ</strong>
        <div>
          <span className="rule-chip fault-rule">{displayLabel(node)}</span>
        </div>
      </div>
      {componentEdges.length > 0 && (
        <div className="rule-line">
          <strong>LIÊN KẾT</strong>
          <div>
            {componentEdges.map((edge) => (
              <button
                type="button"
                className="rule-chip clickable"
                key={edge.id}
                onClick={() => onSelectNode?.(edge.target)}
                title="Chọn bộ phận trong sơ đồ"
              >
                Ảnh hưởng đến {nodeLabel(nodesById, edge.target)}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function RelationshipPanel({ edges, nodesById }) {
  const visibleEdges = edges.filter((edge) =>
    ["HAS_SYMPTOM", "AFFECTS", "PART_OF", "RELATED_TO"].includes(edge.type)
  );

  return (
    <section className="expert-panel">
      <h3>Quan hệ liên kết</h3>
      {visibleEdges.length === 0 ? (
        <p className="muted">Không có quan hệ trực tiếp trong sơ đồ hiện tại</p>
      ) : (
        <ul className="relationship-list">
          {visibleEdges.map((edge) => (
            <li key={edge.id}>
              <span className={`relationship-type ${edge.type?.toLowerCase()}`}>
                {edge.label || RELATIONSHIP_LABELS[edge.type] || "Liên quan"}
              </span>
              <span>
                {nodeLabel(nodesById, edge.source)}
                {" -> "}
                {nodeLabel(nodesById, edge.target)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RepairPanel({ edges, nodesById }) {
  const repairEdges = edges.filter((edge) => edge.type === "FIXED_BY");

  return (
    <section className="expert-panel repair-panel">
      <h3>Giải pháp sửa chữa</h3>
      {repairEdges.length === 0 ? (
        <p className="muted">Chưa có giải pháp sửa chữa trong sơ đồ hiện tại</p>
      ) : (
        <ul className="repair-list">
          {repairEdges.map((edge) => (
            <li key={edge.id}>{nodeLabel(nodesById, edge.target)}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function nodeLabel(nodesById, nodeId) {
  const node = nodesById.get(nodeId);
  return displayLabel(node || { id: nodeId, label: nodeId });
}

function displayLabel(node) {
  if (!node) {
    return "";
  }
  const value = SYSTEM_LABELS[node.label] || SYSTEM_LABELS[node.id] || node.label || node.id;
  return normalizeAutomotiveTerm(value);
}

function displaySystem(system) {
  return normalizeAutomotiveTerm(SYSTEM_LABELS[system] || system || "Hệ thống chưa rõ");
}

function normalizeAutomotiveTerm(value) {
  if (!value) {
    return value;
  }

  return String(value).replaceAll("Bạc đạn", "Ổ bi");
}
