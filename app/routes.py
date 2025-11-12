from flask import render_template, flash, redirect, url_for, request, Blueprint, Response, session
from flask_login import login_required, current_user
from app import db
from app.models import Asset, Facility, Room, MovementLog, RepairLog, Vendor, User, ConsumableStock, ConsumableIssuanceLog, AssetConsumableLink, OwnershipLog, AssetCategory, Staff, Vendor, Technician
from app.forms import AssetForm, MoveAssetForm, InitialRepairForm, UpdateRepairForm, SearchForm, IssueConsumableForm, ReturnConsumableForm
from app.decorators import role_required


from flask import jsonify
import csv
import io
import pickle

bp = Blueprint('main', __name__)


def populate_asset_form_choices(form):
    """Populates the choices for all dynamic dropdowns in the AssetForm."""

    # Add the logic for populating categories
    form.category.choices = [(c.id, c.name) for c in AssetCategory.query.order_by(AssetCategory.name).all()]

    form.room_id.choices = [(r.id, f"{r.facility.name} - {r.name}") for r in
                            Room.query.join(Facility).order_by(Facility.name, Room.name).all()]
    form.supplier_id.choices = [('0', 'Unknown')] + [(v.id, v.name) for v in Vendor.query.order_by(Vendor.name).all()]

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    # This ensures the dashboard stats are relevant to the logged-in user
    base_asset_query = Asset.query.filter(Asset.is_archived == False)
    if current_user.role == 'Branch Manager':
        base_asset_query = base_asset_query.join(Room).filter(Room.facility_id == current_user.facility_id)
    elif current_user.role == 'Department Manager':
        base_asset_query = base_asset_query.filter(Asset.department == current_user.department)

    # Get all assets within the user's scope for Python-based filtering
    all_assets_in_scope = base_asset_query.all()

    # Calculate main dashboard stats
    total_assets = len(all_assets_in_scope)
    assets_awaiting_repair = sum(1 for asset in all_assets_in_scope if asset.status == 'Awaiting Repair')
    assets_in_repair = sum(1 for asset in all_assets_in_scope if asset.status == 'In Repair')
    proposed_for_retirement = sum(1 for asset in all_assets_in_scope if asset.status == 'Proposed for Retirement')
    retired_assets = sum(1 for asset in all_assets_in_scope if asset.status == 'Retired')
    lost_assets = sum(1 for asset in all_assets_in_scope if asset.status == 'Lost')


    # Calculate warranty stats
    expiring_soon_count = sum(1 for asset in all_assets_in_scope if asset.warranty_status == "Expiring Soon")
    expired_count = sum(1 for asset in all_assets_in_scope if asset.warranty_status == "Expired")
    # Calculate low stock items
    low_stock_items = ConsumableStock.query.filter(
        ConsumableStock.qty_in_stock <= ConsumableStock.reorder_level).count()
    return render_template('index.html',
                           title='Dashboard',
                           total_assets=total_assets,
                           assets_awaiting_repair=assets_awaiting_repair,
                           proposed_for_retirement=proposed_for_retirement,
                           assets_in_repair=assets_in_repair,
                           retired_assets=retired_assets,
                           lost_assets = lost_assets,
                           low_stock_items=low_stock_items,
                           expiring_soon_count=expiring_soon_count, expired_count=expired_count)

@bp.route('/locations')
@login_required
def locations():
    # Role-based filtering
    if current_user.role == 'Branch Manager':
        facilities = Facility.query.filter_by(id=current_user.facility_id).order_by(Facility.name).all()
    else:
        facilities = Facility.query.order_by(Facility.name).all()
    return render_template('locations.html', title='Locations', facilities=facilities)


@bp.route('/assets')
@login_required
def assets():
    # --- 1. GET ALL FILTER PARAMETERS FROM URL ---
    search_query = request.args.get('q', default="", type=str).strip()
    selected_status = request.args.get('status', default="", type=str)
    selected_tag = request.args.get('asset_tag', default="", type=str)
    selected_department = request.args.get('department', default="", type=str)
    selected_facility_id = request.args.get('facility_id', default=None, type=int)
    selected_category_id = request.args.get('category_id', default=None, type=int)  # New category filter

    # Drill-down specific filters
    selected_facility_name = request.args.get('facility_name', default="", type=str)
    asset_ids_str = request.args.get('asset_ids', default="", type=str)

    # --- 2. SETUP BASE QUERY & ROLE-BASED FILTERING ---
    query = Asset.query.filter(Asset.is_archived == False)

    if current_user.role == 'Branch Manager':
        query = query.join(Room).filter(Room.facility_id == current_user.facility_id)
        facilities_for_dropdown = Facility.query.filter_by(id=current_user.facility_id).all()
    elif current_user.role == 'Department Manager':
        query = query.filter(Asset.department == current_user.department)
        facilities_for_dropdown = Facility.query.order_by(Facility.name).all()
    else:
        facilities_for_dropdown = Facility.query.order_by(Facility.name).all()

    # Get all categories for the dropdown
    categories_for_dropdown = AssetCategory.query.order_by(AssetCategory.name).all()

    # --- 3. APPLY ALL FILTERS ---
    if asset_ids_str:
        try:
            asset_ids = [int(id) for id in asset_ids_str.split(',')]
            query = query.filter(Asset.id.in_(asset_ids))
        except (ValueError, TypeError):
            flash('Invalid asset ID filter provided.', 'warning')

    if search_query:
        search_term = f"%{search_query}%"
        query = query.outerjoin(AssetCategory).outerjoin(Staff, Asset.owner_id == Staff.id).filter(db.or_(
            Asset.asset_tag.like(search_term),
            AssetCategory.name.like(search_term),
            Asset.make_model.like(search_term),
            Asset.serial_number.like(search_term),
            Staff.name.like(search_term)
        ))

    if selected_status:
        query = query.filter(Asset.status == selected_status)
    if selected_tag:
        query = query.filter(Asset.asset_tag == selected_tag)
    if selected_department:
        query = query.filter(Asset.department == selected_department)
    if selected_facility_id:
        query = query.join(Room).filter(Room.facility_id == selected_facility_id)
    if selected_category_id:
        query = query.filter(Asset.category_id == selected_category_id)

    if selected_facility_name:
        query = query.join(Room).join(Facility).filter(Facility.name == selected_facility_name)

    # --- 4. PREPARE FOR TEMPLATE ---
    pagination_args = request.args.copy()
    pagination_args.pop('page', None)

    page = request.args.get('page', 1, type=int)
    asset_list = query.order_by(Asset.asset_tag).paginate(page=page, per_page=15)

    return render_template('assets.html',
                           title='All Assets',
                           assets=asset_list,
                           facilities=facilities_for_dropdown,
                           categories=categories_for_dropdown,  # Pass categories to template
                           status_choices=Asset.MANUAL_STATUS_CHOICES,  # Use manual list
                           department_choices=Asset.DEPARTMENT_CHOICES,
                           # Dictionary to pre-fill the form fields
                           search_values={
                               'q': search_query,
                               'status': selected_status,
                               'facility_id': selected_facility_id,
                               'department': selected_department,
                               'category_id': selected_category_id
                           },
                           pagination_args=pagination_args)




@bp.route('/asset/<int:id>', methods=['GET', 'POST'])
@login_required
def asset_detail(id):
    asset = Asset.query.get_or_404(id)
    initial_repair_form = InitialRepairForm()
    return_form = ReturnConsumableForm()  # For the return consumable modal

    # --- MOVE/REASSIGN FORM HANDLING ---
    move_form = MoveAssetForm(formdata=None)  # Create empty form to prevent crash

    # Initialize choices with a placeholder to be safe
    move_form.to_room.choices = [('0', '-- Select a New Location --')]
    move_form.new_owner.choices = [('0', '-- Select a New Owner --')]

    # On a POST request, we  manually add the submitted choices back
    # to the form's choices list BEFORE validation. This is the key fix.
    if request.method == 'POST':
        # Handle the 'to_room' dynamic field
        room_id = request.form.get('to_room')
        if room_id and room_id != '0':
            room = Room.query.get(room_id)
            if room:
                move_form.to_room.choices.append((room.id, f"{room.facility.name} - {room.name}"))

        # Handle the 'new_owner' dynamic field
        owner_id = request.form.get('new_owner')
        if owner_id and owner_id != '0':
            staff = Staff.query.get(owner_id)
            if staff:
                move_form.new_owner.choices.append((staff.id, staff.name))

    move_form.process(formdata=request.form)

    if request.method == 'POST' and move_form.submit.data and move_form.validate():
        # All validation passed, proceed with saving.
        previous_owner_id = asset.owner_id
        new_owner_id = move_form.new_owner.data

        from_room_id = asset.room_id
        new_room_id = move_form.to_room.data

        owner_changed = previous_owner_id != new_owner_id
        location_changed = from_room_id != new_room_id

        if location_changed or owner_changed:
            if location_changed:
                asset.room_id = new_room_id
                asset.status = 'In Use' if Room.query.get(
                    new_room_id).facility.name != 'Central Store' else 'In Storage'
                movement = MovementLog(
                    asset_id=asset.id, from_room_id=from_room_id,
                    to_room_id=new_room_id, reason=move_form.reason.data,
                    moved_by_user_id=current_user.id
                )
                db.session.add(movement)

            if owner_changed:
                asset.owner_id = new_owner_id
                ownership_log = OwnershipLog(
                    asset_id=asset.id,
                    previous_owner_id=previous_owner_id,
                    new_owner_id=new_owner_id,
                    changed_by_user_id=current_user.id
                )
                db.session.add(ownership_log)

            db.session.commit()
            flash('Asset has been updated successfully.', 'success')
        else:
            flash('No changes detected in location or owner.', 'info')

        return redirect(url_for('main.asset_detail', id=id))

    # --- DATA PREPARATION FOR DISPLAY (GET Request or Failed POST) ---

    # If it's a GET request, pre-populate the owner field for display in the form.

    if request.method == 'GET':
        move_form.new_owner.data = asset.owner_id or 0

    # Query for all history logs to display on the page
    ownership_logs = OwnershipLog.query.filter_by(asset_id=asset.id).order_by(OwnershipLog.change_date.desc()).all()
    movements = MovementLog.query.filter_by(asset_id=asset.id).order_by(MovementLog.movement_date.desc()).all()
    repairs = RepairLog.query.filter_by(asset_id=asset.id).order_by(RepairLog.report_date.desc()).all()

    return render_template('asset_detail.html',
                           title=f"Asset {asset.asset_tag}",
                           asset=asset,
                           movements=movements,
                           repairs=repairs,
                           ownership_logs=ownership_logs,
                           move_form=move_form,
                           initial_repair_form=initial_repair_form,
                           return_form=return_form)

@bp.route('/asset/new', methods=['GET', 'POST'])
@login_required
@role_required('Super Admin', 'Store Manager')
def new_asset():
    form = AssetForm(formdata=None)
    populate_asset_form_choices(form)
    form.owner_id.choices = []
    if request.method == 'POST':
        owner_id = request.form.get('owner_id')
        if owner_id:
            staff = Staff.query.get(owner_id)
            if staff:
                form.owner_id.choices.append((staff.id, staff.name))

    form.process(formdata=request.form)

    if request.method == 'POST' and form.validate():

        if Asset.query.filter_by(asset_tag=form.asset_tag.data).first():
            form.asset_tag.errors.append('This Asset Tag is already in use.')

        if not form.errors:
            asset = Asset(
                asset_tag=form.asset_tag.data,
                department=form.department.data,
                category_id=form.category.data,
                owner_id=form.owner_id.data,
                make_model=form.make_model.data,
                specs=form.specs.data,
                processor_type=form.processor_type.data,
                processor_speed=form.processor_speed.data,
                ram_size=form.ram_size.data,
                storage_size=form.storage_size.data,
                storage_type=form.storage_type.data,
                serial_number=form.serial_number.data,
                purchase_date=form.purchase_date.data,
                warranty_period=form.warranty_period.data,
                purchase_cost=form.purchase_cost.data,
                status=form.status.data,
                room_id=form.room_id.data,
                supplier_id=form.supplier_id.data if form.supplier_id.data and form.supplier_id.data != 0 else None,
                disposal_notes=form.disposal_notes.data
            )
            db.session.add(asset)
            db.session.commit()
            flash('New asset has been created successfully!', 'success')
            return redirect(url_for('main.asset_detail', id=asset.id))

    # If it's a GET request, apply default values
    if request.method == 'GET':
        default_room = Room.query.join(Facility).filter(Facility.name == "Central Store").first()
        if default_room:
            form.room_id.data = default_room.id

    # On a failed POST, the 'form' object already has the errors and user data.
    return render_template('asset_form.html',
                           title='New Asset',
                           form=form,
                           is_edit_mode=False,
                           asset=None)


@bp.route('/asset/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Super Admin', 'Store Manager')
def edit_asset(id):
    asset = Asset.query.get_or_404(id)

    form = AssetForm(original_asset=asset, original_status=asset.status)
    populate_asset_form_choices(form)

    if hasattr(form, 'owner_id'): del form.owner_id
    if hasattr(form, 'room_id'): del form.room_id

    # Determine which status field to show (read-only or editable)
    is_status_locked = asset.status in Asset.LOCKED_STATUSES
    is_repair_status = asset.status in ['Awaiting Repair', 'In Repair']

    if is_repair_status or is_status_locked:
        if hasattr(form, 'status'): del form.status
    else:
        if hasattr(form, 'status_readonly'): del form.status_readonly

    # --- POST REQUEST HANDLING (Form Submission) ---
    if form.validate_on_submit():

        asset.asset_tag = form.asset_tag.data
        asset.department = form.department.data
        asset.category_id = form.category.data
        asset.make_model = form.make_model.data
        asset.specs = form.specs.data
        asset.processor_type = form.processor_type.data
        asset.processor_speed = form.processor_speed.data
        asset.ram_size = form.ram_size.data
        asset.storage_size = form.storage_size.data
        asset.storage_type = form.storage_type.data
        asset.serial_number = form.serial_number.data
        asset.purchase_date = form.purchase_date.data
        asset.warranty_period = form.warranty_period.data
        asset.purchase_cost = form.purchase_cost.data
        asset.supplier_id = form.supplier_id.data if form.supplier_id.data and form.supplier_id.data != 0 else None
        asset.disposal_notes = form.disposal_notes.data

        # Only update status if it's not locked or managed by the repair workflow
        if not is_repair_status and not is_status_locked:
            asset.status = form.status.data

        db.session.commit()
        flash('Asset has been updated successfully!', 'success')
        return redirect(url_for('main.asset_detail', id=asset.id))


    elif request.method == 'GET':
        form.process(obj=asset)
        form.category.data = asset.category_id
        form.supplier_id.data = asset.supplier_id or 0
        if not (is_repair_status or is_status_locked):
            form.status.data = asset.status
        # Handle the conditional status field
        if is_repair_status or is_status_locked:
            form.status_readonly.data = asset.status
        else:
            form.status.data = asset.status

    return render_template('asset_form.html',
                           title='Edit Asset',
                           form=form,
                           asset=asset,
                           is_repair_status=is_repair_status,
                           is_status_locked=is_status_locked,
                           is_edit_mode=True)

@bp.route('/asset/<int:id>/add_repair', methods=['POST'])
@login_required
@role_required('Super Admin', 'Store Manager')
def add_repair(id):
    asset = Asset.query.get_or_404(id)
    form = InitialRepairForm()


    if form.validate_on_submit():
        repair = RepairLog(
            asset_id=asset.id,
            problem_description=form.problem_description.data,
            status='Pending'  # Default status
        )

        asset.status = 'Awaiting Repair'
        db.session.add(repair)
        db.session.commit()
        flash('Repair issue has been logged. Asset status set to Awaiting Repair.', 'success')
    else:
        # If form fails validation, flash errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')

    return redirect(url_for('main.asset_detail', id=id))


@bp.route('/data/search_rooms')
@login_required
def search_rooms():
    search_query = request.args.get('q', '').strip()
    query = Room.query.join(Facility)

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(db.or_(
            Room.name.like(search_term),
            Facility.name.like(search_term)
        ))

    rooms = query.order_by(Facility.name, Room.name).limit(20).all()
    results = [
        {'value': room.id, 'label': f"{room.facility.name} - {room.name}"}
        for room in rooms
    ]
    return jsonify(results)


@bp.route('/export/assets.csv')
@login_required
def export_assets():
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ['Asset Tag', 'Category', 'Make / Model', 'Serial Number', 'Purchase Date',
               'Warranty (Months)', 'Purchase Cost', 'Status', 'Facility', 'Room']
    writer.writerow(headers)

    for asset in Asset.query.all():
        row = [asset.asset_tag, asset.category.name, asset.make_model, asset.serial_number,
               asset.purchase_date, asset.warranty_period, asset.purchase_cost, asset.status,
               asset.room.facility.name if asset.room else '', asset.room.name if asset.room else '']
        writer.writerow(row)

    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=assets.csv"})


@bp.route('/consumables/issue', methods=['GET', 'POST'])
@login_required
@role_required('Super Admin', 'Store Manager')
def issue_consumable():
    form = IssueConsumableForm(formdata=None)

    # Use '0' as the value for the placeholder
    form.consumable_id.choices = [('0', '-- Type to search for a consumable --')]
    form.issued_for_asset_id.choices = [('0', '-- Type to search for an asset --')]

    if request.method == 'POST':
        consumable_id = request.form.get('consumable_id')
        if consumable_id and consumable_id != '0':
            consumable = ConsumableStock.query.get(consumable_id)
            if consumable:
                form.consumable_id.choices.append((consumable.id, consumable.item_type))

        asset_id = request.form.get('issued_for_asset_id')
        if asset_id and asset_id != '0':
            asset = Asset.query.get(asset_id)
            if asset:
                form.issued_for_asset_id.choices.append((asset.id, asset.asset_tag))

    # Now, process the actual form data
    form.process(formdata=request.form)

    if request.method == 'POST' and form.validate():
        # All validation, including our NumberRange, has passed.
        stock_item = ConsumableStock.query.get(form.consumable_id.data)
        issue_qty = form.quantity.data
        asset = Asset.query.get(form.issued_for_asset_id.data)

        if stock_item.qty_in_stock < issue_qty:
            flash(f'Not enough stock. Only {stock_item.qty_in_stock} available.', 'danger')
        else:
            stock_item.qty_in_stock -= issue_qty

            issuance_log = ConsumableIssuanceLog(
                consumable_id=stock_item.id,
                quantity=issue_qty,
                issued_for_asset_id=asset.id,
                issued_by_user_id=current_user.id
            )
            db.session.add(issuance_log)

            existing_link = AssetConsumableLink.query.filter_by(asset_id=asset.id, consumable_id=stock_item.id).first()
            if existing_link:
                existing_link.quantity += issue_qty
            else:
                asset_link = AssetConsumableLink(asset_id=asset.id, consumable_id=stock_item.id, quantity=issue_qty)
                db.session.add(asset_link)

            db.session.commit()

            owner_name = asset.owner.name if asset.owner else 'Unassigned'
            flash(f'Successfully issued {issue_qty} x {stock_item.item_type} for asset {asset.asset_tag} (Owner: {owner_name}).', 'success')
            return redirect(url_for('main.issue_consumable'))
    return render_template('issue_consumable.html', form=form, title="Issue Consumable")


@bp.route('/asset/<int:asset_id>/return_consumable/<int:link_id>', methods=['POST'])
@login_required
@role_required('Super Admin', 'Store Manager')
def return_consumable(asset_id, link_id):
    form = ReturnConsumableForm()
    link = AssetConsumableLink.query.get_or_404(link_id)

    # We must also validate the quantity being returned
    if form.validate_on_submit():
        return_qty = form.quantity.data
        if return_qty > link.quantity:
            flash('Cannot return more items than are linked to the asset.', 'danger')
        else:
            # 1. Increase the stock
            stock_item = link.consumable
            stock_item.qty_in_stock += return_qty

            # 2. Create a 'Return' log
            return_log = ConsumableIssuanceLog(
                consumable_id=stock_item.id,
                quantity=return_qty,
                issued_for_asset_id=asset_id,
                issued_by_user_id=current_user.id,
                transaction_type='Return',  # Set the new type
                notes=form.notes.data
            )
            db.session.add(return_log)

            # 3. Update or delete the asset link
            if return_qty == link.quantity:
                db.session.delete(link)  # If all are returned, delete the link
            else:
                link.quantity -= return_qty  # If only some are returned, decrease the quantity

            db.session.commit()
            flash('Consumable has been successfully returned to stock.', 'success')
    else:
        flash('A reason for the return is required.', 'danger')

    return redirect(url_for('main.asset_detail', id=asset_id))


# --- API FOR DYNAMIC ASSET SEARCH (when issuing consumable) ---
@bp.route('/data/search_assets')
@login_required
def search_assets():
    search_query = request.args.get('q', '').strip()


    query = Asset.query.filter(
        Asset.is_archived == False,
        Asset.status.notin_(['Retired', 'Lost'])
    )

    if search_query:
        search_term = f"%{search_query}%"

        query = query.outerjoin(Staff, Asset.owner_id == Staff.id).filter(db.or_(
            Asset.asset_tag.like(search_term),
            Asset.serial_number.like(search_term),
            Asset.make_model.like(search_term),
            Staff.name.like(search_term)  # Search by owner's name
        ))

    # Limit results for performance
    assets = query.order_by(Asset.asset_tag).limit(20).all()

    # Format the results into the structure that Choices.js expects: {value, label}
    results = [
        {
            'value': asset.id,
            'label': f"{asset.asset_tag} ({asset.owner.name if asset.owner else 'Unassigned'}) - {asset.make_model or ''}"
        }
        for asset in assets
    ]

    return jsonify(results)

@bp.route('/data/search_consumables')
@login_required
def search_consumables():
    search_query = request.args.get('q', '').strip()
    #query = ConsumableStock.query.filter(ConsumableStock.qty_in_stock > 0)  # Only show items in stock
    query = ConsumableStock.query # show all items in stock

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(db.or_(
            ConsumableStock.item_type.like(search_term),
            ConsumableStock.make.like(search_term),
            ConsumableStock.model.like(search_term),
            ConsumableStock.category.like(search_term)
        ))

    consumables = query.order_by(ConsumableStock.item_type).limit(20).all()

    results = [
        {'value': c.id, 'label': f"{c.item_type} - {c.make} {c.model} (In Stock: {c.qty_in_stock})"}
        for c in consumables
    ]

    return jsonify(results)


# --- API FOR DYNAMIC STAFF SEARCH ---
@bp.route('/data/search_staff')
@login_required
def search_staff():
    search_query = request.args.get('q', '').strip()
    query = Staff.query

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(Staff.name.like(search_term))

    staff_members = query.order_by(Staff.name).limit(20).all()

    results = [{'value': s.id, 'label': s.name} for s in staff_members]

    return jsonify(results)