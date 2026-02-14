from __future__ import annotations

from prefect import flow

from gpti_bot.agents.adaptive_enrichment_agent import run_targeted_enrichment


@flow(name="adaptive-enrichment", log_prints=True)
def adaptive_enrichment_flow(
    limit: int = 60,
    enable_js: bool = True,
    enable_pdf: bool = True,
    max_urls: int = 10,
    timeout_s: int = 8,
):
    """Run adaptive enrichment on firms missing rules/pricing fields."""
    result = run_targeted_enrichment(
        limit=limit,
        enable_js=enable_js,
        enable_pdf=enable_pdf,
        max_urls=max_urls,
        timeout_s=timeout_s,
    )
    print("[adaptive-enrichment]", result)
    return result


if __name__ == "__main__":
    adaptive_enrichment_flow()
