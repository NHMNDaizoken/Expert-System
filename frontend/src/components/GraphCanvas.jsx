import { memo, useEffect, useMemo } from "react";
import dagre from "dagre";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlowProvider,
  useReactFlow,
} from "reactflow";

const minNodeWidth = 196;
const maxNodeWidth = 276;
const baseNodeHeight = 88;
const levelGap = 370;
const rowGap = 44;

const NODE_LEVEL = {
  Symptom: 0,
  Fault: 1,
  Component: 2,
  Subsystem: 3,
  VehicleSystem: 4,
  Repair: 2,
};

const EDGE_STYLES = {
  HAS_SYMPTOM: { stroke: "rgba(148, 163, 184, 0.58)", strokeWidth: 1.7 },
  AFFECTS: { stroke: "rgba(248, 113, 113, 0.56)", strokeWidth: 1.8 },
  PART_OF: { stroke: "rgba(100, 116, 139, 0.5)", strokeWidth: 1.5 },
  FIXED_BY: { stroke: "rgba(74, 222, 128, 0.56)", strokeWidth: 1.8 },
  RELATED_TO: {
    stroke: "rgba(123, 135, 158, 0.44)",
    strokeWidth: 1.5,
    strokeDasharray: "7 7",
  },
};

const TYPE_LABELS = {
  VehicleSystem: "Hệ thống xe",
  Subsystem: "Phân hệ",
  Component: "Bộ phận",
  Fault: "Lỗi",
  Symptom: "Triệu chứng",
  Repair: "Sửa chữa",
};

const STATUS_LABELS = {
  approved: "Đã xác minh",
  pending_review: "Chờ xác minh",
  rejected: "Từ chối",
  unknown: "Chưa rõ",
};

const EDGE_LABELS = {
  HAS_SYMPTOM: "Dấu hiệu",
  AFFECTS: "Ảnh hưởng đến",
  FIXED_BY: "Giải pháp sửa chữa",
  PART_OF: "Thuộc hệ thống",
  RELATED_TO: "Liên quan đến",
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

function ExpertNode({ data }) {
  return (
    <div className="graph-node-card">
      <Handle type="target" position={Position.Left} />
      <div className="graph-node-label">{displayLabel(data)}</div>
      <div className="graph-node-meta">
        <span className={`graph-type-badge ${data.type?.toLowerCase()}`}>
          {TYPE_LABELS[data.type] || data.type}
        </span>
        {data.status && data.status !== "unknown" && (
          <span className={`graph-status ${data.status}`}>
            {STATUS_LABELS[data.status] || data.status}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const MemoExpertNode = memo(ExpertNode);

const nodeTypes = {
  Symptom: MemoExpertNode,
  Fault: MemoExpertNode,
  Component: MemoExpertNode,
  Subsystem: MemoExpertNode,
  VehicleSystem: MemoExpertNode,
  Repair: MemoExpertNode,
};

function toVisualEdge(edge) {
  const isSymptomEdge = edge.type === "HAS_SYMPTOM";
  const label = edge.label || EDGE_LABELS[edge.type] || "Liên quan";
  const style = EDGE_STYLES[edge.type] || {
    stroke: "rgba(100, 116, 139, 0.5)",
    strokeWidth: 1.5,
  };

  return {
    id: edge.id,
    source: isSymptomEdge ? edge.target : edge.source,
    target: isSymptomEdge ? edge.source : edge.target,
    label,
    animated: false,
    type: "smoothstep",
    data: edge,
    style,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: style.stroke,
    },
    labelBgPadding: [7, 3],
    labelBgBorderRadius: 8,
    labelBgStyle: {
      fill: "#0c1118",
      fillOpacity: 0.82,
    },
    labelStyle: {
      fill: "#9aa8bc",
      fontSize: 10.5,
      fontWeight: 700,
    },
  };
}

function nodeDimensions(node) {
  const labelLength = displayLabel(node).length;
  const width = Math.min(
    maxNodeWidth,
    Math.max(minNodeWidth, 164 + Math.min(labelLength, 42) * 2.2)
  );
  const height = labelLength > 58 ? 112 : labelLength > 32 ? 100 : baseNodeHeight;
  return { width, height };
}

function layoutGraph(nodes, edges) {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    ranksep: 150,
    nodesep: 70,
    edgesep: 30,
  });

  nodes.forEach((node) => {
    const { width, height } = nodeDimensions(node.data || node);
    graph.setNode(node.id, {
      width,
      height,
      rank: NODE_LEVEL[node.type] ?? 10,
    });
  });

  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target);
  });

  dagre.layout(graph);

  return nodes.map((node) => {
    const position = graph.node(node.id) || { x: 0, y: 0 };
    const level = NODE_LEVEL[node.type] ?? 5;
    const { width, height } = nodeDimensions(node.data || node);
    const snappedY = Math.round((position.y - height / 2) / rowGap) * rowGap;

    return {
      ...node,
      style: {
        width,
      },
      position: {
        x: level * levelGap,
        y: snappedY,
      },
    };
  });
}

function GraphCanvasInner({ graph, selectedNodeId, onNodeClick }) {
  const visualEdges = useMemo(() => (graph.edges || []).map(toVisualEdge), [graph.edges]);

  const nodes = useMemo(() => {
    const graphNodes = graph.nodes || [];
    const reactFlowNodes = graphNodes.map((node) => ({
      id: node.id,
      type: node.type,
      data: {
        ...node,
        raw: node,
      },
      className: `graph-node ${node.type?.toLowerCase()} ${node.status || ""} ${
        selectedNodeId === node.id ? "selected" : ""
      }`,
      position: { x: 0, y: 0 },
      sourcePosition: "right",
      targetPosition: "left",
    }));

    return layoutGraph(reactFlowNodes, visualEdges);
  }, [graph.nodes, selectedNodeId, visualEdges]);

  const { fitView } = useReactFlow();

  useEffect(() => {
    window.requestAnimationFrame(() => {
      fitView({ padding: 0.18, duration: 450 });
    });
  }, [fitView, nodes.length, visualEdges.length]);

  return (
    <div className="graph-canvas">
      <ReactFlow
        nodes={nodes}
        edges={visualEdges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.12}
        maxZoom={1.5}
        onNodeClick={(_, node) => onNodeClick?.(node.data.raw)}
      >
        <MiniMap
          nodeStrokeWidth={3}
          pannable
          zoomable
          nodeClassName={(node) => `minimap-${node.type?.toLowerCase()}`}
        />
        <Controls />
        <Background gap={24} color="rgba(139, 155, 184, 0.16)" />
      </ReactFlow>
    </div>
  );
}

export default function GraphCanvas({
  graph = { nodes: [], edges: [] },
  selectedNodeId,
  onNodeClick,
}) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner
        graph={graph}
        selectedNodeId={selectedNodeId}
        onNodeClick={onNodeClick}
      />
    </ReactFlowProvider>
  );
}

function displayLabel(node) {
  const value =
    SYSTEM_LABELS[node.label] || SYSTEM_LABELS[node.id] || node.label || node.id;
  return normalizeAutomotiveTerm(value);
}

function normalizeAutomotiveTerm(value) {
  if (!value) {
    return value;
  }

  return String(value).replaceAll("Bạc đạn", "Ổ bi");
}
