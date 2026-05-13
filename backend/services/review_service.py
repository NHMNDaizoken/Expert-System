from fastapi import HTTPException, status
from neo4j import GraphDatabase

from backend.core.config import settings


class ReviewService:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self):
        self.driver.close()

    def list_pending(self):
        query = """
        MATCH (f:Fault)-[r:HAS_SYMPTOM]->(s:Symptom)
        WHERE coalesce(r.status, f.status, s.status) = 'pending_review'
        RETURN
            coalesce(r.id, elementId(r)) AS rule_id,
            f.name AS fault_name,
            f.label_vi AS fault_label,
            s.name AS symptom_name,
            s.label_vi AS symptom_label,
            r.cf AS cf,
            coalesce(r.status, 'pending_review') AS status
        ORDER BY rule_id
        """
        with self.driver.session() as session:
            return [dict(record) for record in session.run(query)]

    def set_rule_status(self, rule_id, new_status, cf=None, note=None):
        query = """
        MATCH (f:Fault)-[r:HAS_SYMPTOM]->(s:Symptom)
        WHERE coalesce(r.id, elementId(r)) = $rule_id
        SET r.status = $new_status,
            r.review_note = $note
        FOREACH (_ IN CASE WHEN $cf IS NULL THEN [] ELSE [1] END |
            SET r.cf = $cf
        )
        RETURN
            coalesce(r.id, elementId(r)) AS rule_id,
            f.name AS fault_name,
            s.name AS symptom_name,
            r.cf AS cf,
            r.status AS status
        """
        with self.driver.session() as session:
            record = session.run(
                query,
                rule_id=rule_id,
                new_status=new_status,
                cf=cf,
                note=note,
            ).single()

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule was not found.",
            )
        return dict(record)
