"""Stockout Orchestrator - Manages per-SKU processing with priority queue"""

import json
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .agent import create_emergency_workflow
from .models import EmergencyStockoutState, SKUProblem, StockoutRecord
from .tools import query_current_stockouts


class StockoutOrchestrator:
    """
    Orchestrates emergency stockout resolution across multiple SKUs
    Handles prioritization, resource tracking, and sequential processing
    """

    def __init__(self):
        self.inventory_state = {}  # Track claimed inventory
        self.all_recommendations = []
        self.priority_analyses = []  # Track priority analyses for SKUs without surplus

    def run(self, criticality_filter: str = None) -> List[Dict[str, Any]]:
        """
        Main orchestration flow:
        1. Get all stockouts
        2. Group by SKU
        3. Calculate priorities
        4. Process sequentially

        Args:
            criticality_filter: Optional filter for product families

        Returns:
            List of all recommendations generated
        """
        print("=" * 80)
        print("SKUPER INTELLIGENCE - EMERGENCY STOCKOUT ORCHESTRATOR")
        print("=" * 80)
        print()

        # Step 1: Get all current stockouts
        print("Step 1: Querying current stockouts...")
        stockouts = self._get_all_stockouts(criticality_filter)
        print(f"Found {len(stockouts)} stockout records")
        print()

        if not stockouts:
            print("No stockouts detected. System is healthy!")
            return {"transfers": [], "priority_analyses": []}

        # Step 2: Group by SKU
        print("Step 2: Grouping stockouts by SKU...")
        stockouts_by_sku = self._group_by_sku(stockouts)
        print(f"Identified {len(stockouts_by_sku)} unique SKUs with stockouts")
        print()

        # Step 3: Calculate priority for each SKU
        print("Step 3: Calculating priority scores...")
        prioritized_skus = self._prioritize_skus(stockouts_by_sku)
        print()
        print("Priority Queue:")
        print("-" * 80)
        for idx, sku_problem in enumerate(prioritized_skus, 1):
            print(
                f"{idx}. {sku_problem['sku_id']} "
                f"({sku_problem['product_info']['product_family']}) "
                f"- Priority: {sku_problem['priority_score']:.2f} "
                f"- Locations: {len(sku_problem['stockouts'])}"
            )
        print("-" * 80)
        print()

        # Step 4: Initialize inventory state
        print("Step 4: Initializing inventory state...")
        self._initialize_inventory_state()
        print(f"Tracking {len(self.inventory_state)} SKU-location combinations")
        print()

        # Step 5: Process each SKU sequentially
        print("Step 5: Processing SKUs sequentially...")
        print("=" * 80)

        for idx, sku_problem in enumerate(prioritized_skus, 1):
            # Get available inventory for THIS SKU (updated with previous claims)
            available_inventory = self._get_available_inventory_for_sku(
                sku_problem["sku_id"]
            )

            # Create SKU problem input
            sku_input = {
                "sku_id": sku_problem["sku_id"],
                "product_details": sku_problem["product_info"],
                "stockout_locations": sku_problem["stockouts"],
                "available_inventory": available_inventory,
            }

            # Create agent workflow and process this SKU
            try:
                workflow = create_emergency_workflow()

                # Convert dict stockouts to Pydantic StockoutRecord objects
                stockout_records = [
                    StockoutRecord(**stockout)
                    for stockout in sku_input["stockout_locations"]
                ]

                # Convert sku_input to EmergencyStockoutState
                initial_state = EmergencyStockoutState(
                    sku_id=sku_input["sku_id"],
                    product_details=sku_input["product_details"],
                    stockout_locations=stockout_records,
                    available_inventory=sku_input["available_inventory"],
                )

                # Invoke the workflow
                result = workflow.invoke(initial_state)

                # Parse structured output from agent
                agent_output = self._parse_agent_output(result)

                # Debug: Log what we got from agent
                if agent_output:
                    logging.info(
                        f"Agent returned output_type: {agent_output.get('output_type')}"
                    )
                else:
                    # Check if this is just because of tool calls or actual parse failure
                    messages = result.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        content = (
                            last_msg.content if hasattr(last_msg, "content") else None
                        )

                        # Only log as warning if there's actual text content that failed to parse
                        if content and isinstance(content, list):
                            has_text = any(
                                isinstance(item, dict) and item.get("type") == "text"
                                for item in content
                            )
                            if has_text:
                                logging.warning(
                                    f"Failed to parse agent output for SKU {sku_problem['sku_id']}"
                                )
                                logging.info(f"Raw agent response: {content}")
                        elif content:
                            logging.warning(
                                f"Failed to parse agent output for SKU {sku_problem['sku_id']}"
                            )
                            logging.info(f"Raw agent response: {content}")

                # Process agent output and store recommendations
                if agent_output and agent_output.get("output_type") == "TRANSFER":
                    transfers = agent_output.get("transfers", [])
                    for transfer in transfers:
                        self.all_recommendations.append(
                            {
                                "sku_id": sku_problem["sku_id"],
                                "from_location": transfer["from_location"],
                                "to_location": transfer["to_location"],
                                "quantity": transfer["quantity"],
                                "reasoning": transfer["reasoning"],
                                "estimated_cost": transfer["estimated_cost"],
                            }
                        )
                elif (
                    agent_output
                    and agent_output.get("output_type") == "PRIORITY_ANALYSIS"
                ):
                    analysis = agent_output.get("priority_analysis", {})
                    self.priority_analyses.append(
                        {
                            "sku_id": sku_problem["sku_id"],
                            "product_family": sku_problem["product_info"][
                                "product_family"
                            ],
                            "summary": analysis.get("summary", ""),
                            "highest_priority_location": analysis.get(
                                "highest_priority_location", ""
                            ),
                            "urgency_level": analysis.get("urgency_level", "UNKNOWN"),
                            "recommended_action": analysis.get(
                                "recommended_action", ""
                            ),
                        }
                    )

            except Exception as e:
                logging.exception(
                    f"Agent processing failed for SKU {sku_problem['sku_id']}",
                    exc_info=e,
                )

        return {
            "transfers": self.all_recommendations,
            "priority_analyses": self.priority_analyses,
        }

    def _get_all_stockouts(
        self, criticality_filter: str = None
    ) -> List[StockoutRecord]:
        """Query database for all current stockouts"""
        result = query_current_stockouts.invoke(
            {
                "time_window": "current_week",
                "criticality_filter": criticality_filter,
                "min_severity": 0,  # Show all stockouts (negative inventory)
            }
        )

        stockouts = json.loads(result)

        if "error" in stockouts:
            raise Exception(f"Error querying stockouts: {stockouts['error']}")

        return stockouts

    def _group_by_sku(
        self, stockouts: List[StockoutRecord]
    ) -> Dict[str, List[StockoutRecord]]:
        """Group stockout records by SKU"""
        grouped = defaultdict(list)

        for stockout in stockouts:
            grouped[stockout["sku_id"]].append(stockout)

        return dict(grouped)

    def _prioritize_skus(
        self, stockouts_by_sku: Dict[str, List[StockoutRecord]]
    ) -> List[SKUProblem]:
        """
        Calculate priority score for each SKU and sort

        Priority Score = weighted sum of:
        - Product criticality (Oncology=100, Vaccines=100, Cardio=80, etc.)
        - Total shortage magnitude
        - Number of locations affected
        - Service level target
        """
        prioritized = []

        for sku_id, sku_stockouts in stockouts_by_sku.items():
            # Get product info from first stockout record
            product_info = {
                "product_family": sku_stockouts[0]["product_family"],
                "target_service_level": sku_stockouts[0]["target_service_level"],
                "temp_class": sku_stockouts[0]["temp_class"],
                "unit_cost_usd": sku_stockouts[0]["unit_cost_usd"],
            }

            # Calculate priority score
            priority_score = self._calculate_priority_score(sku_stockouts, product_info)

            prioritized.append(
                {
                    "sku_id": sku_id,
                    "priority_score": priority_score,
                    "stockouts": sku_stockouts,
                    "product_info": product_info,
                }
            )

        # Sort by priority (highest first)
        prioritized.sort(key=lambda x: x["priority_score"], reverse=True)

        return prioritized

    def _calculate_priority_score(
        self, stockouts: List[StockoutRecord], product_info: Dict[str, Any]
    ) -> float:
        """
        Calculate priority score for a SKU

        Formula:
        Priority = criticality_score * 0.5 +
                   magnitude_score * 0.2 +
                   location_score * 0.2 +
                   service_level_score * 0.1
        """
        # Criticality weight (based on product family)
        criticality_map = {
            "Oncology": 100,
            "Vaccines": 100,
            "Cardio": 80,
            "Diabetes": 70,
        }
        criticality_score = criticality_map.get(product_info["product_family"], 50)

        # Magnitude weight (total shortage across all locations)
        total_shortage = sum(
            abs(s["end_inv_qty"]) for s in stockouts if s["end_inv_qty"] < 0
        )
        magnitude_score = min(total_shortage / 10, 100)  # Cap at 100

        # Location count weight
        location_count = len(stockouts)
        location_score = location_count * 10

        # Service level weight
        service_level_score = product_info["target_service_level"] * 100

        # Weighted combination
        priority_score = (
            criticality_score * 0.5
            + magnitude_score * 0.2
            + location_score * 0.2
            + service_level_score * 0.1
        )

        return priority_score

    def _initialize_inventory_state(self):
        """
        Initialize inventory state for tracking
        Query all available inventory across all SKUs
        """
        # TODO: Query inventory_batches and safetystock_params to build initial state
        # For now, placeholder
        self.inventory_state = {}

    def _get_available_inventory_for_sku(self, sku_id: str) -> Dict[str, int]:
        """
        Get available surplus inventory for a specific SKU
        Adjusted for any previous claims

        Returns:
            Dict mapping location_id to available excess quantity
        """
        # TODO: Query database and adjust for claimed inventory
        # For now, return empty dict
        return {}

    def _update_inventory_state(self, recommendations: List[Dict[str, Any]]):
        """
        Update inventory state after agent generates recommendations
        Record which inventory has been claimed
        """
        for rec in recommendations:
            source = rec["from_location_id"]
            sku = rec["sku_id"]
            qty_claimed = rec["recommended_qty"]

            key = f"{sku}_{source}"
            if key in self.inventory_state:
                self.inventory_state[key] -= qty_claimed

            self.all_recommendations.append(rec)

    def _parse_agent_output(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse structured output from agent's final message"""
        try:
            messages = result.get("messages", [])
            if not messages:
                return None

            last_message = messages[-1]

            # Check if it's a structured output
            if hasattr(last_message, "content"):
                content = last_message.content

                # If content is already dict (structured output)
                if isinstance(content, dict):
                    return content

                # Try parsing as JSON string
                if isinstance(content, str):
                    import json

                    try:
                        return json.loads(content)
                    except (json.JSONDecodeError, ValueError):
                        return None

                # Handle list of content items (from Responses API)
                if isinstance(content, list):
                    import json
                    import re

                    # Skip if this is just tool calls without text response
                    has_text = False
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            has_text = True
                            break

                    if not has_text:
                        # This is a tool-calling response, not the final output
                        logging.debug(
                            "Skipping tool call response - waiting for final text output"
                        )
                        return None

                    # Find text content
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")

                            # Strip markdown code blocks
                            text = re.sub(r"^```json\s*", "", text, flags=re.MULTILINE)
                            text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
                            text = text.strip()

                            try:
                                return json.loads(text)
                            except (json.JSONDecodeError, ValueError) as e:
                                logging.warning(f"Failed to parse JSON from text: {e}")
                                return None

            return None
        except Exception as e:
            logging.exception("Failed to parse agent output", exc_info=e)
            return None


if __name__ == "__main__":
    # Test the orchestrator
    orchestrator = StockoutOrchestrator()
    results = orchestrator.run()

    print()
    print("Results:", results)
