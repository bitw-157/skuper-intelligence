"""Main entry point for Skuper Intelligence"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from src import ProactiveOrchestrator, StockoutOrchestrator

log_filename = f"skuper_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

file_handler = logging.FileHandler(log_filename, mode="w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def print_header(title, subtitle, agent_type):
    """Print formatted header"""
    logger.info("")
    logger.info("=" * 80)
    logger.info(f" {title}")
    logger.info(f" {subtitle}")
    logger.info(f" {agent_type}")
    logger.info("=" * 80)
    logger.info("")


def run_emergency_agent(args):
    """Run Emergency Stockout Resolver for current week stockouts"""
    try:
        print_header(
            "SKUPER INTELLIGENCE",
            "Agentic Inventory Rebalancing System",
            "Emergency Stockout Resolver (Type A Agent)",
        )

        if args.filter:
            logger.info(f"Filtering for: {args.filter} products")
            logger.info("")

        orchestrator = StockoutOrchestrator()
        results = asyncio.run(orchestrator.run(criticality_filter=args.filter))

    except Exception as e:
        logging.exception("Emergency agent execution failed")
        logger.error("")
        logger.error(f"ERROR: {str(e)}")
        logger.error("")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def run_proactive_agent(args):
    """Run Proactive Rebalancer for weeks 2-4 projected stockouts"""
    try:
        print_header(
            "SKUPER INTELLIGENCE",
            "Agentic Inventory Rebalancing System",
            "Proactive Rebalancer (Type B Agent)",
        )

        if args.filter:
            logger.info(f"Filtering for: {args.filter} products")
            logger.info("")

        orchestrator = ProactiveOrchestrator(filter_product_family=args.filter)
        results = asyncio.run(orchestrator.run())

    except Exception as e:
        logging.exception("Proactive agent execution failed")
        logger.error("")
        logger.error(f"ERROR: {str(e)}")
        logger.error("")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def display_emergency_results(results):
    """Display results from Emergency Stockout Resolver"""
    logger.info("")
    logger.info("=" * 80)
    logger.info(" RESULTS")
    logger.info("=" * 80)
    logger.info("")

    transfers = results.get("transfers", [])
    priority_analyses = results.get("priority_analyses", [])

    # Display transfer recommendations
    if transfers:
        logger.info(f"✓ Generated {len(transfers)} transfer recommendation(s)")
        logger.info("")

        for idx, rec in enumerate(transfers, 1):
            logger.info(f"Transfer #{idx}:")
            logger.info(f"  SKU:       {rec['sku_id']}")
            logger.info(f"  Quantity:  {rec['quantity']} units")
            logger.info(f"  From:      {rec['from_location']}")
            logger.info(f"  To:        {rec['to_location']}")
            logger.info(f"  Cost:      ${rec['estimated_cost']:.2f}")
            logger.info(f"  Reasoning: {rec['reasoning']}")
            logger.info("")

    # Display priority analyses
    if priority_analyses:
        logger.info(
            f"⚠ Priority Analyses for {len(priority_analyses)} SKU(s) without surplus:"
        )
        logger.info("")

        for idx, analysis in enumerate(priority_analyses, 1):
            urgency = analysis["urgency_level"]
            urgency_icon = {
                "CRITICAL": "🔴",
                "HIGH": "🟠",
                "MEDIUM": "🟡",
                "LOW": "🟢",
            }.get(urgency, "⚪")

            logger.info(
                f"{urgency_icon} Analysis #{idx}: {analysis['sku_id']} - {analysis['product_family']}"
            )
            logger.info(f"  Urgency Level:      {urgency}")
            logger.info(
                f"  Priority Location:  {analysis['highest_priority_location']}"
            )
            logger.info(f"  Recommended Action: {analysis['recommended_action']}")
            logger.info(f"  Summary:            {analysis['summary']}")
            logger.info("")

    if not transfers and not priority_analyses:
        logger.info(
            "✓ No stockouts detected or agent did not generate recommendations."
        )

    logger.info("")
    logger.info("=" * 80)
    logger.info("System execution complete.")
    logger.info("=" * 80)
    logger.info(f"Log file: {log_filename}")
    logger.info("")


def display_proactive_results(results):
    """Display results from Proactive Rebalancer"""
    logger.info("")
    logger.info("=" * 80)
    logger.info(" RESULTS")
    logger.info("=" * 80)
    logger.info("")

    recommendations = results.get("recommendations", [])
    escalations = results.get("escalations", [])

    # Display recommendations
    if recommendations:
        logger.info(f"✓ Generated {len(recommendations)} proactive recommendation(s)")
        logger.info("")

        for idx, rec in enumerate(recommendations, 1):
            rec_type = rec.get("recommendation_type", "UNKNOWN")

            if rec_type == "SUPPLY_REROUTE":
                logger.info(f"Supply Reroute #{idx}:")
                logger.info(f"  Supply Order:  {rec['supply_order_id']}")
                logger.info(f"  Original Dest: {rec['original_destination']}")
                logger.info(f"  New Dest:      {rec['new_destination']}")
                logger.info(f"  Cost Delta:    ${rec['cost_delta']:.2f}")
                logger.info(f"  Confidence:    {rec['confidence_level']}")
                logger.info(f"  Reasoning:     {rec['reasoning']}")
                logger.info("")

            elif rec_type == "PREEMPTIVE_TRANSFER":
                logger.info(f"Preemptive Transfer #{idx}:")
                logger.info(f"  Quantity:      {rec['quantity']} units")
                logger.info(f"  From:          {rec['from_location']}")
                logger.info(f"  To:            {rec['to_location']}")
                logger.info(f"  Mode:          {rec['transport_mode']}")
                logger.info(f"  Cost:          ${rec['estimated_cost']:.2f}")
                logger.info(f"  Confidence:    {rec['confidence_level']}")
                logger.info(f"  Reasoning:     {rec['reasoning']}")
                logger.info("")

    # Display escalations
    if escalations:
        logger.info(f"⚠ {len(escalations)} SKU(s) escalated for review:")
        logger.info("")

        for idx, esc in enumerate(escalations, 1):
            logger.info(f"Escalation #{idx}:")
            logger.info(f"  Summary: {esc['summary']}")
            if "highest_priority_location" in esc:
                logger.info(f"  Priority Location: {esc['highest_priority_location']}")
            if "projected_stockout_week" in esc:
                logger.info(f"  Stockout Week: {esc['projected_stockout_week']}")
            if "recommended_action" in esc:
                logger.info(f"  Recommended Action: {esc['recommended_action']}")

            reasons = esc.get("reasons_no_solution", [])
            if reasons:
                logger.info("  Reasons:")
                for r in reasons:
                    logger.info(f"    • {r}")

            logger.info("")

    if not recommendations and not escalations:
        logger.info("✓ No projected stockouts or no recommendations generated.")

    logger.info("")
    logger.info("=" * 80)
    logger.info("System execution complete.")
    logger.info("=" * 80)
    logger.info(f"Log file: {log_filename}")
    logger.info("")


def main():
    """Main entry point with subcommand pattern"""
    parser = argparse.ArgumentParser(
        description="Skuper Intelligence - Agentic Inventory Rebalancing System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py emergency
  python main.py emergency --filter Oncology
  python main.py proactive
  python main.py proactive --filter Oncology
        """,
    )

    subparsers = parser.add_subparsers(
        title="Agent Types",
        description="Choose which agent to run",
        dest="agent_type",
        required=True,
    )

    # Emergency agent subcommand
    emergency_parser = subparsers.add_parser(
        "emergency",
        help="Run Emergency Stockout Resolver (Type A) for current week stockouts",
        description="Handles immediate stockouts (weeks 0-1) through emergency inventory transfers",
    )
    emergency_parser.add_argument(
        "--filter",
        type=str,
        help="Filter by product family (e.g., Oncology, Cardiology)",
        default=None,
    )
    emergency_parser.set_defaults(func=run_emergency_agent)

    # Proactive agent subcommand
    proactive_parser = subparsers.add_parser(
        "proactive",
        help="Run Proactive Rebalancer (Type B) for projected stockouts",
        description="Prevents future stockouts (weeks 2-4) through supply rerouting and preemptive transfers",
    )
    proactive_parser.add_argument(
        "--filter",
        type=str,
        help="Filter by product family (e.g., Oncology, Cardiology)",
        default=None,
    )
    proactive_parser.set_defaults(func=run_proactive_agent)

    # Parse arguments and run selected agent
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
