from flask import render_template, Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func, case
from app import db
from app.models import Asset, Facility, Room, RepairLog, MovementLog, OwnershipLog, \
    ConsumableStock, ConsumableIssuanceLog, Vendor, Technician, AssetCategory, Staff, User
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

# Helper function for role-based filtering
def get_base_asset_query():
    query = Asset.query.filter(Asset.is_archived == False)
    if current_user.role == 'Branch Manager':
        return query.join(Room).filter(Room.facility_id == current_user.facility_id)
    if current_user.role == 'Department Manager':
        return query.filter(Asset.department == current_user.department)
    return query

# Helper function to apply date filtering to query objects
def apply_date_filter(query, date_column, start_date_str, end_date_str):
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            query = query.filter(date_column >= start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

            next_day = end_date + timedelta(days=1)
            query = query.filter(date_column < next_day)
        except (ValueError, TypeError):
            pass

    return query

# --- Main Report Pages ---
@reports_bp.route('/assets')
@login_required
def asset_reports():
    return render_template('reports/assets_dashboard.html', title="Asset Reports")

# --- Main Consumable Report Page ---
@reports_bp.route('/consumables')
@login_required
def consumable_reports():
    # This route just renders the main dashboard layout
    return render_template('reports/consumables_dashboard.html', title="Consumable Reports")



# --- DATA API Routes for Charts ---
@reports_bp.route('/data/assets_by_status')
@login_required
def data_assets_by_status():
    base_query = get_base_asset_query()
    status_counts = dict(base_query.with_entities(Asset.status, func.count(Asset.status)).group_by(Asset.status).all())
    labels = list(status_counts.keys())
    data = list(status_counts.values())

    return jsonify({'labels': labels, 'data': data})


@reports_bp.route('/data/assets_by_category')
@login_required
def data_assets_by_category():
    base_query = get_base_asset_query()

    category_counts = base_query \
        .join(AssetCategory, Asset.category_id == AssetCategory.id) \
        .with_entities(
        AssetCategory.name,
        func.count(Asset.id)
    ) \
        .group_by(AssetCategory.name) \
        .order_by(AssetCategory.name) \
        .all()


    if category_counts:
        labels = [row[0] for row in category_counts]
        data = [row[1] for row in category_counts]
    else:
        labels = []
        data = []

    return jsonify({'labels': labels, 'data': data})


@reports_bp.route('/data/repair_costs_by_technician')
@login_required
def data_repair_costs_by_technician():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Base query to get all relevant repairs within the date range
    repair_query = db.session.query(
        RepairLog.id,
        RepairLog.cost,
        Technician.name.label('technician_name')
    ).join(Technician, Technician.id == RepairLog.technician_id)
    repair_query = repair_query.filter(RepairLog.status == 'Completed')
    repair_query = apply_date_filter(repair_query, RepairLog.report_date, start_date_str, end_date_str)

    repairs = repair_query.all()

    # --- PROCESS THE DATA IN PYTHON ---
    tech_data = {}
    for repair in repairs:
        if repair.technician_name not in tech_data:
            tech_data[repair.technician_name] = {'cost': 0, 'frequency': 0, 'repair_ids': []}

        tech_data[repair.technician_name]['cost'] += (repair.cost or 0)
        tech_data[repair.technician_name]['frequency'] += 1
        tech_data[repair.technician_name]['repair_ids'].append(repair.id)

    # Sort by total cost
    sorted_techs = sorted(tech_data.items(), key=lambda item: item[1]['cost'], reverse=True)

    labels = [item[0] for item in sorted_techs]
    costs = [item[1]['cost'] for item in sorted_techs]
    frequencies = [item[1]['frequency'] for item in sorted_techs]
    repair_id_lists = [item[1]['repair_ids'] for item in sorted_techs]

    return jsonify({
        'labels': labels,
        'costs': costs,
        'frequencies': frequencies,
        'repair_ids': repair_id_lists
    })


@reports_bp.route('/data/assets_by_facility')
@login_required
def data_assets_by_facility():
    # This report is for admins, so we don't apply role filters
    facility_counts = db.session.query(
        Facility.name,
        func.count(Asset.id)
    ).join(Room, Facility.id == Room.facility_id) \
        .join(Asset, Room.id == Asset.room_id) \
        .group_by(Facility.name).order_by(Facility.name).all()

    labels = [row[0] for row in facility_counts]
    data = [row[1] for row in facility_counts]

    return jsonify({'labels': labels, 'data': data})


@reports_bp.route('/data/repair_costs_by_facility')
@login_required
def data_repair_costs_by_facility():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Base query to get all relevant repairs within the date range
    repair_query = db.session.query(
        RepairLog.id,
        RepairLog.cost,
        Asset.id.label('asset_id'),
        Facility.name.label('facility_name')
    ).join(Asset).join(Room).join(Facility)

    repair_query = repair_query.filter(RepairLog.status == 'Completed')
    repair_query = apply_date_filter(repair_query, RepairLog.report_date, start_date_str, end_date_str)

    repairs = repair_query.all()

    # --- PROCESS THE DATA IN PYTHON ---

    facility_data = {}
    for repair in repairs:
        if repair.facility_name not in facility_data:
            facility_data[repair.facility_name] = {'cost': 0, 'frequency': 0, 'asset_ids': set()}

        facility_data[repair.facility_name]['cost'] += (repair.cost or 0)
        facility_data[repair.facility_name]['frequency'] += 1
        facility_data[repair.facility_name]['asset_ids'].add(repair.asset_id)

    # Sort by total cost
    sorted_facilities = sorted(facility_data.items(), key=lambda item: item[1]['cost'], reverse=True)

    labels = [item[0] for item in sorted_facilities]
    costs = [item[1]['cost'] for item in sorted_facilities]
    frequencies = [item[1]['frequency'] for item in sorted_facilities]
    # Convert sets of IDs to lists for JSON serialization
    asset_id_lists = [list(item[1]['asset_ids']) for item in sorted_facilities]

    return jsonify({
        'labels': labels,
        'costs': costs,
        'frequencies': frequencies,
        'asset_ids': asset_id_lists
    })

@reports_bp.route('/data/asset_age_distribution')
@login_required
def data_asset_age_distribution():
    base_query = get_base_asset_query()
    today = date.today()

    # Define age brackets using a `case` statement.
    # This tells the database how to categorize each asset based on its purchase_date.
    age_brackets = case(
        (Asset.purchase_date > (today - relativedelta(years=1)), "< 1 Year"),
        (Asset.purchase_date > (today - relativedelta(years=2)), "1-2 Years"),
        (Asset.purchase_date > (today - relativedelta(years=3)), "2-3 Years"),
        (Asset.purchase_date > (today - relativedelta(years=4)), "3-4 Years"),
        (Asset.purchase_date > (today - relativedelta(years=5)), "4-5 Years"),
        else_="5+ Years"
    ).label("age_bracket")

    # The main query
    results = base_query.with_entities(
        age_brackets,
        func.count(Asset.id)
    ).filter(
        Asset.purchase_date != None  # Exclude assets without a purchase date
    ).group_by(
        "age_bracket"
    ).order_by(
        "age_bracket"
    ).all()
    # Ensure a consistent order for the labels
    ordered_labels = ["< 1 Year", "1-2 Years", "2-3 Years", "3-4 Years", "4-5 Years", "5+ Years"]
    data_dict = dict(results)

    # Map the query results to the ordered labels, defaulting to 0 if a bracket has no assets
    ordered_data = [data_dict.get(label, 0) for label in ordered_labels]

    return jsonify({'labels': ordered_labels, 'data': ordered_data})

@reports_bp.route('/assets/explorer')
@login_required
def asset_data_explorer():
    # This route just renders the layout. The content is loaded via JavaScript.
    return render_template('reports/asset_data_explorer.html', title="Asset Data Explorer")



# --- PARTIAL ROUTES FOR DYNAMIC TABLES ---
@reports_bp.route('/partial/high_risk_assets')
@login_required
def partial_high_risk_assets():
    # Base query already handles role-based filtering
    base_query = get_base_asset_query()

    # Define thresholds
    REPAIR_COUNT_THRESHOLD = 3
    REPAIR_COST_PERCENTAGE_THRESHOLD = 0.50 # 50%


    high_risk_assets = base_query.join(Asset.repairs) \
        .group_by(Asset.id) \
        .having(
        db.or_(
            func.count(RepairLog.id) > REPAIR_COUNT_THRESHOLD,
            func.sum(RepairLog.cost) > (Asset.purchase_cost * REPAIR_COST_PERCENTAGE_THRESHOLD)
        )
    ).all()

    return render_template('reports/_table_high_risk.html', high_risk_assets=high_risk_assets)

@reports_bp.route('/partial/warranty_expiring')
@login_required
def partial_warranty_expiring():
    all_assets_in_scope = get_base_asset_query().all()
    expiring_soon_assets = [asset for asset in all_assets_in_scope if asset.warranty_status == 'Expiring Soon']
    return render_template('reports/_table_warranty.html', assets=expiring_soon_assets, report_title="Assets with Warranties Expiring Soon")

@reports_bp.route('/partial/warranty_expired')
@login_required
def partial_warranty_expired():
    all_assets_in_scope = get_base_asset_query().all()
    expired_assets = [asset for asset in all_assets_in_scope if asset.warranty_status == 'Expired']
    return render_template('reports/_table_warranty.html', assets=expired_assets, report_title="Assets with Expired Warranties")

@reports_bp.route('/partial/movement_history')
@login_required
def partial_movement_history():
    # For movement history, we query the log directly
    # and then check if the asset is in the user's scope.
    user_asset_ids = {asset.id for asset in get_base_asset_query().all()}
    movement_logs = MovementLog.query.order_by(MovementLog.movement_date.desc()).all()
    # Filter the logs in Python
    filtered_logs = [log for log in movement_logs if log.asset_id in user_asset_ids]
    return render_template('reports/_table_movement_history.html', movement_logs=filtered_logs)

@reports_bp.route('/partial/ownership_history')
@login_required
def partial_ownership_history():
    user_asset_ids = {asset.id for asset in get_base_asset_query().all()}
    ownership_logs = OwnershipLog.query.order_by(OwnershipLog.change_date.desc()).all()
    filtered_logs = [log for log in ownership_logs if log.asset_id in user_asset_ids]
    return render_template('reports/_table_ownership_history.html', ownership_logs=filtered_logs)


@reports_bp.route('/partial/repair_cost_analysis')
@login_required
def partial_repair_cost_analysis():
    # This query joins Assets with their repairs and uses conditional aggregation.
    assets_with_costs = get_base_asset_query() \
        .join(Asset.repairs) \
        .with_entities(
        Asset,
        # Total cost (ignores cancelled repairs in the sum)
        func.coalesce(func.sum(case((RepairLog.status != 'Cancelled', RepairLog.cost), else_=0)), 0.0).label(
            'total_cost'),

        # Total number of repair logs (all statuses)
        func.count(RepairLog.id).label('total_repair_count'),

        # --- NEW: Count only 'Completed' repairs ---
        func.sum(case((RepairLog.status == 'Completed', 1), else_=0)).label('completed_repair_count'),

        # --- NEW: Get the most recent 'completed_date' ---
        func.max(RepairLog.completed_date).label('last_completed_date')
    ) \
        .group_by(Asset.id) \
        .order_by(func.sum(RepairLog.cost).desc()) \
        .all()

    return render_template('reports/_table_repair_cost_analysis.html', assets_with_costs=assets_with_costs)

@reports_bp.route('/partial/assets_proposed_retirement')
@login_required
def partial_assets_proposed_retirement():
    assets = get_base_asset_query().filter(Asset.status == 'Proposed for Retirement').all()
    return render_template('reports/_table_end_of_life.html', assets=assets, report_title="Assets Proposed for Retirement")

@reports_bp.route('/partial/assets_retired')
@login_required
def partial_assets_retired():
    assets = get_base_asset_query().filter(Asset.status == 'Retired').all()
    return render_template('reports/_table_end_of_life.html', assets=assets, report_title="Retired Assets")

@reports_bp.route('/partial/assets_lost')
@login_required
def partial_assets_lost():
    assets = get_base_asset_query().filter(Asset.status == 'Lost').all()
    return render_template('reports/_table_end_of_life.html', assets=assets, report_title="Lost Assets")


@reports_bp.route('/data/consumption_by_facility')
@login_required
def data_consumption_by_facility():
    """
    API endpoint for consumption by facility.
    Calculates NET consumption for both bar heights and tooltip details.
    """
    # --- 1. GET FILTERS ---
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    consumable_id = request.args.get('consumable_id', type=int)

    # --- 2. DEFINE THE NET QUANTITY CALCULATION ---

    net_quantity = func.sum(
        case(
            (ConsumableIssuanceLog.transaction_type == 'Issue', ConsumableIssuanceLog.quantity),
            (ConsumableIssuanceLog.transaction_type == 'Return', -ConsumableIssuanceLog.quantity),
            else_=0
        )
    ).label('net_quantity')

    # --- 3. RUN THE MAIN QUERY FOR BOTH CHART AND TOOLTIP DATA ---
    # We can now get everything we need in a single, powerful query.
    query = db.session.query(
        Facility.name.label('facility_name'),
        ConsumableStock.item_type,
        ConsumableStock.make,
        ConsumableStock.model,
        Asset.asset_tag,
        Staff.name.label('owner_name'),
        net_quantity  # Use our net calculation here
    ).select_from(ConsumableIssuanceLog) \
        .join(Asset, ConsumableIssuanceLog.issued_for_asset_id == Asset.id) \
        .join(Room, Asset.room_id == Room.id) \
        .join(Facility, Room.facility_id == Facility.id) \
        .join(ConsumableStock, ConsumableIssuanceLog.consumable_id == ConsumableStock.id) \
        .outerjoin(Staff, Asset.owner_id == Staff.id)

    # Apply filters
    query = apply_date_filter(query, ConsumableIssuanceLog.issued_date, start_date_str, end_date_str)
    if consumable_id:
        query = query.filter(ConsumableIssuanceLog.consumable_id == consumable_id)

    # Group by all the descriptive fields to get the net quantity for each unique issuance type
    issuance_data = query.group_by(
        'facility_name', ConsumableStock.id, Asset.id, 'owner_name'
    ).all()

    # --- 4. PROCESS DATA IN PYTHON ---
    facility_summary = {}
    for row in issuance_data:
        # Skip any results where the net quantity is zero or less
        if row.net_quantity <= 0:
            continue

        if row.facility_name not in facility_summary:
            facility_summary[row.facility_name] = {'total': 0, 'details': []}

        # Add the net quantity for this specific item to the facility's total
        facility_summary[row.facility_name]['total'] += row.net_quantity

        # Build the detailed tooltip string using the calculated net quantity
        owner = row.owner_name or 'Unassigned'
        detail_string = (
                f"{row.net_quantity} x {row.item_type} ({row.make or ''} {row.model or ''})".strip() +
                f" for {row.asset_tag} ({owner})"
        )
        facility_summary[row.facility_name]['details'].append(detail_string)

    # Sort by facility name
    sorted_facilities = sorted(facility_summary.items(), key=lambda item: item[0])

    # --- 5. PREPARE FINAL JSON RESPONSE ---
    labels = [item[0] for item in sorted_facilities]
    data = [item[1]['total'] for item in sorted_facilities]
    tooltip_details = [item[1]['details'] for item in sorted_facilities]

    return jsonify({
        'labels': labels,
        'data': data,
        'tooltip_details': tooltip_details
    })

@reports_bp.route('/data/top_moving_consumables')
@login_required
def data_top_moving_consumables():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # --- CONDITIONAL SUM ---
    net_issued = func.sum(
        case(
            (ConsumableIssuanceLog.transaction_type == 'Issue', ConsumableIssuanceLog.quantity),
            (ConsumableIssuanceLog.transaction_type == 'Return', -ConsumableIssuanceLog.quantity),
            else_=0
        )
    ).label('net_issued')

    # Base query
    query = db.session.query(
        ConsumableStock.item_type,
        ConsumableStock.make,
        ConsumableStock.model,
        net_issued
    ).join(ConsumableStock, ConsumableIssuanceLog.consumable_id == ConsumableStock.id)

    # Apply the date filter
    query = apply_date_filter(query, ConsumableIssuanceLog.issued_date, start_date_str, end_date_str)

    # Group, order, and limit the results based on the net amount
    top_items = query.group_by(ConsumableStock.id) \
        .order_by(net_issued.desc()) \
        .limit(10).all()

    labels = [f"{item.item_type} ({item.make or ''} {item.model or ''})".strip() for item in top_items]
    data = [item.net_issued for item in top_items]

    return jsonify({'labels': labels, 'data': data})

#consumables slicer
@reports_bp.route('/data/search_consumable_stock')
@login_required
def data_search_consumable_stock():
    search_query = request.args.get('q', '').strip()
    query = ConsumableStock.query
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(db.or_(
            ConsumableStock.item_type.like(search_term),
            ConsumableStock.make.like(search_term),
            ConsumableStock.model.like(search_term)
        ))

    consumables = query.order_by(ConsumableStock.item_type).limit(20).all()
    results = [
        {'value': c.id, 'label': f"{c.item_type} - {c.make} {c.model}"}
        for c in consumables
    ]
    return jsonify(results)


@reports_bp.route('/data/stock_vs_reorder')
@login_required
def data_stock_vs_reorder():
    # Show top 10 items closest to their reorder level
    stock_levels = ConsumableStock.query.order_by(
        (ConsumableStock.qty_in_stock - ConsumableStock.reorder_level)
    ).limit(10).all()

    labels = [f"{s.item_type} ({s.make})" for s in stock_levels]
    stock_data = [s.qty_in_stock for s in stock_levels]
    reorder_data = [s.reorder_level for s in stock_levels]

    return jsonify({'labels': labels, 'stock_data': stock_data, 'reorder_data': reorder_data})


# --- CONSUMABLE DATA EXPLORER PARTIAL ROUTES ---

@reports_bp.route('/partial/consumable_issuance_log')
@login_required
def partial_consumable_issuance_log():
    logs = ConsumableIssuanceLog.query.order_by(ConsumableIssuanceLog.issued_date.desc())
    return render_template('reports/_table_consumable_issuance_log.html', logs=logs)


@reports_bp.route('/partial/consumable_stock_levels')
@login_required
def partial_consumable_stock_levels():
    stock = ConsumableStock.query.order_by(ConsumableStock.category, ConsumableStock.item_type).all()
    return render_template('reports/_table_consumable_stock_levels.html', stock=stock)

@reports_bp.route('/partial/asset_consumption_log') # Renamed for clarity
@login_required
def partial_asset_consumption_log():
    # This query fetches the full, detailed log.
    # join all related tables to get the descriptive names.
    logs = db.session.query(
        ConsumableIssuanceLog, # Select the whole log object
        Asset,
        ConsumableStock,
        User
    ).select_from(ConsumableIssuanceLog)\
     .join(Asset, ConsumableIssuanceLog.issued_for_asset_id == Asset.id)\
     .join(ConsumableStock, ConsumableIssuanceLog.consumable_id == ConsumableStock.id)\
     .join(User, ConsumableIssuanceLog.issued_by_user_id == User.id)\
     .order_by(Asset.asset_tag, ConsumableIssuanceLog.issued_date.desc())\
     .all()

    return render_template('reports/_table_asset_consumption_log.html', logs=logs)


@reports_bp.route('/consumables/explorer')
@login_required
def consumable_data_explorer():
    return render_template('reports/consumable_data_explorer.html', title="Consumable Data Explorer")


@reports_bp.route('/data/repair_outcomes_monthly')
@login_required
def data_repair_outcomes_monthly():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    query = db.session.query(
        func.strftime('%Y-%m', RepairLog.updated_date).label('month'),

        # Count completed repairs
        func.sum(case((RepairLog.status == 'Completed', 1), else_=0)).label('completed_count'),

        # Count cancelled repairs
        func.sum(case((RepairLog.status == 'Cancelled', 1), else_=0)).label('cancelled_count'),

        # Sum cost of ONLY completed repairs
        func.sum(case((RepairLog.status == 'Completed', RepairLog.cost), else_=0)).label('total_cost'),

        # Get IDs for completed repairs
        func.group_concat(case((RepairLog.status == 'Completed', RepairLog.id), else_=None)).label('completed_ids_str'),

        # Get IDs for cancelled repairs
        func.group_concat(case((RepairLog.status == 'Cancelled', RepairLog.id), else_=None)).label('cancelled_ids_str')

    ).filter(
        RepairLog.status.in_(['Completed', 'Cancelled'])
    )

    # Apply the date filter to the single, authoritative date column
    query = apply_date_filter(query, RepairLog.updated_date, start_date_str, end_date_str)

    results = query.group_by('month').order_by('month').all()

    # --- PROCESS THE DATA (now much simpler) ---
    labels = [row.month for row in results]
    completed_data = [row.completed_count for row in results]
    cancelled_data = [row.cancelled_count for row in results]
    completed_costs = [float(row.total_cost or 0) for row in results]

    # group_concat can return None, so we handle that
    completed_ids = [row.completed_ids_str or '' for row in results]
    cancelled_ids = [row.cancelled_ids_str or '' for row in results]

    return jsonify({
        'labels': labels,
        'completed_data': completed_data,
        'cancelled_data': cancelled_data,
        'completed_ids': completed_ids,
        'cancelled_ids': cancelled_ids,
        'completed_costs': completed_costs
    })