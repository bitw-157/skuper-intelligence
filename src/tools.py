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
    Get all immediate stockouts requiring resolution from projection_calcs_4w table.

    Use this tool to identify locations with current or projected stockouts that need
    inventory transfers. Results include product details, location priorities, and
    handling requirements (e.g., ColdChain compliance).

    Args:
        time_window: Filter by week - 'current_week' for immediate stockouts (Week 0-1),
                    'next_week' for Week 2, 'all' for all projected stockouts
        criticality_filter: Optional product family filter (e.g., 'Oncology', 'Vaccines',
                           'Cardio', 'Diabetes') to prioritize critical products
        min_severity: Only return stockouts worse than this threshold (e.g., -100 means
                     shortages of 100+ units). Lower/more negative = more severe.

    Returns:
        JSON string with list of stockout records including:
        - location_id, sku_id: Identifiers for the stockout
        - end_inv_qty: Projected inventory (negative = shortage amount)
        - safety_stock_qty: Minimum inventory target
        - demand_fcst_qty: Weekly demand forecast
        - product_family, target_service_level, temp_class, unit_cost_usd: Product details
        - location_type, priority_tier, handling_class: Location capabilities
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

    Use this tool to identify source locations that have surplus inventory above their
    safety stock levels. Results are filtered to only show 'Released' quality inventory
    that can be transferred. Use this to find transfer sources for emergency stockouts.

    Args:
        sku_id: Product identifier (e.g., 'SKU_001')
        min_excess_qty: Minimum transferable surplus required (units above safety stock).
                       Default 50 units ensures meaningful transfer quantities.
        exclude_locations: List of location IDs to exclude (e.g., destinations or locations
                          already considered). Provide as list: ['DC_01', 'DC_02']
        prioritize_near_expiry: If True, sorts by expiry date to move expiring inventory
                               first (FEFO - First Expire First Out). Recommended: True.
        handling_class_required: Filter by location capability - 'ColdChain' for temperature-
                                controlled products, 'Ambient' for standard products, or None
                                for any. CRITICAL: Must match product temp_class requirements.

    Returns:
        JSON string with surplus locations including:
        - location_id: Source location identifier
        - total_available_qty: Total inventory at location
        - safety_stock_qty: Minimum required inventory (do not go below this)
        - excess_qty: Transferable amount (total_available - safety_stock)
        - min_days_to_expiry: Days until earliest batch expires
        - has_near_expiry: Boolean flag if any batch expires within 30 days
        - handling_class: Location capability ('ColdChain' or 'Ambient')
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

    Use this tool to find shipping options and costs for inventory transfers. Results
    include both Air and Ground modes with lead times and costs. Only returns lanes
    where allowed_flag=1 (approved routes).

    Args:
        from_location: Source location ID (e.g., 'DC_01', 'PLANT_01')
        to_location: Destination location ID (e.g., 'DC_02', 'RETAIL_01')
        max_lead_time: Optional filter for maximum acceptable lead time in days.
                      Use this when shipment must arrive by specific date (e.g., 3 days
                      for emergency stockouts). If None, returns all available lanes.
        mode_preference: Optional filter for specific mode - 'Air' (faster, expensive)
                        or 'Ground' (slower, cheaper). If None, returns both modes.

    Returns:
        JSON string with transportation lanes including:
        - lane_id: Unique lane identifier (use this for cost calculations)
        - from_location_id, to_location_id: Route endpoints
        - mode: 'Air' or 'Ground'
        - standard_lead_time_days: Typical transit time
        - max_lead_time_days: Worst-case transit time (use for safety)
        - min_transfer_qty: Minimum shipment size (if transfer < this, may not be feasible)
        - transfer_cost_per_unit_usd: Cost per unit shipped
        - co2_kg_per_unit: Carbon footprint per unit (for sustainability reporting)
        - allowed_flag: Always 1 in results (filtered for approved routes only)
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
    Get batch-level inventory with expiry information for FEFO (First Expire First Out) management.

    Use this tool to understand expiry dates and quality status of inventory at a location.
    Helps identify near-expiry batches that should be transferred first to minimize waste.

    Args:
        location_id: Location identifier (e.g., 'DC_01')
        sku_id: Product identifier (e.g., 'SKU_001')
        quality_filter: Quality status filter:
                       - 'Released': Available for transfer (default)
                       - 'Quarantine': Under quality hold
                       - 'All': All quality statuses
        sort_by: Sort order:
                - 'days_to_expiry': Prioritize expiring batches (FEFO)
                - 'available_qty': Prioritize largest batches

    Returns:
        JSON string with batch details including:
        - batch_id: Unique batch identifier
        - on_hand_qty, reserved_qty, available_qty: Inventory status
        - expiry_date: Batch expiration date
        - days_to_expiry: Days until expiration (prioritize < 30 days)
        - near_expiry_flag: Boolean if expires within 30 days
        - quality_status: 'Released' or 'Quarantine'
        - last_movement_date: Last transaction date
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

    CRITICAL VALIDATION TOOL: Use this before recommending any transfer to ensure:
    1. Source maintains safety stock (is_stable = True required)
    2. Destination stockout is resolved (resolves_stockout = True)
    3. Destination stays within capacity (within_capacity = True)

    This simulation helps avoid creating new stockouts at the source location.

    Args:
        source_location: Source location ID (e.g., 'DC_01')
        destination_location: Destination location ID (e.g., 'DC_02')
        sku_id: Product identifier (e.g., 'SKU_001')
        transfer_qty: Quantity to transfer (units)
        lead_time_days: Transit time in days (from transportation lane)

    Returns:
        JSON string with simulation results:

        Source impact:
        - current_inventory: Inventory before transfer
        - post_transfer_inventory: Inventory after transfer leaves
        - safety_stock: Minimum required (MUST maintain this)
        - is_stable: True if post_transfer >= safety_stock (REQUIRED for approval)
        - remaining_excess: Surplus remaining after transfer

        Destination impact:
        - current_inventory: Current deficit (negative = shortage)
        - post_transfer_inventory: Inventory after transfer arrives
        - safety_stock: Minimum target inventory
        - max_stock: Maximum capacity
        - resolves_stockout: True if post_transfer >= 0 (resolves shortage)
        - within_capacity: True if post_transfer <= max_stock
        - buffer_achieved: True if post_transfer >= safety_stock (ideal outcome)
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

    MANDATORY CHECK for temperature-sensitive products. Products with temp_class='ColdChain'
    MUST only be transferred between locations with handling_class='ColdChain'. Violating
    this constraint can result in product spoilage and patient safety issues.

    Always call this tool when:
    - Product temp_class is 'ColdChain'
    - Before recommending any transfer
    - To validate if a transfer route is feasible

    Args:
        source_location: Source location ID (e.g., 'DC_01')
        destination_location: Destination location ID (e.g., 'DC_02')
        sku_id: Product identifier (e.g., 'SKU_001')
        lane_id: Optional specific lane ID for validation (currently not used)

    Returns:
        JSON string with compliance check:
        - status: 'PASS' (compliant) or 'FAIL' (violations detected)
        - violations: List of specific violation descriptions
        - product_temp_class: Product requirement ('ColdChain' or 'Ambient')
        - source_handling_class: Source capability ('ColdChain' or 'Ambient')
        - dest_handling_class: Destination capability ('ColdChain' or 'Ambient')

        DECISION RULE: Only proceed with transfer if status='PASS'
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

    Use this tool to understand future demand patterns and forecast reliability.
    forecast_confidence values indicate how much safety buffer to add:
    - High confidence (>0.8): Trust the forecast, use standard buffer
    - Medium confidence (0.6-0.8): Add moderate buffer (10-20%)
    - Low confidence (<0.6): Add larger buffer (20-30%) or escalate

    Args:
        location_id: Location identifier (e.g., 'DC_01')
        sku_id: Product identifier (e.g., 'SKU_001')
        weeks_ahead: Number of weeks to forecast (1-4):
                    - 1: Current week projections
                    - 2-4: Future weeks for proactive planning

    Returns:
        JSON string with forecast details (one row per week):
        - week_start_date: Forecast week start date
        - forecast_qty: Expected demand (units)
        - forecast_confidence: Reliability score (0.0-1.0)
        - forecast_source: Model used ('ML', 'Historical', 'Manual')
        - last_updated: Timestamp of last forecast update
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
    Verify if destination already has supply orders en route that may resolve the stockout.

    Use this tool to avoid redundant transfers when supply is already scheduled. If incoming
    supply will resolve the stockout, transfers may not be necessary. This is especially
    important for proactive agent to check before recommending preemptive transfers.

    Args:
        location_id: Destination location identifier (e.g., 'DC_01')
        sku_id: Product identifier (e.g., 'SKU_001')
        weeks_ahead: Number of weeks to check ahead (default 4 covers emergency + proactive timeframe)

    Returns:
        JSON string with incoming supply orders:
        - supply_order_id: Unique order identifier
        - source_location_id: Origin of the supply
        - qty: Quantity arriving (units)
        - planned_arrival_date: Expected arrival date
        - arrival_week_start: Week start date for grouping
        - status: 'Planned', 'Firm', or 'InTransit'
        - reroutable_flag: 1 if can be rerouted (proactive agent uses this)
        - cancelable_flag: 1 if can be cancelled
        - lead_time_days: Transit time
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

    Use this tool to get accurate cost estimates for transfers. Important: If transfer
    quantity is below min_transfer_qty, actual cost will be based on minimum quantity.
    This helps avoid recommending uneconomical small transfers.

    Args:
        lane_id: Transportation lane identifier (from query_transportation_lanes)
        transfer_qty: Quantity to transfer (units)

    Returns:
        JSON string with cost breakdown:
        - lane_id: Lane identifier used
        - requested_qty: Quantity you requested
        - min_transfer_qty: Minimum shipment size for this lane
        - actual_transfer_qty: Quantity that will be shipped (max of requested and min)
        - cost_per_unit: Per-unit cost from lane
        - base_cost: Cost for requested quantity
        - min_qty_adjustment: Extra cost if below minimum (0 if above minimum)
        - total_cost: Final total cost
        - mode: 'Air' or 'Ground'

        NOTE: If requested_qty < min_transfer_qty, you pay for min_transfer_qty
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


# ============================================================================
# NEW TOOLS FOR TYPE B: PROACTIVE REBALANCER
# ============================================================================


@tool
def query_incoming_supply_orders(
    sku_id: str,
    weeks_ahead: int = 4,
    destination_filter: Optional[str] = None,
) -> str:
    """
    Find all reroutable incoming supply orders for a specific SKU within planning horizon.

    PRIMARY TOOL FOR PROACTIVE AGENT: Use this FIRST when handling projected stockouts.
    Supply reroutes are preferred over emergency transfers because they're more efficient
    (no additional freight cost for new shipment, just cost delta for route change).

    Focus on orders with reroutable_flag=1 going to locations that DON'T have stockouts.
    These orders can potentially be redirected to resolve projected stockouts elsewhere.

    Args:
        sku_id: Product identifier to check for incoming supply (e.g., 'SKU_001')
        weeks_ahead: How far ahead to look (default 4 weeks covers proactive horizon)
        destination_filter: Optional location ID to filter - use this to check if a
                           specific location already has supply en route

    Returns:
        JSON string with list of supply orders including:
        - supply_order_id: Unique order identifier (use this for rerouting)
        - sku_id: Product identifier
        - destination_location_id: Current destination (location that would lose supply)
        - source_location_id: Origin (plant/supplier - usually fixed)
        - qty: Planned quantity (units)
        - planned_arrival_date: Expected arrival date
        - arrival_week_start: Week bucket (compare with stockout week)
        - status: 'Planned' (flexible) or 'Firm' (committed but still reroutable)
        - reroutable_flag: 1=can reroute, 0=locked (tool filters for 1 only)
        - cancelable_flag: Whether order can be cancelled
        - unit_transport_cost_usd: Current cost per unit
        - lead_time_days: Transit time from source
        - order_priority: Priority level (1=highest, consider when rerouting)

        STRATEGY: Look for orders going to locations WITHOUT stockouts, check if qty
        is sufficient to resolve stockout if rerouted, validate using simulate_supply_reroute
    """
    try:
        # Calculate date range for weeks ahead
        from datetime import datetime, timedelta

        current_date = datetime.strptime(CURRENT_WEEK_START, "%Y-%m-%d")
        end_date = current_date + timedelta(weeks=weeks_ahead)

        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                query = """
                SELECT 
                    supply_order_id,
                    sku_id,
                    destination_location_id,
                    source_location_id,
                    qty,
                    planned_arrival_date,
                    arrival_week_start,
                    status,
                    reroutable_flag,
                    cancelable_flag,
                    unit_transport_cost_usd,
                    lead_time_days,
                    order_priority
                FROM supply_plan
                WHERE sku_id = %s
                  AND arrival_week_start > %s
                  AND arrival_week_start <= %s
                  AND status IN ('Planned', 'Firm')
                  AND reroutable_flag::text = '1'
                """

                params = [sku_id, CURRENT_WEEK_START, end_date.strftime("%Y-%m-%d")]

                if destination_filter:
                    query += " AND destination_location_id = %s"
                    params.append(destination_filter)

                query += " ORDER BY arrival_week_start ASC, order_priority ASC"

                cur.execute(query, params)
                rows = cur.fetchall()

        return json.dumps(rows, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def simulate_supply_reroute(
    supply_order_id: str,
    from_location_id: str,
    to_location_id: str,
) -> str:
    """
    Calculate the full impact of rerouting a supply order to a different destination.

    CRITICAL VALIDATION TOOL FOR PROACTIVE AGENT: Use this after identifying a candidate
    reroute from query_incoming_supply_orders. This simulation helps you understand:
    1. Will rerouting create a stockout at the original destination? (MUST CHECK)
    2. Will it resolve the stockout at the new destination? (GOAL)
    3. What is the cost impact? (Should be < 70% of emergency transfer cost)
    4. Will it arrive in time? (Before projected stockout  week)

    Only recommend reroute if: is_feasible=True AND creates_stockout=False.

    Args:
        supply_order_id: Which supply order to reroute (from query_incoming_supply_orders)
        from_location_id: Current destination that would LOSE this supply (check safety!)
        to_location_id: Proposed new destination that would GAIN this supply (stockout location)

    Returns:
        JSON string with comprehensive simulation results:
        - is_feasible: Whether reroute is technically possible (bool)
        - cost_delta_usd: Additional cost (positive) or savings (negative)
        - eta_change_days: Change in arrival time (positive = later)
        - from_location_impact: Effect on original destination
            * current_end_inv_qty: Current projected inventory
            * new_end_inv_qty: Inventory if supply is rerouted away
            * creates_stockout: Whether reroute causes stockout (REJECT if True)
            * safety_stock_qty: Minimum target inventory
        - to_location_impact: Effect on new destination
            * current_end_inv_qty: Current projected inventory
            * new_end_inv_qty: Inventory if supply is rerouted here
            * resolves_stockout: Whether this fixes a stockout (bool)
            * safety_stock_qty: Minimum target inventory
        - supply_order_details: Original order information
        - new_lane_details: Transportation lane for new route
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Get supply order details
                cur.execute(
                    """
                    SELECT 
                        supply_order_id,
                        sku_id,
                        source_location_id,
                        destination_location_id,
                        qty,
                        arrival_week_start,
                        unit_transport_cost_usd,
                        lead_time_days,
                        status
                    FROM supply_plan
                    WHERE supply_order_id = %s
                    """,
                    [supply_order_id],
                )
                order = cur.fetchone()

                if not order:
                    return json.dumps(
                        {"error": f"Supply order {supply_order_id} not found"}
                    )

                # Check if new transportation lane exists
                cur.execute(
                    """
                    SELECT 
                        lane_id,
                        mode,
                        standard_lead_time_days as avg_transit_days,
                        transfer_cost_per_unit_usd as unit_cost_usd,
                        allowed_flag
                    FROM transportation_lanes
                    WHERE from_location_id = %s
                      AND to_location_id = %s
                      AND allowed_flag::text = '1'
                    ORDER BY standard_lead_time_days ASC, transfer_cost_per_unit_usd ASC
                    LIMIT 1
                    """,
                    [order["source_location_id"], to_location_id],
                )
                new_lane = cur.fetchone()

                if not new_lane:
                    return json.dumps(
                        {
                            "is_feasible": False,
                            "reason": f"No transportation lane exists from {order['source_location_id']} to {to_location_id}",
                        }
                    )

                # Get current projection for from_location (losing supply)
                cur.execute(
                    """
                    SELECT 
                        p.end_inv_qty,
                        p.supply_in_qty,
                        ss.safety_stock_qty
                    FROM projection_calcs_4w p
                    JOIN safety_stock_parameters ss 
                        ON p.location_id = ss.location_id AND p.sku_id = ss.sku_id
                    WHERE p.location_id = %s 
                      AND p.sku_id = %s 
                      AND p.week_start_date = %s
                    """,
                    [from_location_id, order["sku_id"], order["arrival_week_start"]],
                )
                from_proj = cur.fetchone()

                # Get current projection for to_location (gaining supply)
                cur.execute(
                    """
                    SELECT 
                        p.end_inv_qty,
                        p.supply_in_qty,
                        p.projected_stockout_flag,
                        ss.safety_stock_qty
                    FROM projection_calcs_4w p
                    JOIN safety_stock_parameters ss 
                        ON p.location_id = ss.location_id AND p.sku_id = ss.sku_id
                    WHERE p.location_id = %s 
                      AND p.sku_id = %s 
                      AND p.week_start_date = %s
                    """,
                    [to_location_id, order["sku_id"], order["arrival_week_start"]],
                )
                to_proj = cur.fetchone()

        if not from_proj or not to_proj:
            return json.dumps(
                {
                    "is_feasible": False,
                    "reason": "Projection data not available for one or both locations",
                }
            )

        # Calculate impacts
        cost_delta = (
            new_lane["unit_cost_usd"] - order["unit_transport_cost_usd"]
        ) * order["qty"]
        eta_change = new_lane["avg_transit_days"] - order["lead_time_days"]

        from_new_inv = from_proj["end_inv_qty"] - order["qty"]
        to_new_inv = to_proj["end_inv_qty"] + order["qty"]

        result = {
            "is_feasible": True,
            "cost_delta_usd": round(cost_delta, 2),
            "eta_change_days": eta_change,
            "from_location_impact": {
                "location_id": from_location_id,
                "current_end_inv_qty": from_proj["end_inv_qty"],
                "new_end_inv_qty": from_new_inv,
                "creates_stockout": from_new_inv < 0,
                "below_safety_stock": from_new_inv < from_proj["safety_stock_qty"],
                "safety_stock_qty": from_proj["safety_stock_qty"],
            },
            "to_location_impact": {
                "location_id": to_location_id,
                "current_end_inv_qty": to_proj["end_inv_qty"],
                "new_end_inv_qty": to_new_inv,
                "resolves_stockout": to_proj["projected_stockout_flag"] == 1
                and to_new_inv >= 0,
                "achieves_safety_stock": to_new_inv >= to_proj["safety_stock_qty"],
                "safety_stock_qty": to_proj["safety_stock_qty"],
            },
            "supply_order_details": {
                "supply_order_id": order["supply_order_id"],
                "sku_id": order["sku_id"],
                "qty": order["qty"],
                "original_destination": from_location_id,
                "source": order["source_location_id"],
                "original_cost_per_unit": order["unit_transport_cost_usd"],
            },
            "new_lane_details": {
                "lane_id": new_lane["lane_id"],
                "mode": new_lane["mode"],
                "lead_time_days": new_lane["avg_transit_days"],
                "cost_per_unit": new_lane["unit_cost_usd"],
            },
        }

        return json.dumps(result, default=str)

    except Exception as e:
        logging.exception("Database operation failed")
        return json.dumps({"error": str(e)})


@tool
def validate_supply_reroute_constraints(
    supply_order_id: str,
    new_destination_id: str,
) -> str:
    """
    Validate business rules and constraints before recommending a supply reroute.

    Use this tool as a final check before recommending supply reroute. It validates:
    - Order is actually reroutable (reroutable_flag=1)
    - Order status allows changes (Planned or Firm, not InTransit)
    - Transportation lane exists to new destination
    - Cold chain compliance if product requires it
    - No business/policy blocks on the reroute

    Call this AFTER simulate_supply_reroute shows positive results but BEFORE
    making final recommendation.

    Args:
        supply_order_id: Supply order to validate (from query_incoming_supply_orders)
        new_destination_id: Proposed new destination location (stockout location)

    Returns:
        JSON string with validation results:
        - is_valid: Whether reroute passes all checks (bool)
        - constraints_passed: List of constraint names that passed
        - constraints_failed: List of constraint names that failed
        - warnings: List of non-blocking warnings
        - details: Additional context for failures
    """
    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Get supply order details
                cur.execute(
                    """
                    SELECT 
                        so.supply_order_id,
                        so.sku_id,
                        so.source_location_id,
                        so.destination_location_id,
                        so.status,
                        so.reroutable_flag,
                        so.order_priority,
                        p.temp_class as product_temp_class
                    FROM supply_plan so
                    JOIN products p ON so.sku_id = p.sku_id
                    WHERE so.supply_order_id = %s
                    """,
                    [supply_order_id],
                )
                order = cur.fetchone()

                if not order:
                    return json.dumps(
                        {
                            "is_valid": False,
                            "constraints_failed": ["order_not_found"],
                            "details": f"Supply order {supply_order_id} not found",
                        }
                    )

                # Get destination location capabilities
                cur.execute(
                    """
                    SELECT 
                        location_id,
                        handling_class,
                        location_type
                    FROM locations
                    WHERE location_id = %s
                    """,
                    [new_destination_id],
                )
                dest_loc = cur.fetchone()

                if not dest_loc:
                    return json.dumps(
                        {
                            "is_valid": False,
                            "constraints_failed": ["destination_not_found"],
                            "details": f"Destination {new_destination_id} not found",
                        }
                    )

                # Check if lane exists
                cur.execute(
                    """
                    SELECT lane_id, allowed_flag
                    FROM transportation_lanes
                    WHERE from_location_id = %s
                      AND to_location_id = %s
                    """,
                    [order["source_location_id"], new_destination_id],
                )
                lane = cur.fetchone()

        # Validate constraints
        passed = []
        failed = []
        warnings = []

        # 1. Check reroutable flag
        if order["reroutable_flag"] == 1:
            passed.append("reroutable_flag")
        else:
            failed.append("reroutable_flag")

        # 2. Check status (must be Planned or Firm, not InTransit)
        if order["status"] in ["Planned", "Firm"]:
            passed.append("order_status")
        else:
            failed.append("order_status")
            warnings.append(
                f"Order status is '{order['status']}' - may be too late to reroute"
            )

        # 3. Check lane existence
        if lane and lane["allowed_flag"] == 1:
            passed.append("transportation_lane")
        elif lane:
            failed.append("transportation_lane")
            warnings.append("Lane exists but is not allowed")
        else:
            failed.append("transportation_lane")

        # 4. Temperature/handling class compatibility (warning only for MVP)
        if (
            order["product_temp_class"] == "ColdChain"
            and dest_loc["handling_class"] != "ColdChain"
        ):
            warnings.append(
                f"Product requires ColdChain but destination is {dest_loc['handling_class']}"
            )

        # 5. High priority orders (warning only)
        if order["order_priority"] == 1:
            warnings.append(
                "Order has highest priority (1) - rerouting may impact critical supply"
            )

        result = {
            "is_valid": len(failed) == 0,
            "constraints_passed": passed,
            "constraints_failed": failed,
            "warnings": warnings,
            "details": {
                "supply_order_id": order["supply_order_id"],
                "current_destination": order["destination_location_id"],
                "proposed_destination": new_destination_id,
                "reroutable_flag": order["reroutable_flag"],
                "status": order["status"],
                "lane_exists": lane is not None if lane else False,
            },
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
    # Type B: Proactive Rebalancer tools
    query_incoming_supply_orders,
    simulate_supply_reroute,
    validate_supply_reroute_constraints,
]
