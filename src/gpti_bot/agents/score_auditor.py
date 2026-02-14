from __future__ import annotations
from typing import Any, Dict, List


def audit_rules(rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Agent B institutionnel :
    - calcule un score de confiance basé sur les champs critiques
    - détecte des red flags typiques des prop firms
    - ne fait appel à aucun LLM
    """

    # -----------------------------------------------------
    # 1. Gestion des erreurs
    # -----------------------------------------------------
    if not isinstance(rules, dict):
        return {
            "status": "failed",
            "confidence": 0.0,
            "signals": {"error": "invalid_rules_format"},
        }

    if "error" in rules:
        return {
            "status": "failed",
            "confidence": 0.0,
            "signals": {"error": rules.get("error")},
        }

    # -----------------------------------------------------
    # 2. Champs requis institutionnels
    # -----------------------------------------------------
    required_fields = [
        "profit_target",
        "daily_drawdown",
        "max_drawdown",
        "payout_split",
        "min_trading_days",
    ]

    present = sum(1 for k in required_fields if rules.get(k))
    confidence = round(present / len(required_fields), 3)

    # -----------------------------------------------------
    # 3. Red flags institutionnels
    # -----------------------------------------------------
    red_flags: List[str] = []

    # --- Max Drawdown "unlimited" ---
    dd = str(rules.get("max_drawdown") or "").lower()
    if "unlimited" in dd or "no limit" in dd:
        red_flags.append("max_drawdown_unlimited_claim")

    # --- News trading marketing claims ---
    ns = str(rules.get("news_trading") or "").lower()
    notes = str(rules.get("notes") or "").lower()

    if "always allowed" in ns and "spread" in notes:
        red_flags.append("news_trading_may_be_marketing")

    # --- Profit target unrealistic ---
    pt = str(rules.get("profit_target") or "").lower()
    if any(x in pt for x in ["0%", "zero", "no target"]):
        red_flags.append("profit_target_unrealistic")

    # --- Payout split suspicious ---
    ps = str(rules.get("payout_split") or "").lower()
    if "100%" in ps or "100 %" in ps:
        red_flags.append("payout_split_marketing_claim")

    # -----------------------------------------------------
    # 4. Score final institutionnel
    # -----------------------------------------------------
    return {
        "status": "ok",
        "confidence": confidence,
        "signals": {
            "required_present": present,
            "required_total": len(required_fields),
            "red_flags": red_flags,
        },
    }