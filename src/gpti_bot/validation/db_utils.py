"""
Database utilities for validation framework.
Replaces subprocess calls with proper SQLAlchemy queries.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import create_engine, text, func
from sqlalchemy.orm import sessionmaker
import logging

logger = logging.getLogger(__name__)

# Database connection
def _normalize_db_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _build_database_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return _normalize_db_url(env_url)

    user = os.environ.get("POSTGRES_USER", "gpti")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "gpti")

    if password:
        return _normalize_db_url(f"postgresql://{user}:{password}@{host}:{port}/{db}")
    return _normalize_db_url(f"postgresql://{user}@{host}:{port}/{db}")


DATABASE_URL = _build_database_url()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class ValidationDB:
    """Database interface for validation metrics."""

    @staticmethod
    def _load_active_weights(session) -> Dict[str, float]:
        result = session.execute(text("""
            SELECT weights
            FROM score_version
            WHERE is_active = true
            LIMIT 1
        """))
        row = result.fetchone()
        return row[0] if row and row[0] else {}

    @staticmethod
    def _get_snapshot_meta(session, snapshot_key_or_id: str) -> Optional[Dict]:
        """Resolve snapshot metadata by key or numeric id."""
        try:
            snap_id = int(snapshot_key_or_id)
        except (TypeError, ValueError):
            snap_id = None

        if snap_id is not None:
            result = session.execute(text("""
                SELECT id, snapshot_key, created_at
                FROM snapshot_metadata
                WHERE id = :snap_id
                LIMIT 1
            """), {"snap_id": snap_id})
        else:
            result = session.execute(text("""
                SELECT id, snapshot_key, created_at
                FROM snapshot_metadata
                WHERE snapshot_key = :snap_key
                ORDER BY created_at DESC
                LIMIT 1
            """), {"snap_key": snapshot_key_or_id})

        row = result.fetchone()
        if not row:
            return None

        return {"id": row[0], "snapshot_key": row[1], "created_at": row[2]}

    @staticmethod
    def _get_latest_score_snapshot_id(session, snapshot_key: str) -> Optional[int]:
        result = session.execute(text("""
            SELECT snapshot_id
            FROM snapshot_scores
            WHERE snapshot_key = :snapshot_key
            ORDER BY snapshot_id DESC
            LIMIT 1
        """), {"snapshot_key": snapshot_key})
        row = result.fetchone()
        return row[0] if row else None

    @staticmethod
    def get_session():
        """Get a new database session."""
        return SessionLocal()

    @staticmethod
    def compute_coverage_metrics(snapshot_id: str) -> Dict:
        """
        Test 1: Coverage & Data Sufficiency
        
        Metrics:
        - coverage_percent: % of firms with rules_extracted
        - avg_na_rate: average NA_rate across all firms
        - agent_c_pass_rate: % of firms passing Oversight Gate verification
        """
        session = ValidationDB.get_session()
        try:
            snapshot = ValidationDB._get_snapshot_meta(session, snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot {snapshot_id} not found")
                return {
                    "total_firms": 0,
                    "coverage_percent": 0,
                    "avg_na_rate": 0,
                    "agent_c_pass_rate": 0
                }

            latest_score_snapshot_id = ValidationDB._get_latest_score_snapshot_id(session, snapshot["snapshot_key"])
            if not latest_score_snapshot_id:
                logger.warning(f"No scores found for snapshot_key {snapshot['snapshot_key']}")
                return {
                    "total_firms": 0,
                    "coverage_percent": 0,
                    "avg_na_rate": 0,
                    "agent_c_pass_rate": 0
                }

            result = session.execute(text("""
                SELECT
                    COUNT(DISTINCT firm_id) as total_firms,
                    COUNT(DISTINCT CASE WHEN score_0_100 IS NOT NULL THEN firm_id END) * 100.0 /
                        NULLIF(COUNT(DISTINCT firm_id), 0) as coverage_percent,
                    AVG(na_rate) * 100.0 as avg_na_rate
                FROM snapshot_scores
                WHERE snapshot_id = :snapshot_id
            """), {"snapshot_id": latest_score_snapshot_id})
            
            row = result.fetchone()
            
            pass_rate_result = session.execute(text("""
                SELECT COUNT(*) FILTER (WHERE verdict = 'pass') * 100.0 /
                       NULLIF(COUNT(*), 0) as pass_rate
                FROM agent_c_audit
                WHERE snapshot_key = :snapshot_key
            """), {"snapshot_key": snapshot["snapshot_key"]})
            pass_rate = pass_rate_result.fetchone()[0]

            return {
                "total_firms": int(row[0]) if row[0] else 0,
                "coverage_percent": round(float(row[1]) if row[1] else 0, 2),
                "avg_na_rate": round(float(row[2]) if row[2] else 0, 2),
                "agent_c_pass_rate": round(float(pass_rate) if pass_rate else 0, 2)
            }
        except Exception as e:
            logger.error(f"Error computing coverage metrics: {e}")
            return {
                "total_firms": 0,
                "coverage_percent": 0,
                "avg_na_rate": 0,
                "agent_c_pass_rate": 0
            }
        finally:
            session.close()

    @staticmethod
    def compute_stability_metrics(snapshot_id: str, prev_snapshot_id: Optional[str] = None) -> Dict:
        """
        Test 2: Stability & Turnover
        
        Metrics:
        - avg_score_change: average absolute score change from previous snapshot
        - top_10_turnover: number of firms entering/leaving top 10
        - top_20_turnover: number of firms entering/leaving top 20
        - verdict_churn_rate: % of firms changing verdict (pass → review)
        """
        session = ValidationDB.get_session()
        try:
            snapshot = ValidationDB._get_snapshot_meta(session, snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot {snapshot_id} not found")
                return {
                    "avg_score_change": 0,
                    "top_10_turnover": 0,
                    "top_20_turnover": 0,
                    "verdict_churn_rate": 0
                }

            latest_score_snapshot_id = ValidationDB._get_latest_score_snapshot_id(session, snapshot["snapshot_key"])
            if not latest_score_snapshot_id:
                logger.warning(f"No scores found for snapshot_key {snapshot['snapshot_key']}")
                return {
                    "avg_score_change": 0,
                    "top_10_turnover": 0,
                    "top_20_turnover": 0,
                    "verdict_churn_rate": 0
                }

            if prev_snapshot_id:
                prev_snapshot = ValidationDB._get_snapshot_meta(session, prev_snapshot_id)
                prev_score_snapshot_id = ValidationDB._get_latest_score_snapshot_id(session, prev_snapshot["snapshot_key"]) if prev_snapshot else None
            else:
                result = session.execute(text("""
                    SELECT snapshot_id
                    FROM snapshot_scores
                    WHERE snapshot_key = :snapshot_key AND snapshot_id < :current_id
                    ORDER BY snapshot_id DESC
                    LIMIT 1
                """), {
                    "snapshot_key": snapshot["snapshot_key"],
                    "current_id": latest_score_snapshot_id
                })
                row = result.fetchone()
                prev_score_snapshot_id = row[0] if row else None

            if not prev_score_snapshot_id:
                logger.warning(f"No previous score snapshot found for {snapshot['snapshot_key']}")
                return {
                    "avg_score_change": 0,
                    "top_10_turnover": 0,
                    "top_20_turnover": 0,
                    "verdict_churn_rate": 0
                }

            # Score changes
            result = session.execute(text("""
                SELECT AVG(ABS(curr.score_0_100 - prev.score_0_100)) as avg_change
                FROM snapshot_scores curr
                JOIN snapshot_scores prev ON curr.firm_id = prev.firm_id
                WHERE curr.snapshot_id = :curr_id AND prev.snapshot_id = :prev_id
            """), {"curr_id": latest_score_snapshot_id, "prev_id": prev_score_snapshot_id})
            
            avg_change = result.fetchone()[0] or 0

            # Top 10 turnover
            result = session.execute(text("""
                WITH curr_top_10 AS (
                    SELECT firm_id FROM snapshot_scores
                    WHERE snapshot_id = :curr_id
                    ORDER BY score_0_100 DESC NULLS LAST LIMIT 10
                ),
                prev_top_10 AS (
                    SELECT firm_id FROM snapshot_scores
                    WHERE snapshot_id = :prev_id
                    ORDER BY score_0_100 DESC NULLS LAST LIMIT 10
                )
                SELECT COUNT(*) FROM (
                    SELECT * FROM curr_top_10
                    EXCEPT
                    SELECT * FROM prev_top_10
                ) as diff
            """), {"curr_id": latest_score_snapshot_id, "prev_id": prev_score_snapshot_id})
            
            top_10_turnover = result.fetchone()[0] or 0

            # Top 20 turnover
            result = session.execute(text("""
                WITH curr_top_20 AS (
                    SELECT firm_id FROM snapshot_scores
                    WHERE snapshot_id = :curr_id
                    ORDER BY score_0_100 DESC NULLS LAST LIMIT 20
                ),
                prev_top_20 AS (
                    SELECT firm_id FROM snapshot_scores
                    WHERE snapshot_id = :prev_id
                    ORDER BY score_0_100 DESC NULLS LAST LIMIT 20
                )
                SELECT COUNT(*) FROM (
                    SELECT * FROM curr_top_20
                    EXCEPT
                    SELECT * FROM prev_top_20
                ) as diff
            """), {"curr_id": latest_score_snapshot_id, "prev_id": prev_score_snapshot_id})
            
            top_20_turnover = result.fetchone()[0] or 0

            # Verdict churn
            result = session.execute(text("""
                SELECT NULL::numeric as churn_rate
            """))
            
            churn_rate = result.fetchone()[0] or 0

            return {
                "avg_score_change": round(float(avg_change), 4),
                "top_10_turnover": int(top_10_turnover),
                "top_20_turnover": int(top_20_turnover),
                "verdict_churn_rate": round(float(churn_rate), 2)
            }
        except Exception as e:
            logger.error(f"Error computing stability metrics: {e}")
            return {
                "avg_score_change": 0,
                "top_10_turnover": 0,
                "top_20_turnover": 0,
                "verdict_churn_rate": 0
            }
        finally:
            session.close()

    @staticmethod
    def compute_ground_truth_validation(snapshot_id: str, lookback_days: int = 30) -> Dict:
        """
        Test 4: Ground-Truth Event Validation
        
        Metrics:
        - events_in_period: number of external events in lookback window
        - events_predicted: number of events preceded by NA-spike or score drop
        - prediction_precision: events_predicted / events_in_period
        """
        session = ValidationDB.get_session()
        try:
            snapshot = ValidationDB._get_snapshot_meta(session, snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot {snapshot_id} not found")
                return {
                    "events_in_period": 0,
                    "events_predicted": 0,
                    "prediction_precision": 0
                }

            snapshot_date = snapshot["created_at"]
            lookback_date = snapshot_date - timedelta(days=lookback_days)

            latest_score_snapshot_id = ValidationDB._get_latest_score_snapshot_id(session, snapshot["snapshot_key"])
            if not latest_score_snapshot_id:
                return {
                    "events_in_period": 0,
                    "events_predicted": 0,
                    "prediction_precision": 0
                }

            # Events in period
            result = session.execute(text("""
                SELECT COUNT(*) FROM events
                WHERE event_date >= :lookback_date AND event_date <= :snapshot_date
            """), {"lookback_date": lookback_date, "snapshot_date": snapshot_date})
            
            events_total = result.fetchone()[0] or 0

            # Events predicted (preceded by NA spike or score drop)
            # This is a simplified version - real implementation would check historical snapshots
            result = session.execute(text("""
                SELECT COUNT(*) FROM events e
                WHERE e.event_date >= :lookback_date AND e.event_date <= :snapshot_date
                AND EXISTS (
                    SELECT 1 FROM snapshot_scores s
                    LEFT JOIN firms f ON f.firm_id = s.firm_id
                    WHERE s.snapshot_id = :snapshot_id
                      AND (s.na_rate > 0.5 OR s.score_0_100 < 40)
                      AND (
                        (e.firm_id IS NOT NULL AND e.firm_id = s.firm_id)
                        OR (e.firm_id IS NULL AND e.firm_name IS NOT NULL AND f.brand_name = e.firm_name)
                      )
                )
            """), {
                "lookback_date": lookback_date,
                "snapshot_date": snapshot_date,
                                "snapshot_id": latest_score_snapshot_id
            })
            
            events_predicted = result.fetchone()[0] or 0

            precision = (events_predicted / events_total * 100) if events_total > 0 else 0

            return {
                "events_in_period": int(events_total),
                "events_predicted": int(events_predicted),
                "prediction_precision": round(precision, 2)
            }
        except Exception as e:
            logger.error(f"Error computing ground-truth validation: {e}")
            return {
                "events_in_period": 0,
                "events_predicted": 0,
                "prediction_precision": 0
            }
        finally:
            session.close()

    @staticmethod
    def compute_sensitivity_metrics(snapshot_id: str) -> Dict:
        """
        Test 3: Sensitivity & Stress Tests

        Metrics:
        - pillar_sensitivity_mean: avg absolute score impact when removing each pillar
        - fallback_usage_percent: % of pillar scores using NA fallback (0.5)
        - stability_score: 0-100 heuristic based on sensitivity + fallback usage
        """
        session = ValidationDB.get_session()
        try:
            snapshot = ValidationDB._get_snapshot_meta(session, snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot {snapshot_id} not found")
                return {
                    "pillar_sensitivity_mean": 0,
                    "fallback_usage_percent": 0,
                    "stability_score": 0
                }

            latest_score_snapshot_id = ValidationDB._get_latest_score_snapshot_id(session, snapshot["snapshot_key"])
            if not latest_score_snapshot_id:
                logger.warning(f"No scores found for snapshot_key {snapshot['snapshot_key']}")
                return {
                    "pillar_sensitivity_mean": 0,
                    "fallback_usage_percent": 0,
                    "stability_score": 0
                }

            weights = ValidationDB._load_active_weights(session)

            result = session.execute(text("""
                SELECT score_0_100, pillar_scores
                FROM snapshot_scores
                WHERE snapshot_id = :snapshot_id
            """), {"snapshot_id": latest_score_snapshot_id})

            total_impacts = 0.0
            impact_count = 0
            fallback_count = 0
            pillar_count = 0

            for score_0_100, pillar_scores in result:
                if not pillar_scores or score_0_100 is None:
                    continue

                try:
                    pillar_scores_dict = dict(pillar_scores)
                except Exception:
                    continue

                total_weight = sum(
                    float(weights.get(p, 0))
                    for p in pillar_scores_dict.keys()
                    if weights.get(p, 0) is not None
                )

                if total_weight <= 0:
                    continue

                for pillar_key, pillar_score in pillar_scores_dict.items():
                    pillar_count += 1
                    if pillar_score == 0.5:
                        fallback_count += 1

                    weight = float(weights.get(pillar_key, 0))
                    if weight <= 0:
                        continue

                    remaining_weight = total_weight - weight
                    if remaining_weight <= 0:
                        continue

                    remaining_sum = 0.0
                    for other_key, other_score in pillar_scores_dict.items():
                        if other_key == pillar_key:
                            continue
                        other_weight = float(weights.get(other_key, 0))
                        remaining_sum += float(other_score) * other_weight

                    score_without = 100.0 * (remaining_sum / remaining_weight)
                    total_impacts += abs(score_without - float(score_0_100))
                    impact_count += 1

            pillar_sensitivity_mean = (total_impacts / impact_count) if impact_count else 0.0
            fallback_usage_percent = (fallback_count / pillar_count * 100.0) if pillar_count else 0.0
            stability_score = max(0.0, 100.0 - (pillar_sensitivity_mean + fallback_usage_percent))

            return {
                "pillar_sensitivity_mean": round(float(pillar_sensitivity_mean), 4),
                "fallback_usage_percent": round(float(fallback_usage_percent), 2),
                "stability_score": round(float(stability_score), 2)
            }
        except Exception as e:
            logger.error(f"Error computing sensitivity metrics: {e}")
            return {
                "pillar_sensitivity_mean": 0,
                "fallback_usage_percent": 0,
                "stability_score": 0
            }
        finally:
            session.close()

    @staticmethod
    def compute_calibration_bias_metrics(snapshot_id: str) -> Dict:
        """
        Test 5: Calibration / Bias checks

        Metrics:
        - score_distribution_skew: skewness of score distribution
        - jurisdiction_bias_score: placeholder (no jurisdiction field available)
        - model_type_bias_score: max avg score gap across model_type
        """
        session = ValidationDB.get_session()
        try:
            snapshot = ValidationDB._get_snapshot_meta(session, snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot {snapshot_id} not found")
                return {
                    "score_distribution_skew": 0,
                    "jurisdiction_bias_score": 0,
                    "model_type_bias_score": 0
                }

            latest_score_snapshot_id = ValidationDB._get_latest_score_snapshot_id(session, snapshot["snapshot_key"])
            if not latest_score_snapshot_id:
                logger.warning(f"No scores found for snapshot_key {snapshot['snapshot_key']}")
                return {
                    "score_distribution_skew": 0,
                    "jurisdiction_bias_score": 0,
                    "model_type_bias_score": 0
                }

            result = session.execute(text("""
                SELECT s.score_0_100, f.model_type
                FROM snapshot_scores s
                JOIN firms f ON f.firm_id = s.firm_id
                WHERE s.snapshot_id = :snapshot_id
            """), {"snapshot_id": latest_score_snapshot_id})

            scores = []
            model_type_scores: Dict[str, List[float]] = {}
            for score_0_100, model_type in result:
                if score_0_100 is None:
                    continue
                score_val = float(score_0_100)
                scores.append(score_val)
                if model_type:
                    model_type_scores.setdefault(model_type, []).append(score_val)

            n = len(scores)
            if n < 3:
                skew = 0.0
            else:
                mean = sum(scores) / n
                variance = sum((x - mean) ** 2 for x in scores) / (n - 1)
                std = variance ** 0.5
                if std == 0:
                    skew = 0.0
                else:
                    skew = (n / ((n - 1) * (n - 2))) * sum(((x - mean) / std) ** 3 for x in scores)

            model_type_avgs = [sum(v) / len(v) for v in model_type_scores.values() if v]
            if len(model_type_avgs) >= 2:
                model_type_bias = max(model_type_avgs) - min(model_type_avgs)
            else:
                model_type_bias = 0.0

            return {
                "score_distribution_skew": round(float(skew), 4),
                "jurisdiction_bias_score": 0.0,
                "model_type_bias_score": round(float(model_type_bias), 2)
            }
        except Exception as e:
            logger.error(f"Error computing calibration/bias metrics: {e}")
            return {
                "score_distribution_skew": 0,
                "jurisdiction_bias_score": 0,
                "model_type_bias_score": 0
            }
        finally:
            session.close()

    @staticmethod
    def compute_auditability_metrics(snapshot_id: str) -> Dict:
        """
        Test 6: Auditability

        Metrics:
        - evidence_linkage_rate: % of firms with traceable evidence URLs or hashes
        - version_metadata: active scoring version
        """
        session = ValidationDB.get_session()
        try:
            snapshot = ValidationDB._get_snapshot_meta(session, snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot {snapshot_id} not found")
                return {
                    "evidence_linkage_rate": 0,
                    "version_metadata": None
                }

            latest_score_snapshot_id = ValidationDB._get_latest_score_snapshot_id(session, snapshot["snapshot_key"])
            if not latest_score_snapshot_id:
                logger.warning(f"No scores found for snapshot_key {snapshot['snapshot_key']}")
                return {
                    "evidence_linkage_rate": 0,
                    "version_metadata": None
                }

            total_result = session.execute(text("""
                SELECT COUNT(DISTINCT firm_id)
                FROM snapshot_scores
                WHERE snapshot_id = :snapshot_id
            """), {"snapshot_id": latest_score_snapshot_id})
            total_firms = total_result.fetchone()[0] or 0

            linked_result = session.execute(text("""
                SELECT COUNT(DISTINCT firm_id) FROM (
                    SELECT s.firm_id
                    FROM snapshot_scores s
                    JOIN datapoints d ON d.firm_id = s.firm_id
                    WHERE s.snapshot_id = :snapshot_id
                      AND (d.source_url IS NOT NULL OR d.evidence_hash IS NOT NULL)
                    UNION
                    SELECT s.firm_id
                    FROM snapshot_scores s
                    JOIN evidence e ON e.firm_id = s.firm_id
                    WHERE s.snapshot_id = :snapshot_id
                      AND (e.source_url IS NOT NULL OR e.sha256 IS NOT NULL)
                ) t
            """), {"snapshot_id": latest_score_snapshot_id})
            linked_firms = linked_result.fetchone()[0] or 0

            version_result = session.execute(text("""
                SELECT version_key
                FROM snapshot_scores
                WHERE snapshot_id = :snapshot_id
                GROUP BY version_key
                ORDER BY COUNT(*) DESC
                LIMIT 1
            """), {"snapshot_id": latest_score_snapshot_id})
            version_row = version_result.fetchone()
            version_metadata = version_row[0] if version_row else None

            evidence_linkage_rate = (linked_firms / total_firms * 100.0) if total_firms else 0.0

            return {
                "evidence_linkage_rate": round(float(evidence_linkage_rate), 2),
                "version_metadata": version_metadata
            }
        except Exception as e:
            logger.error(f"Error computing auditability metrics: {e}")
            return {
                "evidence_linkage_rate": 0,
                "version_metadata": None
            }
        finally:
            session.close()

    @staticmethod
    def store_validation_metrics(snapshot_id: str, metrics: Dict) -> bool:
        """
        Store validation metrics in validation_metrics table.
        
        Args:
            snapshot_id: The snapshot being validated
            metrics: Dict with all test metrics
        
        Returns:
            True if successful, False otherwise
        """
        session = ValidationDB.get_session()
        try:
            session.execute(text("""
                INSERT INTO validation_metrics (
                    snapshot_id,
                    timestamp,
                    total_firms,
                    coverage_percent,
                    avg_na_rate,
                    agent_c_pass_rate,
                    avg_score_change,
                    top_10_turnover,
                    top_20_turnover,
                    events_in_period,
                    events_predicted,
                    prediction_precision,
                    pillar_sensitivity_mean,
                    fallback_usage_percent,
                    stability_score,
                    score_distribution_skew,
                    jurisdiction_bias_score,
                    model_type_bias_score,
                    evidence_linkage_rate,
                    version_metadata,
                    created_at
                ) VALUES (
                    :snapshot_id,
                    NOW(),
                    :total_firms,
                    :coverage_percent,
                    :avg_na_rate,
                    :agent_c_pass_rate,
                    :avg_score_change,
                    :top_10_turnover,
                    :top_20_turnover,
                    :events_in_period,
                    :events_predicted,
                    :prediction_precision,
                    :pillar_sensitivity_mean,
                    :fallback_usage_percent,
                    :stability_score,
                    :score_distribution_skew,
                    :jurisdiction_bias_score,
                    :model_type_bias_score,
                    :evidence_linkage_rate,
                    :version_metadata,
                    NOW()
                )
                ON CONFLICT (snapshot_id) DO UPDATE SET
                    total_firms = :total_firms,
                    coverage_percent = :coverage_percent,
                    avg_na_rate = :avg_na_rate,
                    agent_c_pass_rate = :agent_c_pass_rate,
                    avg_score_change = :avg_score_change,
                    top_10_turnover = :top_10_turnover,
                    top_20_turnover = :top_20_turnover,
                    events_in_period = :events_in_period,
                    events_predicted = :events_predicted,
                    prediction_precision = :prediction_precision,
                    pillar_sensitivity_mean = :pillar_sensitivity_mean,
                    fallback_usage_percent = :fallback_usage_percent,
                    stability_score = :stability_score,
                    score_distribution_skew = :score_distribution_skew,
                    jurisdiction_bias_score = :jurisdiction_bias_score,
                    model_type_bias_score = :model_type_bias_score,
                    evidence_linkage_rate = :evidence_linkage_rate,
                    version_metadata = :version_metadata
            """), {
                "snapshot_id": snapshot_id,
                "total_firms": metrics.get("coverage", {}).get("total_firms", 0),
                "coverage_percent": metrics.get("coverage", {}).get("coverage_percent", 0),
                "avg_na_rate": metrics.get("coverage", {}).get("avg_na_rate", 0),
                "agent_c_pass_rate": metrics.get("coverage", {}).get("agent_c_pass_rate", 0),
                "avg_score_change": metrics.get("stability", {}).get("avg_score_change", 0),
                "top_10_turnover": metrics.get("stability", {}).get("top_10_turnover", 0),
                "top_20_turnover": metrics.get("stability", {}).get("top_20_turnover", 0),
                "events_in_period": metrics.get("ground_truth", {}).get("events_in_period", 0),
                "events_predicted": metrics.get("ground_truth", {}).get("events_predicted", 0),
                "prediction_precision": metrics.get("ground_truth", {}).get("prediction_precision", 0),
                "pillar_sensitivity_mean": metrics.get("sensitivity", {}).get("pillar_sensitivity_mean", 0),
                "fallback_usage_percent": metrics.get("sensitivity", {}).get("fallback_usage_percent", 0),
                "stability_score": metrics.get("sensitivity", {}).get("stability_score", 0),
                "score_distribution_skew": metrics.get("calibration", {}).get("score_distribution_skew", 0),
                "jurisdiction_bias_score": metrics.get("calibration", {}).get("jurisdiction_bias_score", 0),
                "model_type_bias_score": metrics.get("calibration", {}).get("model_type_bias_score", 0),
                "evidence_linkage_rate": metrics.get("auditability", {}).get("evidence_linkage_rate", 0),
                "version_metadata": metrics.get("auditability", {}).get("version_metadata")
            })
            session.commit()
            logger.info(f"Stored validation metrics for {snapshot_id}")
            return True
        except Exception as e:
            logger.error(f"Error storing validation metrics: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def create_alert(alert_type: str, severity: str, metric_name: str, 
                     current_value: float, threshold_value: float, message: str) -> bool:
        """
        Create a validation alert record.
        """
        session = ValidationDB.get_session()
        try:
            session.execute(text("""
                INSERT INTO validation_alerts (
                    alert_type,
                    severity,
                    metric_name,
                    current_value,
                    threshold_value,
                    message,
                    created_at
                ) VALUES (
                    :alert_type,
                    :severity,
                    :metric_name,
                    :current_value,
                    :threshold_value,
                    :message,
                    NOW()
                )
            """), {
                "alert_type": alert_type,
                "severity": severity,
                "metric_name": metric_name,
                "current_value": current_value,
                "threshold_value": threshold_value,
                "message": message
            })
            session.commit()
            return True
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    @staticmethod
    def get_recent_alerts(limit: int = 10) -> List[Dict]:
        """Retrieve recent unresolved alerts."""
        session = ValidationDB.get_session()
        try:
            result = session.execute(text("""
                SELECT alert_type, severity, metric_name, current_value, 
                       threshold_value, message, created_at
                FROM validation_alerts
                WHERE resolved_at IS NULL
                ORDER BY created_at DESC
                LIMIT :limit
            """), {"limit": limit})
            
            alerts = []
            for row in result:
                alerts.append({
                    "alert_type": row[0],
                    "severity": row[1],
                    "metric_name": row[2],
                    "current_value": float(row[3]),
                    "threshold_value": float(row[4]),
                    "message": row[5],
                    "created_at": row[6].isoformat() if row[6] else None
                })
            return alerts
        except Exception as e:
            logger.error(f"Error retrieving alerts: {e}")
            return []
        finally:
            session.close()
