"""Stockout Orchestrator - Manages per-SKU processing with priority queue"""

import asyncio
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage

from .agent_emergency import create_emergency_agent, format_sku_problem
from .models import SKUProblem, StockoutRecord
from .tools import query_current_stockouts


class StockoutOrchestrator:
    """Orchestrates emergency stockout resolution across multiple SKUs."""

    def __init__(self):
        self.all_recommendations = []
        self.priority_analyses = []
        self._executor = ThreadPoolExecutor(max_workers=10)

    async def run(self, criticality_filter: str = None) -> List[Dict[str, Any]]:
        """Main orchestration flow: get stockouts, group by SKU, prioritize, and process."""
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

        # Step 4: Process SKUs in parallel
        print(f"Step 4: Processing {len(prioritized_skus)} SKUs in parallel...")
        print("=" * 80)

        # Run all SKUs concurrently
        tasks = [
            self._process_single_sku(sku_problem) for sku_problem in prioritized_skus
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        return {
            "transfers": self.all_recommendations,
            "priority_analyses": self.priority_analyses,
        }

    async def _process_single_sku(self, sku_problem: Dict[str, Any]) -> None:
        """Process a single SKU's stockouts with the emergency agent."""
        sku_id = sku_problem["sku_id"]

        # Create SKU problem input
        sku_input = {
            "sku_id": sku_id,
            "product_details": sku_problem["product_info"],
            "stockout_locations": sku_problem["stockouts"],
        }

        # Create agent workflow and process this SKU
        try:
            # Run synchronous agent.invoke() in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor, self._invoke_agent_sync, sku_input
            )

            # Extract structured output from result state
            # With response_format=AgentOutput, OpenAI returns validated Pydantic instance
            agent_output = result.get("structured_response")

            # Fallback to parsing if needed (shouldn't happen with ProviderStrategy)
            if not agent_output:
                agent_output = self._parse_agent_output(result)

            # Debug: Log what we got from agent
            if agent_output:
                # Handle both Pydantic model and dict
                output_type = (
                    agent_output.output_type
                    if hasattr(agent_output, "output_type")
                    else agent_output.get("output_type")
                )
                logging.info(f"{sku_id}: Agent returned output_type: {output_type}")
            else:
                # Check if this is just because of tool calls or actual parse failure
                messages = result.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    content = last_msg.content if hasattr(last_msg, "content") else None

                    # Only log as warning if there's actual text content that failed to parse
                    if content and isinstance(content, list):
                        has_text = any(
                            isinstance(item, dict) and item.get("type") == "text"
                            for item in content
                        )
                        if has_text:
                            logging.warning(f"{sku_id}: Failed to parse agent output")
                            logging.info(f"{sku_id}: Raw agent response: {content}")
                    elif content:
                        logging.warning(f"{sku_id}: Failed to parse agent output")
                        logging.info(f"{sku_id}: Raw agent response: {content}")

            # Process agent output and store recommendations
            if agent_output:
                # Handle both Pydantic model and dict
                output_type = (
                    agent_output.output_type
                    if hasattr(agent_output, "output_type")
                    else agent_output.get("output_type")
                )

                # Extract summary
                summary = (
                    agent_output.summary
                    if hasattr(agent_output, "summary")
                    else agent_output.get("summary", "")
                )
                logging.info(f"{sku_id}: {summary}")

                # Process per-location results
                location_results = (
                    agent_output.location_results
                    if hasattr(agent_output, "location_results")
                    else agent_output.get("location_results", [])
                )

                resolved_count = 0
                unresolved_count = 0

                for loc_result in location_results:
                    # Handle Pydantic model or dict
                    if hasattr(loc_result, "status"):
                        status = loc_result.status
                        location_id = loc_result.location_id
                        shortage_qty = loc_result.shortage_qty
                        transfer = loc_result.transfer
                        reason_unresolved = loc_result.reason_unresolved
                    else:
                        status = loc_result.get("status")
                        location_id = loc_result.get("location_id")
                        shortage_qty = loc_result.get("shortage_qty")
                        transfer = loc_result.get("transfer")
                        reason_unresolved = loc_result.get("reason_unresolved")

                    if status == "RESOLVED":
                        resolved_count += 1
                        # Store transfer recommendation
                        if transfer:
                            if hasattr(transfer, "from_location"):
                                transfer_dict = {
                                    "from_location": transfer.from_location,
                                    "to_location": transfer.to_location,
                                    "quantity": transfer.quantity,
                                    "reasoning": transfer.reasoning,
                                    "estimated_cost": transfer.estimated_cost,
                                }
                            else:
                                transfer_dict = transfer

                            recommendation = {
                                "sku_id": sku_id,
                                **transfer_dict,
                            }
                            self.all_recommendations.append(recommendation)
                            logging.info(
                                f"{sku_id}: ✓ {location_id} resolved ({shortage_qty} units) - "
                                f"Transfer from {transfer_dict['from_location']}"
                            )
                    elif status == "UNRESOLVED":
                        unresolved_count += 1
                        logging.warning(
                            f"{sku_id}: ✗ {location_id} unresolved ({shortage_qty} units) - {reason_unresolved}"
                        )

                # Log overall outcome for this SKU
                total_locations = resolved_count + unresolved_count
                if resolved_count == total_locations:
                    logging.info(
                        f"{sku_id}: ✓ All {total_locations} location(s) resolved"
                    )
                elif resolved_count > 0:
                    logging.warning(
                        f"{sku_id}: ⚠ Partial success - {resolved_count}/{total_locations} location(s) resolved"
                    )
                else:
                    logging.error(
                        f"{sku_id}: ✗ No locations resolved - escalation required"
                    )

                # Handle complete escalation (no locations resolved)
                if output_type == "ESCALATION":
                    analysis = (
                        agent_output.priority_analysis
                        if hasattr(agent_output, "priority_analysis")
                        else agent_output.get("priority_analysis", {})
                    )

                    if analysis:
                        # Handle Pydantic model or dict
                        if hasattr(analysis, "summary"):
                            analysis_dict = {
                                "summary": analysis.summary,
                                "highest_priority_location": analysis.highest_priority_location,
                                "urgency_level": analysis.urgency_level,
                                "recommended_action": analysis.recommended_action,
                            }
                        else:
                            analysis_dict = analysis

                        self.priority_analyses.append(
                            {
                                "sku_id": sku_id,
                                "product_family": sku_problem["product_info"][
                                    "product_family"
                                ],
                                **analysis_dict,
                            }
                        )

        except Exception as e:
            logging.exception(
                f"{sku_id}: Agent processing failed",
                exc_info=e,
            )

    def _invoke_agent_sync(self, sku_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synchronous wrapper for agent invocation (runs in thread pool).
        """
        agent = create_emergency_agent()

        # Convert dict stockouts to StockoutRecord objects
        stockout_records = [
            StockoutRecord(**stockout) for stockout in sku_input["stockout_locations"]
        ]

        # Create initial state
        initial_state = {
            "sku_id": sku_input["sku_id"],
            "product_details": sku_input["product_details"],
            "stockout_locations": stockout_records,
            "reasoning_trace": [],
            "tools_called": [],
            "iteration_count": 0,
            "messages": [],
        }

        # Format initial prompt
        initial_prompt = format_sku_problem(initial_state)
        initial_state["messages"] = [HumanMessage(content=initial_prompt)]

        # Invoke agent (blocking call)
        result = agent.invoke(initial_state)

        return result

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

    def _parse_agent_output(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse structured output from agent's final message.

        Fallback method when structured_response is not in state.
        With OpenAI's native structured output, this shouldn't be needed.
        """
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

                    # Strip markdown code blocks if present
                    text = content.strip()
                    if text.startswith("```json"):
                        text = text[7:]
                    elif text.startswith("```"):
                        text = text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()

                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, ValueError):
                        return None

                # Handle list of content items (from Responses API)
                if isinstance(content, list):
                    import json

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

                            # Strip markdown code blocks more aggressively
                            text = text.strip()
                            # Remove opening ```json or ```
                            if text.startswith("```json"):
                                text = text[7:]
                            elif text.startswith("```"):
                                text = text[3:]
                            # Remove closing ```
                            if text.endswith("```"):
                                text = text[:-3]
                            text = text.strip()

                            try:
                                return json.loads(text)
                            except (json.JSONDecodeError, ValueError) as e:
                                logging.warning(f"Failed to parse JSON from text: {e}")
                                logging.debug(f"Attempted to parse: {text[:200]}")
                                return None

            return None
        except Exception as e:
            logging.exception("Failed to parse agent output", exc_info=e)
            return None


if __name__ == "__main__":
    # Test the orchestrator
    async def test():
        orchestrator = StockoutOrchestrator()
        results = await orchestrator.run()
        print()
        print("Results:", results)

    asyncio.run(test())
