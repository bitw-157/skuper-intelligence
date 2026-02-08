"""Proactive Rebalancer Orchestrator (Type B)"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List

import psycopg
from langchain_core.messages import HumanMessage

from .agent_proactive import create_proactive_agent, format_sku_problem
from .config import CURRENT_WEEK_START, DB_CONFIG


class ProactiveOrchestrator:
    """Orchestrates proactive rebalancing for SKUs with projected stockouts in weeks 2-4."""

    def __init__(self, filter_product_family: str = None, filter_location: str = None):
        """Initialize orchestrator with optional filters."""
        self.filter_product_family = filter_product_family
        self.filter_location = filter_location
        self._executor = ThreadPoolExecutor(max_workers=10)

    async def run(self) -> Dict[str, Any]:
        """Main orchestration loop for parallel SKU processing."""
        print("=" * 80)
        print("SKUPER INTELLIGENCE - PROACTIVE REBALANCER ORCHESTRATOR")
        print(f"Analysis Date: {CURRENT_WEEK_START}")
        print("=" * 80)
        print()

        # Step 1: Get projected stockouts (weeks 2-4 only)
        print("Step 1: Querying projected stockouts (weeks 2-4)...")
        projected_stockouts = self._get_projected_stockouts()
        print(f"Found {len(projected_stockouts)} projected stockout records")
        print()

        if not projected_stockouts:
            print("No projected stockouts detected. All locations well-stocked!")
            return {
                "status": "success",
                "skus_processed": 0,
                "recommendations": [],
                "escalations": [],
                "summary": "No proactive interventions needed",
            }

        # Step 2: Group by SKU
        print("Step 2: Grouping projected stockouts by SKU...")
        skus_to_process = self._group_by_sku(projected_stockouts)
        print(f"Identified {len(skus_to_process)} unique SKUs with projected stockouts")
        print()

        # Step 3: Calculate priority for each SKU
        print("Step 3: Calculating priority scores...")
        prioritized_skus = self._prioritize_skus(skus_to_process)
        print()
        print("Priority Queue:")
        print("-" * 80)
        for idx, sku_problem in enumerate(prioritized_skus, 1):
            print(
                f"{idx}. {sku_problem['sku_id']} "
                f"({sku_problem['product_family']}) "
                f"- Priority: {sku_problem['priority_score']:.2f} "
                f"- Locations: {len(sku_problem['locations'])} "
                f"- Earliest Week: {sku_problem['earliest_week']}"
            )
        print("-" * 80)
        print()

        # Step 4: Process SKUs in parallel
        print(f"Step 4: Processing {len(prioritized_skus)} SKUs in parallel...")
        print("=" * 80)

        # Create tasks for parallel execution
        tasks = [
            self._process_single_sku(idx, sku_problem, len(prioritized_skus))
            for idx, sku_problem in enumerate(prioritized_skus, 1)
        ]

        # Run all SKUs concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        all_recommendations = []
        all_escalations = []

        for idx, result in enumerate(results, 1):
            if isinstance(result, Exception):
                sku_id = prioritized_skus[idx - 1]["sku_id"]
                logging.error(f"{sku_id}: Processing failed: {result}")
                all_escalations.append(
                    {
                        "summary": f"Processing failed for {sku_id}",
                        "reasons_no_solution": [str(result)],
                    }
                )
            elif result:
                if result.get("recommendations"):
                    all_recommendations.extend(result["recommendations"])
                if result.get("escalations"):
                    all_escalations.extend(result["escalations"])

        print()
        print("=" * 80)
        print(f"Processed {len(prioritized_skus)} SKUs")
        print(f"Generated {len(all_recommendations)} recommendations")
        print(f"Escalated {len(all_escalations)} SKU(s) for review")
        print("=" * 80)

        return {
            "status": "success",
            "skus_processed": len(prioritized_skus),
            "recommendations": all_recommendations,
            "escalations": all_escalations,
            "summary": f"Processed {len(prioritized_skus)} SKUs, generated {len(all_recommendations)} proactive recommendations",
        }

    def _get_projected_stockouts(self) -> List[Dict[str, Any]]:
        """
        Query projection_calcs_4w table for stockouts in weeks 2-4

        Returns:
            List of projected stockout records
        """
        # Parse CURRENT_WEEK_START if it's a string
        if isinstance(CURRENT_WEEK_START, str):
            current_week = datetime.fromisoformat(CURRENT_WEEK_START)
        else:
            current_week = CURRENT_WEEK_START

        # Calculate week boundaries
        week_2_start = current_week + timedelta(weeks=2)
        week_4_end = current_week + timedelta(weeks=5)  # End of week 4

        # Convert to strings for query
        week_2_start_str = week_2_start.strftime("%Y-%m-%d")
        week_4_end_str = week_4_end.strftime("%Y-%m-%d")

        query = """
            SELECT 
                pc.location_id,
                pc.sku_id,
                pc.week_start_date,
                pc.end_inv_qty as projected_inventory,
                pc.demand_fcst_qty as forecasted_demand,
                pc.safety_stock_qty as safety_stock_level,
                pc.projected_stockout_flag as stockout_risk_flag,
                p.product_family,
                p.temp_class as temperature_class,
                p.unit_cost_usd as unit_cost,
                l.priority_tier,
                df.forecast_confidence
            FROM projection_calcs_4w pc
            JOIN products p ON pc.sku_id = p.sku_id
            JOIN locations l ON pc.location_id = l.location_id
            LEFT JOIN demand_forecast_4w df 
                ON pc.sku_id = df.sku_id 
                AND pc.location_id = df.location_id
                AND pc.week_start_date = df.week_start_date
            WHERE pc.projected_stockout_flag::integer = 1
                AND pc.week_start_date >= %s
                AND pc.week_start_date < %s
        """

        params = [week_2_start_str, week_4_end_str]

        # Add filters
        if self.filter_product_family:
            query += " AND p.product_family = %s"
            params.append(self.filter_product_family)

        if self.filter_location:
            query += " AND pc.location_id = %s"
            params.append(self.filter_location)

        query += " ORDER BY pc.week_start_date, l.priority_tier, pc.sku_id"

        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]

        return results

    def _group_by_sku(
        self, projected_stockouts: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Group projected stockouts by SKU

        Args:
            projected_stockouts: List of projected stockout records

        Returns:
            Dictionary mapping sku_id to aggregated problem data
        """
        skus = {}

        for record in projected_stockouts:
            sku_id = record["sku_id"]

            if sku_id not in skus:
                skus[sku_id] = {
                    "sku_id": sku_id,
                    "product_family": record["product_family"],
                    "temperature_class": record["temperature_class"],
                    "unit_cost": float(record["unit_cost"])
                    if record["unit_cost"]
                    else 0,
                    "locations": [],
                    "total_shortage": 0,
                    "earliest_week": record["week_start_date"],
                }

            # Add location details
            shortage = (
                abs(float(record["projected_inventory"]))
                if record["projected_inventory"]
                and float(record["projected_inventory"]) < 0
                else 0
            )

            skus[sku_id]["locations"].append(
                {
                    "location_id": record["location_id"],
                    "priority_tier": record["priority_tier"],
                    "week_start_date": record["week_start_date"],
                    "projected_shortage": shortage,
                    "forecasted_demand": float(record["forecasted_demand"])
                    if record["forecasted_demand"]
                    else 0,
                    "safety_stock_level": float(record["safety_stock_level"])
                    if record["safety_stock_level"]
                    else 0,
                    "forecast_confidence": float(record["forecast_confidence"])
                    if record["forecast_confidence"]
                    else 0.7,
                }
            )

            skus[sku_id]["total_shortage"] += shortage

            # Track earliest week
            if record["week_start_date"] < skus[sku_id]["earliest_week"]:
                skus[sku_id]["earliest_week"] = record["week_start_date"]

        return skus

    def _prioritize_skus(self, skus: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prioritize SKUs for processing

        Priority factors:
        - Time urgency (earlier weeks = higher priority)
        - Severity (total shortage magnitude)
        - Location criticality (priority_tier)
        - Product value (unit_cost)

        Args:
            skus: Dictionary of SKU problems

        Returns:
            Sorted list of SKU problems (highest priority first)
        """
        # Parse CURRENT_WEEK_START if it's a string
        if isinstance(CURRENT_WEEK_START, str):
            current_week = datetime.fromisoformat(CURRENT_WEEK_START)
        else:
            current_week = CURRENT_WEEK_START

        sku_list = list(skus.values())

        for sku in sku_list:
            # Parse earliest_week if it's a string
            earliest_week = sku["earliest_week"]
            if isinstance(earliest_week, str):
                earliest_week = datetime.fromisoformat(earliest_week)

            # Calculate time urgency (weeks until earliest stockout)
            weeks_until = (earliest_week - current_week).days / 7
            time_urgency = max(0, 5 - weeks_until)  # Higher for sooner stockouts

            # Location criticality (average priority tier)
            avg_priority = sum(loc["priority_tier"] for loc in sku["locations"]) / len(
                sku["locations"]
            )
            criticality = 4 - avg_priority  # Lower tier number = higher criticality

            # Shortage severity
            severity = sku["total_shortage"] / 100  # Normalize

            # Product value
            value = sku["unit_cost"] / 10  # Normalize

            # Combined score
            priority_score = (
                time_urgency * 3.0  # Time is important but not as critical as Type A
                + severity * 2.5
                + criticality * 2.0
                + value * 1.5
            )

            sku["priority_score"] = priority_score

        # Sort by priority (highest first)
        return sorted(sku_list, key=lambda x: x["priority_score"], reverse=True)

    async def _process_single_sku(
        self, idx: int, sku_problem: Dict[str, Any], total: int
    ) -> Dict[str, Any]:
        """
        Process a single SKU through the proactive agent (async wrapper).

        Args:
            idx: SKU index in priority queue
            sku_problem: SKU problem data
            total: Total number of SKUs being processed

        Returns:
            Dictionary with recommendations or escalations
        """
        sku_id = sku_problem["sku_id"]
        product_family = sku_problem["product_family"]
        location_count = len(sku_problem["locations"])

        try:
            # Run synchronous agent processing in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor, self._process_sku_sync, sku_problem
            )

            # Log SKU-level outcome
            if result.get("recommendations"):
                rec_count = len(result["recommendations"])
                rec_types = {}
                for rec in result["recommendations"]:
                    rec_type = rec.get("recommendation_type", "UNKNOWN")
                    rec_types[rec_type] = rec_types.get(rec_type, 0) + 1

                type_summary = ", ".join(
                    [f"{count} {rtype}" for rtype, count in rec_types.items()]
                )
                logging.info(
                    f"✓ {sku_id} ({product_family}): {rec_count} recommendation(s) - {type_summary}"
                )

            if result.get("escalations"):
                escalation_summary = result["escalations"][0].get(
                    "summary", "Unknown reason"
                )[:80]
                logging.info(
                    f"⚠ {sku_id} ({product_family}): ESCALATION - {escalation_summary}"
                )

            return result

        except Exception as e:
            logging.exception(f"{sku_id}: Agent processing failed", exc_info=e)
            return {
                "recommendations": [],
                "escalations": [
                    {
                        "summary": f"Processing failed for {sku_id}",
                        "reasons_no_solution": [str(e)],
                    }
                ],
            }

    def _process_sku_sync(self, sku_problem: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single SKU through the proactive agent

        Args:
            sku_problem: SKU problem data with locations

        Returns:
            Dictionary with recommendations or escalations
        """
        sku_id = sku_problem["sku_id"]

        # Get incoming supply orders for this SKU
        incoming_supply = self._get_incoming_supply_orders(sku_id)

        # Get current inventory snapshot
        inventory_snapshot = self._get_current_inventory(sku_id)

        # Build agent state as dictionary (TypedDict compatible)
        initial_state = {
            "sku_id": sku_id,
            "product_details": {
                "product_family": sku_problem["product_family"],
                "temperature_class": sku_problem["temperature_class"],
                "unit_cost": sku_problem["unit_cost"],
            },
            "projected_stockout_locations": sku_problem["locations"],
            "incoming_supply_orders": incoming_supply,
            "current_inventory_snapshot": inventory_snapshot,
            "reasoning_trace": [],
            "tools_called": [],
            "iteration_count": 0,
            "messages": [],  # Empty messages list - agent will populate
        }

        # Format initial problem description for the agent
        initial_prompt = format_sku_problem(initial_state)

        # Add initial message to state
        initial_state["messages"] = [HumanMessage(content=initial_prompt)]

        # Create agent and invoke
        agent = create_proactive_agent()
        final_state = agent.invoke(initial_state)

        # Extract recommendations from final message
        recommendations = self._extract_recommendations(final_state)

        return recommendations

    def _get_incoming_supply_orders(self, sku_id: str) -> List[Dict[str, Any]]:
        """
        Get incoming supply orders for SKU (weeks 2-4)

        Args:
            sku_id: SKU identifier

        Returns:
            List of supply order records
        """
        # Parse CURRENT_WEEK_START if it's a string
        if isinstance(CURRENT_WEEK_START, str):
            current_week = datetime.fromisoformat(CURRENT_WEEK_START)
        else:
            current_week = CURRENT_WEEK_START

        week_2_start = current_week + timedelta(weeks=2)
        week_4_end = current_week + timedelta(weeks=5)

        # Convert to strings for query
        week_2_start_str = week_2_start.strftime("%Y-%m-%d")
        week_4_end_str = week_4_end.strftime("%Y-%m-%d")

        query = """
            SELECT 
                supply_order_id,
                sku_id,
                destination_location_id,
                qty as order_quantity,
                arrival_week_start,
                status,
                reroutable_flag,
                supply_type as source_type
            FROM supply_plan
            WHERE sku_id = %s
                AND arrival_week_start >= %s
                AND arrival_week_start < %s
                AND status IN ('Planned', 'Firm')
            ORDER BY arrival_week_start
        """

        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query, [sku_id, week_2_start_str, week_4_end_str])
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]

        return results

    def _get_current_inventory(self, sku_id: str) -> List[Dict[str, Any]]:
        """
        Get current inventory levels across all locations for SKU

        Args:
            sku_id: SKU identifier

        Returns:
            List of inventory records
        """
        query = """
            SELECT 
                ib.location_id,
                SUM(ib.available_qty) as total_inventory,
                sp.safety_stock_qty as safety_stock
            FROM inventory_batches ib
            LEFT JOIN safety_stock_parameters sp 
                ON ib.sku_id = sp.sku_id 
                AND ib.location_id = sp.location_id
            WHERE ib.sku_id = %s
                AND ib.expiry_date::date > CURRENT_DATE
            GROUP BY ib.location_id, sp.safety_stock_qty
            ORDER BY total_inventory DESC
        """

        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(query, [sku_id])
                columns = [desc[0] for desc in cur.description]
                results = [dict(zip(columns, row)) for row in cur.fetchall()]

        return results

    def _extract_recommendations(self, final_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured recommendations from agent's output

        Args:
            final_state: Final agent state after processing (dict from create_agent)

        Returns:
            Dictionary with recommendations and escalations
        """
        recommendations = []
        escalations = []

        # First check for structured_response (from response_format=ProactiveAgentOutput)
        structured_output = final_state.get("structured_response")

        if structured_output:
            # Handle Pydantic model or dict
            output_type = (
                structured_output.output_type
                if hasattr(structured_output, "output_type")
                else structured_output.get("output_type")
            )

            # Extract summary
            summary = (
                structured_output.summary
                if hasattr(structured_output, "summary")
                else structured_output.get("summary", "")
            )

            sku_id = final_state.get("sku_id", "Unknown")

            # Process per-location results
            location_results = (
                structured_output.location_results
                if hasattr(structured_output, "location_results")
                else structured_output.get("location_results", [])
            )

            resolved_count = 0
            unresolved_count = 0

            for loc_result in location_results:
                # Handle Pydantic model or dict
                if hasattr(loc_result, "status"):
                    status = loc_result.status
                    location_id = loc_result.location_id
                    projected_shortage_qty = loc_result.projected_shortage_qty
                    stockout_week = loc_result.stockout_week
                    supply_reroute = loc_result.supply_reroute
                    preemptive_transfer = loc_result.preemptive_transfer
                    reason_unresolved = loc_result.reason_unresolved
                else:
                    status = loc_result.get("status")
                    location_id = loc_result.get("location_id")
                    projected_shortage_qty = loc_result.get("projected_shortage_qty")
                    stockout_week = loc_result.get("stockout_week")
                    supply_reroute = loc_result.get("supply_reroute")
                    preemptive_transfer = loc_result.get("preemptive_transfer")
                    reason_unresolved = loc_result.get("reason_unresolved")

                if status == "RESOLVED":
                    resolved_count += 1

                    # Store supply reroute recommendation
                    if supply_reroute:
                        if hasattr(supply_reroute, "supply_order_id"):
                            rec_dict = {
                                "supply_order_id": supply_reroute.supply_order_id,
                                "original_destination": supply_reroute.original_destination,
                                "new_destination": supply_reroute.new_destination,
                                "reasoning": supply_reroute.reasoning,
                                "cost_delta": supply_reroute.cost_delta,
                                "confidence_level": supply_reroute.confidence_level,
                            }
                        else:
                            rec_dict = supply_reroute
                        rec_dict["recommendation_type"] = "SUPPLY_REROUTE"
                        rec_dict["location_id"] = location_id
                        rec_dict["stockout_week"] = stockout_week
                        recommendations.append(rec_dict)

                    # Store preemptive transfer recommendation
                    elif preemptive_transfer:
                        if hasattr(preemptive_transfer, "from_location"):
                            rec_dict = {
                                "from_location": preemptive_transfer.from_location,
                                "to_location": preemptive_transfer.to_location,
                                "quantity": preemptive_transfer.quantity,
                                "transport_mode": preemptive_transfer.transport_mode,
                                "reasoning": preemptive_transfer.reasoning,
                                "estimated_cost": preemptive_transfer.estimated_cost,
                                "confidence_level": preemptive_transfer.confidence_level,
                            }
                        else:
                            rec_dict = preemptive_transfer
                        rec_dict["recommendation_type"] = "PREEMPTIVE_TRANSFER"
                        rec_dict["location_id"] = location_id
                        rec_dict["stockout_week"] = stockout_week
                        recommendations.append(rec_dict)

                elif status == "UNRESOLVED":
                    unresolved_count += 1

            # Log per-SKU summary
            total_locations = resolved_count + unresolved_count
            if resolved_count > 0:
                logging.info(
                    f"{sku_id}: {summary} ({resolved_count}/{total_locations} locations)"
                )

            # Handle complete escalation (no locations resolved)
            if output_type == "ESCALATION":
                escalation = (
                    structured_output.escalation
                    if hasattr(structured_output, "escalation")
                    else structured_output.get("escalation")
                )
                if escalation:
                    if hasattr(escalation, "dict"):
                        escalations.append(escalation.dict())
                    else:
                        escalations.append(escalation)

            return {"recommendations": recommendations, "escalations": escalations}

        # Fallback: Parse from messages if structured_response not available
        messages = final_state.get("messages", [])
        if not messages:
            return {"recommendations": [], "escalations": []}

        # Fallback: Parse from messages if structured_response not available
        messages = final_state.get("messages", [])
        if not messages:
            return {"recommendations": [], "escalations": []}

        last_message = messages[-1]
        content = (
            last_message.content
            if hasattr(last_message, "content")
            else str(last_message)
        )

        # Try to parse JSON from content
        try:
            # Look for JSON in the content
            if isinstance(content, str):
                # Strip markdown code blocks if present
                text = content.strip()
                if text.startswith("```json"):
                    text = text[7:]
                elif text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

                # Parse JSON
                result = json.loads(text)

                output_type = result.get("output_type", "")

                if output_type == "SUPPLY_REROUTE":
                    supply_reroutes = result.get("supply_reroutes", [])
                    for reroute in supply_reroutes:
                        reroute["recommendation_type"] = "SUPPLY_REROUTE"
                        recommendations.append(reroute)
                elif output_type == "PREEMPTIVE_TRANSFER":
                    preemptive_transfers = result.get("preemptive_transfers", [])
                    for transfer in preemptive_transfers:
                        transfer["recommendation_type"] = "PREEMPTIVE_TRANSFER"
                        recommendations.append(transfer)
                elif output_type == "ESCALATION":
                    escalations.append(result.get("escalation", {}))
        except (json.JSONDecodeError, AttributeError) as e:
            print(f"  [WARN] Could not parse agent output: {e}")
            # Create escalation for unparseable output
            sku_id = final_state.get("sku_id", "Unknown")
            escalations.append(
                {
                    "summary": f"Agent processing incomplete for {sku_id}",
                    "reasons_no_solution": ["Agent output could not be parsed"],
                    "raw_output": str(content)[:200],
                }
            )

        return {"recommendations": recommendations, "escalations": escalations}
