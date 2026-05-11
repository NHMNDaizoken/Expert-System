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

const nodeWidth = 220;
const nodeHeight = 86;
const levelGap = nodeWidth + 180;

const NODE_LEVEL = {
  Symptom: 0,
  Fault: 1,
  Component: 2,
  Subsystem: 3,
  VehicleSystem: 4,
  Repair: 2,
};

const EDGE_STYLES = {
  HAS_SYMPTOM: { stroke: "#2563eb", strokeWidth: 2.4 },
  AFFECTS: { stroke: "#dc2626", strokeWidth: 2.4 },
  PART_OF: { stroke: "#0f766e", strokeWidth: 2.2 },
  FIXED_BY: { stroke: "#16a34a", strokeWidth: 2.4 },
  RELATED_TO: { stroke: "#7c3aed", strokeWidth: 2, strokeDasharray: "6 5" },
};

function ExpertNode({ data }) {
  return (
    <div className="graph-node-card">
      <Handle type="target" position={Position.Left} />
      <div className="graph-node-label">{data.label}</div>
      <div className="graph-node-meta">
        <span className={`graph-type-badge ${data.type?.toLowerCase()}`}>
          {data.type}
        </span>
        {data.status && data.status !== "unknown" && (
          <span className={`graph-status ${data.status}`}>{data.status}</span>
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

  return {
    id: edge.id,
    source: isSymptomEdge ? edge.target : edge.source,
    target: isSymptomEdge ? edge.source : edge.target,
    label: edge.cf == null ? edge.type : `${edge.type} ${Number(edge.cf).toFixed(2)}`,
    animated: isSymptomEdge,
    type: "smoothstep",
    data: edge,
    style: EDGE_STYLES[edge.type] || { stroke: "#64748b", strokeWidth: 2 },
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: EDGE_STYLES[edge.type]?.stroke || "#64748b",
    },
    labelBgPadding: [8, 4],
    labelBgBorderRadius: 6,
    labelBgStyle: {
      fill: "#1a1d27",
      fillOpacity: 0.95,
    },
    labelStyle: {
      fill: "#94a3b8",
      fontSize: 11,
      fontWeight: 700,
    },
  };
}

function layoutGraph(nodes, edges) {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "LR",
    ranksep: 180,
    nodesep: 80,
    edgesep: 30,
  });

  nodes.forEach((node) => {
    graph.setNode(node.id, {
      width: nodeWidth,
      height: nodeHeight,
      rank: NODE_LEVEL[node.type] ?? 10,
    });
  });

  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target);
  });

  dagre.layout(graph);

  const levelOffsets = new Map();

  return nodes.map((node) => {
    const position = graph.node(node.id) || { x: 0, y: 0 };
    const level = NODE_LEVEL[node.type] ?? 5;
    const sameLevelCount = levelOffsets.get(level) || 0;
    levelOffsets.set(level, sameLevelCount + 1);

    return {
      ...node,
      position: {
        x: level * levelGap,
        y: position.y - nodeHeight / 2 + sameLevelCount * 4,
      },
    };
  });
}

function GraphCanvasInner({ graph, onNodeClick }) {
  const visualEdges = useMemo(
    () => (graph.edges || []).map(toVisualEdge),
    [graph.edges]
  );

  const nodes = useMemo(() => {
    const graphNodes = graph.nodes || [];
    const reactFlowNodes = graphNodes.map((node) => ({
      id: node.id,
      type: node.type,
      data: {
        ...node,
        raw: node,
      },
      className: `graph-node ${node.type?.toLowerCase()} ${node.status || ""}`,
      position: { x: 0, y: 0 },
      sourcePosition: "right",
      targetPosition: "left",
    }));

    return layoutGraph(reactFlowNodes, visualEdges);
  }, [graph.nodes, visualEdges]);

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
        <Background gap={22} color="#2d3245" />
      </ReactFlow>
    </div>
  );
}

export default function GraphCanvas({ graph = { nodes: [], edges: [] }, onNodeClick }) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner graph={graph} onNodeClick={onNodeClick} />
    </ReactFlowProvider>
  );
}
