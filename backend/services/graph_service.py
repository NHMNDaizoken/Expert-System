import json
import re
from pathlib import Path

from neo4j import GraphDatabase

from backend.config import settings
from backend.services.diagnosis_service import confidence_label


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = PROJECT_ROOT / "data" / "staging" / "ontology.json"
RULES_PATH = PROJECT_ROOT / "data" / "staging" / "kg_rules_from_dataset.json"
SYMPTOM_ALIASES_PATH = PROJECT_ROOT / "data" / "staging" / "symptom_aliases.json"
TRANSLATIONS_PATH = PROJECT_ROOT / "data" / "staging" / "vi_translations.json"

RELATION_LABELS = {
    "HAS_SYMPTOM": "Dấu hiệu",
    "CAUSED_BY": "Nguyên nhân",
    "AFFECTS": "Ảnh hưởng đến",
    "FIXED_BY": "Giải pháp sửa chữa",
    "RELATED_TO": "Liên quan đến",
    "PART_OF": "Thuộc hệ thống",
}


def slugify(text):
    text = str(text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


class GraphService:
    NODE_LABELS = [
        "VehicleSystem",
        "Subsystem",
        "Component",
        "Fault",
        "Symptom",
        "Repair",
    ]
    SEARCH_LABELS = {"Fault", "Symptom", "Component", "Repair"}
    RELATIONSHIP_TYPES = [
        "PART_OF",
        "AFFECTS",
        "HAS_SYMPTOM",
        "FIXED_BY",
        "RELATED_TO",
    ]

    def __init__(self):
        self.driver = None
        self.translations = self._load_json(TRANSLATIONS_PATH, default={})
        if settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password:
            self.driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )

    def close(self):
        if self.driver is not None:
            self.driver.close()

    def get_graph(self):
        try:
            graph = self._get_graph_from_neo4j()
            if graph["nodes"]:
                return graph
        except Exception:
            pass

        try:
            return self._get_graph_from_files()
        except Exception:
            return {"nodes": [], "edges": []}

    def get_fault_graph(self, fault_id):
        try:
            graph = self._get_fault_graph_from_neo4j(fault_id)
            if graph["nodes"]:
                return graph
        except Exception:
            pass

        try:
            return self._get_fault_graph_from_files(fault_id)
        except Exception:
            return {"nodes": [], "edges": []}

    def search_graph(self, query):
        query = (query or "").strip()
        if not query:
            return []

        try:
            results = self._search_graph_from_neo4j(query)
            if results:
                return results
        except Exception:
            pass

        try:
            return self._search_graph_from_files(query)
        except Exception:
            return []

    def list_faults(self, query="", limit=200):
        query = (query or "").strip()
        limit = max(1, min(int(limit or 200), 500))

        try:
            results = self._list_faults_from_neo4j(query, limit)
            if results:
                return results
        except Exception:
            pass

        try:
            return self._list_faults_from_files(query, limit)
        except Exception:
            return []

    def get_stats(self):
        try:
            stats = self._get_stats_from_neo4j()
            if stats["relationships"] or any(stats[label] for label in self.NODE_LABELS):
                return stats
        except Exception:
            pass

        try:
            return self._get_stats_from_files()
        except Exception:
            return self._empty_stats()

    def _get_graph_from_neo4j(self):
        if self.driver is None:
            return {"nodes": [], "edges": []}

        query = """
        MATCH (n)
        WHERE any(label IN labels(n)
          WHERE label IN ['VehicleSystem', 'Subsystem', 'Component', 'Fault', 'Symptom', 'Repair'])
        OPTIONAL MATCH (n)-[r:PART_OF|AFFECTS|HAS_SYMPTOM|FIXED_BY|RELATED_TO]->(m)
        WHERE m IS NULL OR any(label IN labels(m)
          WHERE label IN ['VehicleSystem', 'Subsystem', 'Component', 'Fault', 'Symptom', 'Repair'])
        RETURN n, r, m
        """
        nodes = []
        edges = []

        with self.driver.session() as session:
            for record in session.run(query):
                nodes.append(self._format_node(record["n"], self._labels(record["n"])))
                if record["m"] is None:
                    continue
                nodes.append(self._format_node(record["m"], self._labels(record["m"])))
                edges.append(self._format_edge(record["r"]))

        return {
            "nodes": self._dedupe_nodes(nodes),
            "edges": self._dedupe_edges(edges),
        }

    def _get_fault_graph_from_neo4j(self, fault_id):
        if self.driver is None:
            return {"nodes": [], "edges": []}

        query = """
        MATCH (f:Fault {id: $fault_id})
        OPTIONAL MATCH (f)-[hs:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (f)-[af:AFFECTS]->(c:Component)
        OPTIONAL MATCH (c)-[cp:PART_OF]->(sub:Subsystem)
        OPTIONAL MATCH (sub)-[sp:PART_OF]->(sys:VehicleSystem)
        OPTIONAL MATCH (f)-[fr:FIXED_BY]->(r:Repair)
        OPTIONAL MATCH (f)-[rel:RELATED_TO]-(rf:Fault)
        RETURN
          [node IN [f] + collect(DISTINCT s) + collect(DISTINCT c)
            + collect(DISTINCT sub) + collect(DISTINCT sys)
            + collect(DISTINCT r) + collect(DISTINCT rf)
            WHERE node IS NOT NULL] AS nodes,
          [edge IN collect(DISTINCT hs) + collect(DISTINCT af)
            + collect(DISTINCT cp) + collect(DISTINCT sp)
            + collect(DISTINCT fr) + collect(DISTINCT rel)
            WHERE edge IS NOT NULL] AS edges
        """

        with self.driver.session() as session:
            record = session.run(query, fault_id=fault_id).single()

        if record is None:
            return {"nodes": [], "edges": []}

        nodes = [
            self._format_node(node, self._labels(node))
            for node in record["nodes"]
            if node is not None
        ]
        edges = [
            self._format_edge(edge)
            for edge in record["edges"]
            if edge is not None
        ]
        return {
            "nodes": self._dedupe_nodes(nodes),
            "edges": self._dedupe_edges(edges),
        }

    def _search_graph_from_neo4j(self, query):
        if self.driver is None:
            return []

        cypher = """
        MATCH (n)
        WHERE any(label IN labels(n)
          WHERE label IN ['Fault', 'Symptom', 'Component', 'Repair'])
        WITH n, toLower($query) AS q
        WHERE toLower(toString(coalesce(n.id, ""))) CONTAINS q
           OR toLower(toString(coalesce(n.name, ""))) CONTAINS q
           OR toLower(toString(coalesce(n.display_name, ""))) CONTAINS q
           OR toLower(toString(coalesce(n.label_vi, ""))) CONTAINS q
        RETURN n
        LIMIT 30
        """

        with self.driver.session() as session:
            nodes = [
                self._format_node(record["n"], self._labels(record["n"]))
                for record in session.run(cypher, query=query)
            ]

        return self._compact_nodes(nodes)

    def _list_faults_from_neo4j(self, query, limit):
        if self.driver is None:
            return []

        cypher = """
        MATCH (f:Fault)
        WITH f, toLower($query) AS q
        WHERE q = ""
           OR toLower(toString(coalesce(f.id, ""))) CONTAINS q
           OR toLower(toString(coalesce(f.name, ""))) CONTAINS q
           OR toLower(toString(coalesce(f.display_name, ""))) CONTAINS q
           OR toLower(toString(coalesce(f.label_vi, ""))) CONTAINS q
        OPTIONAL MATCH (f)-[:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (f)-[:AFFECTS]->(c:Component)
        RETURN f, count(DISTINCT s) AS symptom_count, count(DISTINCT c) AS component_count
        ORDER BY coalesce(f.display_name, f.label_vi, f.name, f.id)
        LIMIT $limit
        """

        with self.driver.session() as session:
            nodes = []
            for record in session.run(cypher, query=query, limit=limit):
                node = self._format_node(record["f"], self._labels(record["f"]))
                node["summary"] = {
                    "symptom_count": int(record["symptom_count"] or 0),
                    "component_count": int(record["component_count"] or 0),
                }
                nodes.append(node)

        return self._compact_faults(nodes)

    def _get_stats_from_neo4j(self):
        if self.driver is None:
            return self._empty_stats()

        stats = self._empty_stats()

        with self.driver.session() as session:
            for label in self.NODE_LABELS:
                record = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS count"
                ).single()
                stats[label] = int(record["count"]) if record is not None else 0

            record = session.run("MATCH ()-[r]->() RETURN count(r) AS count").single()
            stats["relationships"] = int(record["count"]) if record is not None else 0

        return stats

    def _get_graph_from_files(self):
        ontology = self._load_json(ONTOLOGY_PATH, default={"vehicle_systems": []})
        rules_data = self._load_json(RULES_PATH, default=[])
        symptom_aliases = self._load_json(SYMPTOM_ALIASES_PATH, default={})
        rules = rules_data.get("rules", rules_data) if isinstance(rules_data, dict) else rules_data

        nodes = []
        edges = []

        def add_node(node_id, label, node_type, status="approved", metadata=None):
            properties = dict(metadata or {})
            properties.update({
                "id": node_id,
                "label": label or node_id,
                "type": node_type,
                "status": status,
            })
            nodes.append(self._format_node(properties, [node_type]))

        def add_edge(source, target, edge_type, cf=None, metadata=None):
            edge_id = f"{source}-{edge_type}-{target}"
            edges.append({
                "id": edge_id,
                "source": source,
                "target": target,
                "type": edge_type,
                "label": RELATION_LABELS.get(edge_type, edge_type),
                "cf": cf,
                "confidence_label": (
                    confidence_label(float(cf)) if cf is not None else None
                ),
                "metadata": metadata or {},
            })

        for system in ontology.get("vehicle_systems", []):
            system_id = system["id"]
            add_node(
                system_id,
                self._display_label(system),
                "VehicleSystem",
                metadata=system,
            )

            for subsystem in system.get("subsystems", []):
                subsystem_id = subsystem["id"]
                add_node(
                    subsystem_id,
                    self._display_label(subsystem),
                    "Subsystem",
                    metadata=subsystem,
                )
                add_edge(subsystem_id, system_id, "PART_OF")

                for component in subsystem.get("components", []):
                    component_id = component["id"]
                    add_node(
                        component_id,
                        self._display_label(component),
                        "Component",
                        metadata=component,
                    )
                    add_edge(component_id, subsystem_id, "PART_OF")

        for symptom_id, symptom in symptom_aliases.items():
            add_node(symptom_id, self._display_label(symptom), "Symptom", metadata=symptom)

        for rule in rules:
            fault_id = rule["fault_id"]
            status = rule.get("status", "approved")
            add_node(fault_id, self._display_label(rule), "Fault", status, metadata=rule)

            for component_id in rule.get("affected_components", []):
                add_edge(fault_id, component_id, "AFFECTS")

            for symptom in rule.get("symptoms", []):
                symptom_id = symptom["symptom_id"]
                if not any(node["id"] == symptom_id for node in nodes):
                    add_node(symptom_id, symptom_id, "Symptom")
                add_edge(
                    fault_id,
                    symptom_id,
                    "HAS_SYMPTOM",
                    symptom.get("cf"),
                    {"priority": symptom.get("priority", 2)},
                )

            for repair in rule.get("repairs", []):
                repair_id = repair["repair_id"]
                add_node(repair_id, self._display_label(repair), "Repair", status, repair)
                add_edge(fault_id, repair_id, "FIXED_BY")

        return {
            "nodes": self._dedupe_nodes(nodes),
            "edges": self._dedupe_edges(edges),
        }

    def _get_fault_graph_from_files(self, fault_id):
        graph = self._get_graph_from_files()
        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        if fault_id not in nodes_by_id:
            return {"nodes": [], "edges": []}

        selected_node_ids = {fault_id}
        selected_edges = []
        affected_component_ids = set()

        for edge in graph["edges"]:
            if edge["source"] == fault_id and edge["type"] in {
                "HAS_SYMPTOM",
                "AFFECTS",
                "FIXED_BY",
                "RELATED_TO",
            }:
                selected_edges.append(edge)
                selected_node_ids.add(edge["target"])
                if edge["type"] == "AFFECTS":
                    affected_component_ids.add(edge["target"])
            elif edge["target"] == fault_id and edge["type"] == "RELATED_TO":
                selected_edges.append(edge)
                selected_node_ids.add(edge["source"])

        parent_ids = set(affected_component_ids)
        while parent_ids:
            current_id = parent_ids.pop()
            for edge in graph["edges"]:
                if edge["source"] == current_id and edge["type"] == "PART_OF":
                    selected_edges.append(edge)
                    if edge["target"] not in selected_node_ids:
                        selected_node_ids.add(edge["target"])
                        parent_ids.add(edge["target"])

        return {
            "nodes": [
                nodes_by_id[node_id]
                for node_id in selected_node_ids
                if node_id in nodes_by_id
            ],
            "edges": self._dedupe_edges(selected_edges),
        }

    def _search_graph_from_files(self, query):
        graph = self._get_graph_from_files()
        needle = query.lower()
        matches = []

        for node in graph["nodes"]:
            if node.get("type") not in self.SEARCH_LABELS:
                continue

            metadata = node.get("metadata") or {}
            haystack = [
                node.get("id"),
                node.get("label"),
                metadata.get("name"),
                metadata.get("display_name"),
                metadata.get("label_vi"),
            ]
            if any(needle in str(value).lower() for value in haystack if value):
                matches.append(node)

        return self._compact_nodes(matches[:30])

    def _list_faults_from_files(self, query, limit):
        rules_data = self._load_json(RULES_PATH, default=[])
        rules = rules_data.get("rules", rules_data) if isinstance(rules_data, dict) else rules_data
        needle = query.lower()
        faults = []

        for rule in rules:
            metadata = rule or {}
            haystack = [
                metadata.get("fault_id"),
                metadata.get("fault_name"),
                metadata.get("display_name"),
                metadata.get("label_vi"),
                metadata.get("system"),
                metadata.get("system_id"),
            ]
            if needle and not any(needle in str(value).lower() for value in haystack if value):
                continue

            fault_id = metadata.get("fault_id")
            if not fault_id:
                continue

            faults.append({
                "id": fault_id,
                "label": self._display_label(metadata) or fault_id,
                "type": "Fault",
                "status": metadata.get("status", "approved"),
                "summary": {
                    "system": metadata.get("system_id") or metadata.get("system"),
                    "symptom_count": len(metadata.get("symptoms", [])),
                    "component_count": len(metadata.get("affected_components", [])),
                    "repair_count": len(metadata.get("repairs", [])),
                },
            })

        faults.sort(key=lambda item: item["label"].lower())
        return faults[:limit]

    def _get_stats_from_files(self):
        graph = self._get_graph_from_files()
        stats = self._empty_stats()

        for node in graph["nodes"]:
            node_type = node.get("type")
            if node_type in stats:
                stats[node_type] += 1

        stats["relationships"] = len(graph["edges"])
        return stats

    def _load_json(self, path, default):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _display_label(self, data):
        return self._localize_display_label(
            data.get("label_vi")
            or data.get("display_name")
            or data.get("label")
            or data.get("fault_label")
            or data.get("fault_name")
            or data.get("repair_label")
            or data.get("repair_name")
            or data.get("name")
        )

    def _localize_display_label(self, value):
        text = str(value or "").strip()
        if not text:
            return text
        action_label = self._format_action_label(text)
        if action_label != text:
            return action_label
        return self.translations.get(slugify(text), text)

    def _format_action_label(self, text):
        patterns = [
            (r"^Diagnosis for (.+)$", "Kiểm tra"),
            (r"^Repair for (.+)$", "Sửa chữa"),
            (r"^Replace (.+)$", "Thay"),
            (r"^Inspect (.+)$", "Kiểm tra"),
            (r"^Clean (.+)$", "Vệ sinh"),
            (r"^Test (.+)$", "Kiểm tra"),
            (r"^Adjust (.+)$", "Điều chỉnh"),
        ]
        for pattern, verb in patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if match:
                target = self.translations.get(slugify(match.group(1)), match.group(1).strip())
                return f"{verb} {target}"
        return text

    def _node_id(self, node):
        properties = self._node_properties(node)
        return str(
            properties.get("id")
            or properties.get("name")
            or getattr(node, "element_id", "")
        )

    def _format_node(self, node, labels):
        properties = self._node_properties(node)
        node_id = self._node_id(node)
        node_type = next(
            (label for label in self.NODE_LABELS if label in labels),
            properties.get("type") or (labels[0] if labels else "Node"),
        )
        label = self._localize_display_label(
            properties.get("label_vi")
            or properties.get("display_name")
            or properties.get("label")
            or properties.get("fault_label")
            or properties.get("fault_name")
            or properties.get("repair_label")
            or properties.get("repair_name")
            or properties.get("name")
            or node_id
        )
        metadata = {
            key: self._json_safe(value)
            for key, value in properties.items()
            if key not in {"id", "label", "type", "status"}
        }
        return {
            "id": node_id,
            "label": label,
            "type": node_type,
            "status": properties.get("status") or "unknown",
            "metadata": metadata,
        }

    def _format_edge(self, rel):
        cf = rel.get("cf")
        confidence = None
        if cf is not None:
            try:
                confidence = confidence_label(float(cf))
            except (TypeError, ValueError):
                confidence = None
        metadata = {
            key: self._json_safe(value)
            for key, value in self._node_properties(rel).items()
            if key != "cf"
        }

        return {
            "id": str(getattr(rel, "element_id", "")) or (
                f"{self._node_id(rel.start_node)}-{rel.type}-{self._node_id(rel.end_node)}"
            ),
            "source": self._node_id(rel.start_node),
            "target": self._node_id(rel.end_node),
            "type": rel.type,
            "label": RELATION_LABELS.get(rel.type, rel.type),
            "cf": cf,
            "confidence_label": confidence,
            "metadata": metadata,
        }

    def _dedupe_nodes(self, nodes):
        deduped = {}
        for node in nodes:
            if not node or not node.get("id"):
                continue
            deduped[node["id"]] = node
        return list(deduped.values())

    def _dedupe_edges(self, edges):
        deduped = {}
        for edge in edges:
            if not edge:
                continue
            edge_id = edge.get("id") or (
                f"{edge.get('source')}-{edge.get('type')}-{edge.get('target')}"
            )
            deduped[edge_id] = {**edge, "id": edge_id}
        return list(deduped.values())

    def _compact_nodes(self, nodes):
        return [
            {
                "id": node["id"],
                "label": node["label"],
                "type": node["type"],
                "status": node["status"],
            }
            for node in self._dedupe_nodes(nodes)
        ]

    def _compact_faults(self, nodes):
        return [
            {
                "id": node["id"],
                "label": node["label"],
                "type": node["type"],
                "status": node["status"],
                "summary": node.get("summary", {}),
            }
            for node in self._dedupe_nodes(nodes)
        ]

    def _labels(self, node):
        return list(getattr(node, "labels", []))

    def _node_properties(self, node):
        try:
            return dict(node)
        except (TypeError, ValueError):
            return {}

    def _json_safe(self, value):
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, list | tuple | set):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        return str(value)

    def _empty_stats(self):
        return {**{label: 0 for label in self.NODE_LABELS}, "relationships": 0}
