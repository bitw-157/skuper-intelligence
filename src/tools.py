"""Database tools for Emergency Stockout Resolver Agent"""

import json
import logging
from typing import List, Optional

import psycopg
from langchain_core.tools import tool
from psycopg.rows import dict_row

from .config import CURRENT_WEEK_START, DB_CONFIG


@tool
def query_current_stockouts(
    time_window: str = "current_week",
    criticality_filter: Optional[str] = None,
    min_severity: int = -1000,
) -> str:
    """
    Get all immediate stockouts requiring resolution.

    Args:
        time_window: Filter by week ('current_week', 'next_week', 'all')
        criticality_filter: Product family filter (e.g., 'Oncology', 'Vaccines')
        min_severity: Only show shortages worse than this (e.g., -100)

    Returns:
        JSON string with list of stockout records including:
        - location_id, sku_id, end_inv_qty, safety_stock_qty
        - product_family, target_service_level, temp_class
        - location_type, priority_tier, handling_class
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT 
                    p.location_id,
                    p.sku_id,
                    p.week_start_date,
                    p.end_inv_qty,
                    p.safety_stock_qty,
                    p.projected_stockout_flag,
                    p.demand_fcst_qty,
                    prod.product_family,
                    prod.target_service_level,
                    prod.temp_class,
                    prod.unit_cost_usd,
                    loc.location_type,
                    loc.priority_tier,
                    loc.handling_class
                FROM projection_calcs_4w p
                JOIN products prod ON p.sku_id = prod.sku_id
                JOIN locations loc ON p.location_id = loc.location_id
                WHERE p.projected_stockout_flag::text = '1'
                    AND p.end_inv_qty < %s
                """

                params = [min_severity]

                if time_window == "current_week":
                    query += " AND p.week_start_date = %s"
                    params.append(CURRENT_WEEK_START)

                if criticality_filter:
                    query += " AND prod.product_family = %s"
                    params.append(criticality_filter)

                query += " ORDER BY prod.target_service_level DESC, p.end_inv_qty ASC"

                cur.execute(query, params)
                rows = cur.fetchall()

        return json.dumps(rows, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def query_inventory_surplus(
    sku_id: str,
    min_excess_qty: int = 50,
    exclude_locations: Optional[List[str]] = None,
    prioritize_near_expiry: bool = True,
    handling_class_required: Optional[str] = None,
) -> str:
    """
    Find locations with transferable excess inventory for a specific SKU.

    Args:
        sku_id: Product identifier
        min_excess_qty: Minimum transferable surplus required
        exclude_locations: Locations to exclude from results
        prioritize_near_expiry: Sort by expiry date (move expiring inventory first)
        handling_class_required: Filter by Ambient/ColdChain capability

    Returns:
        JSON string with surplus locations including:
        - location_id, available_qty, excess_qty
        - days_to_expiry, near_expiry_flag
        - handling_class
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT 
                    ib.location_id,
                    SUM(ib.available_qty) as total_available_qty,
                    ss.safety_stock_qty,
                    (SUM(ib.available_qty) - ss.safety_stock_qty) as excess_qty,
                    MIN(ib.days_to_expiry) as min_days_to_expiry,
                    MAX(ib.near_expiry_flag) as has_near_expiry,
                    loc.handling_class
                FROM inventory_batches ib
                JOIN safety_stock_parameters ss ON ib.location_id = ss.location_id AND ib.sku_id = ss.sku_id
                JOIN locations loc ON ib.location_id = loc.location_id
                WHERE ib.sku_id = %s
                    AND ib.quality_status = 'Released'
                """

                params = [sku_id]

                if handling_class_required:
                    query += " AND loc.handling_class = %s"
                    params.append(handling_class_required)

                query += """
                GROUP BY ib.location_id, ss.safety_stock_qty, loc.handling_class
                HAVING (SUM(ib.available_qty) - ss.safety_stock_qty) >= %s
                """
                params.append(min_excess_qty)

                if exclude_locations:
                    placeholders = ",".join(["%s"] * len(exclude_locations))
                    query += f" AND ib.location_id NOT IN ({placeholders})"
                    params.extend(exclude_locations)

                if prioritize_near_expiry:
                    query += " ORDER BY has_near_expiry DESC, min_days_to_expiry ASC, excess_qty DESC"
                else:
                    query += " ORDER BY excess_qty DESC"

                cur.execute(query, params)
                rows = cur.fetchall()

        return json.dumps(rows, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def query_transportation_lanes(
    from_location: str,
    to_location: str,
    max_lead_time: Optional[int] = None,
    mode_preference: Optional[str] = None,
) -> str:
    """
    Get available transportation routes between two locations.

    Args:
        from_location: Source location ID
        to_location: Destination location ID
        max_lead_time: Filter by maximum acceptable lead time (days)
        mode_preference: Prefer specific mode ('Air', 'Ground')

    Returns:
        JSON string with transportation lanes including:
        - lane_id, mode, standard_lead_time_days, max_lead_time_days
        - transfer_cost_per_unit_usd, min_transfer_qty
        - co2_kg_per_unit, allowed_flag
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT 
                    lane_id,
                    from_location_id,
                    to_location_id,
                    mode,
                    standard_lead_time_days,
                    max_lead_time_days,
                    min_transfer_qty,
                    transfer_cost_per_unit_usd,
                    co2_kg_per_unit,
                    allowed_flag
                FROM transportation_lanes
                WHERE from_location_id = %s
                    AND to_location_id = %s
                    AND allowed_flag::text = '1'
                """

                params = [from_location, to_location]

                if max_lead_time:
                    query += " AND standard_lead_time_days <= %s"
                    params.append(max_lead_time)

                if mode_preference:
                    query += " AND mode = %s"
                    params.append(mode_preference)

                query += " ORDER BY standard_lead_time_days ASC, transfer_cost_per_unit_usd ASC"

                cur.execute(query, params)
                rows = cur.fetchall()

        return json.dumps(rows, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def get_batch_details(
    location_id: str,
    sku_id: str,
    quality_filter: str = "Released",
    sort_by: str = "days_to_expiry",
) -> str:
    """
    Get batch-level inventory with expiry information.

    Args:
        location_id: Location identifier
        sku_id: Product identifier
        quality_filter: Quality status filter ('Released', 'Quarantine', 'All')
        sort_by: Sort order ('days_to_expiry', 'available_qty')

    Returns:
        JSON string with batch details including:
        - batch_id, available_qty, expiry_date, days_to_expiry
        - near_expiry_flag, quality_status
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT 
                    batch_id,
                    on_hand_qty,
                    reserved_qty,
                    available_qty,
                    expiry_date,
                    days_to_expiry,
                    near_expiry_flag,
                    quality_status,
                    last_movement_date
                FROM inventory_batches
                WHERE location_id = %s
                    AND sku_id = %s
                """

                params = [location_id, sku_id]

                if quality_filter != "All":
                    query += " AND quality_status = %s"
                    params.append(quality_filter)

                if sort_by == "days_to_expiry":
                    query += " ORDER BY days_to_expiry ASC"
                elif sort_by == "available_qty":
                    query += " ORDER BY available_qty DESC"

                cur.execute(query, params)
                rows = cur.fetchall()

        return json.dumps(rows, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def simulate_transfer_impact(
    source_location: str,
    destination_location: str,
    sku_id: str,
    transfer_qty: int,
    lead_time_days: int,
) -> str:
    """
    Project inventory levels after transfer at both source and destination.

    Args:
        source_location: Source location ID
        destination_location: Destination location ID
        sku_id: Product identifier
        transfer_qty: Quantity to transfer
        lead_time_days: Transit time in days

    Returns:
        JSON string with simulation results including:
        - source: current_inv, post_transfer_inv, safety_stock, is_stable
        - destination: current_inv, post_transfer_inv, safety_stock, resolves_stockout
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Get source current state
                cur.execute(
                    """
                    SELECT 
                        p.end_inv_qty as current_inventory,
                        ss.safety_stock_qty
                    FROM projection_calcs_4w p
                    JOIN safety_stock_parameters ss ON p.location_id = ss.location_id AND p.sku_id = ss.sku_id
                    WHERE p.location_id = %s AND p.sku_id = %s AND p.week_start_date = %s
                """,
                    [source_location, sku_id, CURRENT_WEEK_START],
                )
                source_data = cur.fetchone()

                # Get destination current state
                cur.execute(
                    """
                    SELECT 
                        p.end_inv_qty as current_inventory,
                        ss.safety_stock_qty,
                        ss.max_stock_qty
                    FROM projection_calcs_4w p
                    JOIN safety_stock_parameters ss ON p.location_id = ss.location_id AND p.sku_id = ss.sku_id
                    WHERE p.location_id = %s AND p.sku_id = %s AND p.week_start_date = %s
                """,
                    [destination_location, sku_id, CURRENT_WEEK_START],
                )
                dest_data = cur.fetchone()

        if not source_data or not dest_data:
            return json.dumps({"error": "Location or SKU not found in projections"})

        # Calculate impacts
        source_post_transfer = source_data["current_inventory"] - transfer_qty
        dest_post_transfer = dest_data["current_inventory"] + transfer_qty

        result = {
            "source": {
                "location_id": source_location,
                "current_inventory": source_data["current_inventory"],
                "post_transfer_inventory": source_post_transfer,
                "safety_stock": source_data["safety_stock_qty"],
                "is_stable": source_post_transfer >= source_data["safety_stock_qty"],
                "remaining_excess": source_post_transfer
                - source_data["safety_stock_qty"],
            },
            "destination": {
                "location_id": destination_location,
                "current_inventory": dest_data["current_inventory"],
                "post_transfer_inventory": dest_post_transfer,
                "safety_stock": dest_data["safety_stock_qty"],
                "max_stock": dest_data["max_stock_qty"],
                "resolves_stockout": dest_post_transfer >= 0,
                "within_capacity": dest_post_transfer <= dest_data["max_stock_qty"],
                "buffer_achieved": dest_post_transfer >= dest_data["safety_stock_qty"],
            },
            "transfer_qty": transfer_qty,
            "lead_time_days": lead_time_days,
        }

        return json.dumps(result, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def validate_cold_chain_compliance(
    source_location: str,
    destination_location: str,
    sku_id: str,
    lane_id: Optional[str] = None,
) -> str:
    """
    Verify cold chain requirements are met across the transfer route.

    Args:
        source_location: Source location ID
        destination_location: Destination location ID
        sku_id: Product identifier
        lane_id: Optional lane ID for validation

    Returns:
        JSON string with compliance check:
        - status: 'PASS' or 'FAIL'
        - violations: List of violation descriptions
        - product_temp_class, source_handling_class, dest_handling_class
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Get product temp requirements
                cur.execute(
                    """
                    SELECT temp_class
                    FROM products
                    WHERE sku_id = %s
                """,
                    [sku_id],
                )
                product = cur.fetchone()

                # Get source location capabilities
                cur.execute(
                    """
                    SELECT handling_class
                    FROM locations
                    WHERE location_id = %s
                """,
                    [source_location],
                )
                source_loc = cur.fetchone()

                # Get destination location capabilities
                cur.execute(
                    """
                    SELECT handling_class
                    FROM locations
                    WHERE location_id = %s
                """,
                    [destination_location],
                )
                dest_loc = cur.fetchone()

        if not product or not source_loc or not dest_loc:
            return json.dumps({"error": "Product or location not found"})

        violations = []

        # Check if product requires ColdChain
        if product["temp_class"] == "ColdChain":
            if source_loc["handling_class"] != "ColdChain":
                violations.append(
                    f"Source location {source_location} cannot handle ColdChain products"
                )
            if dest_loc["handling_class"] != "ColdChain":
                violations.append(
                    f"Destination location {destination_location} cannot handle ColdChain products"
                )

        result = {
            "status": "PASS" if len(violations) == 0 else "FAIL",
            "violations": violations,
            "product_temp_class": product["temp_class"],
            "source_handling_class": source_loc["handling_class"],
            "dest_handling_class": dest_loc["handling_class"],
        }

        return json.dumps(result, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def get_demand_forecast_details(
    location_id: str, sku_id: str, weeks_ahead: int = 1
) -> str:
    """
    Get demand forecast with confidence levels for buffer calculations.

    Args:
        location_id: Location identifier
        sku_id: Product identifier
        weeks_ahead: Number of weeks to forecast (1-4)

    Returns:
        JSON string with forecast details:
        - forecast_qty, forecast_confidence
        - forecast_source, last_updated
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT 
                        week_start_date,
                        forecast_qty,
                        forecast_confidence,
                        forecast_source,
                        last_updated
                    FROM demand_forecast_4w
                    WHERE location_id = %s
                        AND sku_id = %s
                    ORDER BY week_start_date ASC
                    LIMIT %s
                """,
                    [location_id, sku_id, weeks_ahead],
                )
                rows = cur.fetchall()

        return json.dumps(rows, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def check_incoming_supply(location_id: str, sku_id: str, weeks_ahead: int = 4) -> str:
    """
    Verify if destination already has supply orders en route.

    Args:
        location_id: Destination location identifier
        sku_id: Product identifier
        weeks_ahead: Number of weeks to check ahead

    Returns:
        JSON string with incoming supply orders:
        - supply_order_id, qty, arrival_week_start
        - status, reroutable_flag, cancelable_flag
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT 
                        supply_order_id,
                        source_location_id,
                        qty,
                        planned_arrival_date,
                        arrival_week_start,
                        status,
                        reroutable_flag,
                        cancelable_flag,
                        lead_time_days
                    FROM supply_plan
                    WHERE destination_location_id = %s
                        AND sku_id = %s
                        AND status IN ('Planned', 'Firm', 'InTransit')
                    ORDER BY arrival_week_start ASC
                    LIMIT %s
                """,
                    [location_id, sku_id, weeks_ahead],
                )
                rows = cur.fetchall()

        return json.dumps(rows, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def calculate_transfer_cost(lane_id: str, transfer_qty: int) -> str:
    """
    Calculate total transfer cost including minimum quantity adjustments.

    Args:
        lane_id: Transportation lane identifier
        transfer_qty: Quantity to transfer

    Returns:
        JSON string with cost breakdown:
        - base_cost, min_qty_adjustment, total_cost
        - min_transfer_qty, actual_transfer_qty
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT 
                        min_transfer_qty,
                        transfer_cost_per_unit_usd,
                        mode
                    FROM transportation_lanes
                    WHERE lane_id = %s
                """,
                    [lane_id],
                )
                lane = cur.fetchone()

        if not lane:
            return json.dumps({"error": "Lane not found"})

        # Adjust for minimum quantity
        actual_qty = max(transfer_qty, lane["min_transfer_qty"])
        base_cost = transfer_qty * lane["transfer_cost_per_unit_usd"]
        total_cost = actual_qty * lane["transfer_cost_per_unit_usd"]
        min_qty_adjustment = total_cost - base_cost

        result = {
            "lane_id": lane_id,
            "requested_qty": transfer_qty,
            "min_transfer_qty": lane["min_transfer_qty"],
            "actual_transfer_qty": actual_qty,
            "cost_per_unit": lane["transfer_cost_per_unit_usd"],
            "base_cost": round(base_cost, 2),
            "min_qty_adjustment": round(min_qty_adjustment, 2),
            "total_cost": round(total_cost, 2),
            "mode": lane["mode"],
        }

        return json.dumps(result, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


# Export all tools
ALL_TOOLS = [
    query_current_stockouts,
    query_inventory_surplus,
    query_transportation_lanes,
    get_batch_details,
    simulate_transfer_impact,
    validate_cold_chain_compliance,
    get_demand_forecast_details,
    check_incoming_supply,
    calculate_transfer_cost,
]
