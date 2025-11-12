import csv
import io
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from flask import render_template, flash, redirect, url_for, Blueprint, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Facility, Room, Vendor, RepairLog, Asset, Technician, ConsumableStock, AssetCategory, Staff
from app.forms import UserForm, FacilityForm, RoomForm, VendorForm, UpdateRepairForm, TechnicianForm, ConsumableStockForm, AssetCategoryForm, StaffForm
from app.decorators import role_required
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
@login_required
@role_required('Super Admin')
def before_request():
    """Protects all admin routes."""
    pass


# --- User Management ---
@admin_bp.route('/users')
def list_users():
    users = User.query.order_by(User.username).all()
    return render_template('admin/list_users.html', users=users, title="Manage Users")


@admin_bp.route('/user/add', methods=['GET', 'POST'])
def add_user():
    form = UserForm()
    facilities = Facility.query.order_by(Facility.name).all()
    form.facility.choices = [('0', '-- Not Applicable --')] + [(f.id, f.name) for f in facilities]
    if form.validate_on_submit():
        has_errors = False
        # Custom uniqueness validation
        if User.query.filter_by(username=form.username.data).first():
            form.username.errors.append('Username is already taken.')
            has_errors = True
        if User.query.filter_by(email=form.email.data).first():
            form.email.errors.append('Email is already in use.')
            has_errors = True

        # If the role is Department Manager, the department field becomes mandatory.
        if form.role.data == 'Department Manager' and form.department.data == 0:
            form.department.errors.append('Please select a department for this role.')
            has_errors = True

        if not has_errors:
            user = User(username=form.username.data, email=form.email.data, role=form.role.data)
            if form.password.data:
                user.set_password(form.password.data)

            # Simplified saving logic
            user.facility_id = form.facility.data if form.role.data == 'Branch Manager' and form.facility.data else None
            # Convert '0' to None, otherwise save the department name from the form choices
            if form.role.data == 'Department Manager' and form.department.data:
                user.department = dict(form.department.choices).get(form.department.data)
            else:
                user.department = None

            db.session.add(user)
            db.session.commit()
            flash('User created successfully!', 'success')
            return redirect(url_for('admin.list_users'))

    return render_template('admin/user_form.html', form=form, title="Add New User")


@admin_bp.route('/user/edit/<int:id>', methods=['GET', 'POST'])
def edit_user(id):
    user = User.query.get_or_404(id)
    form = UserForm(obj=user)
    facilities = Facility.query.order_by(Facility.name).all()
    form.facility.choices = [('0', '-- Select a Branch --')] + [(f.id, f.name) for f in facilities]

    if form.validate_on_submit():
        has_errors = False
        # Custom uniqueness validation
        if User.query.filter(User.username == form.username.data, User.id != id).first():
            form.username.errors.append('Username is already taken by another user.')
            has_errors = True
        if User.query.filter(User.email == form.email.data, User.id != id).first():
            form.email.errors.append('Email is already in use by another user.')
            has_errors = True


        if form.role.data == 'Department Manager' and form.department.data == 0:
            form.department.errors.append('Please select a department for this role.')
            has_errors = True

        if not has_errors:
            user.username = form.username.data
            user.email = form.email.data
            user.role = form.role.data
            if form.password.data:
                user.set_password(form.password.data)

            user.facility_id = form.facility.data if form.role.data == 'Branch Manager' and form.facility.data else None
            if form.role.data == 'Department Manager' and form.department.data:
                user.department = dict(form.department.choices).get(form.department.data)
            else:
                user.department = None

            db.session.commit()
            flash('User updated successfully!', 'success')
            return redirect(url_for('admin.list_users'))

    # On GET request, pre-populate the form correctly
    if request.method == 'GET':
        form.facility.data = user.facility_id or 0
        # Find the integer key for the department name
        if user.department:
            dept_choices_dict = {text: key for key, text in form.department.choices}
            form.department.data = dept_choices_dict.get(user.department, 0)

    return render_template('admin/user_form.html', form=form, title="Edit User")


@admin_bp.route('/user/delete/<int:id>', methods=['POST'])
def delete_user(id):
    if id == current_user.id:
        flash("You cannot delete your own account.", 'danger')
        return redirect(url_for('admin.list_users'))
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    flash('User has been deleted successfully.', 'success')
    return redirect(url_for('admin.list_users'))


# --- Facility & Room Management ---
@admin_bp.route('/locations')
def list_locations():
    facilities = Facility.query.order_by(Facility.name).all()
    return render_template('admin/list_locations.html', facilities=facilities, title="Manage Locations")


@admin_bp.route('/facility/add', methods=['GET', 'POST'])
def add_facility():
    form = FacilityForm()
    if form.validate_on_submit():
        facility_name = form.name.data.strip()  # Remove leading/trailing whitespace

        # Check if a facility with this name already exists (case-insensitive check is more robust)
        existing_facility = Facility.query.filter(func.lower(Facility.name) == func.lower(facility_name)).first()

        if existing_facility:
            flash(f'A facility named "{facility_name}" already exists.', 'danger')
        else:
            facility = Facility(name=facility_name)
            db.session.add(facility)
            db.session.commit()
            flash('Facility added successfully.', 'success')
            return redirect(url_for('admin.list_locations'))

    return render_template('admin/facility_form.html', form=form, title="Add Facility")


@admin_bp.route('/facility/edit/<int:id>', methods=['GET', 'POST'])
def edit_facility(id):
    facility = Facility.query.get_or_404(id)
    form = FacilityForm(obj=facility)
    if form.validate_on_submit():
        new_name = form.name.data.strip()

        # Check if ANOTHER facility (with a different ID) already has this name
        existing_facility = Facility.query.filter(
            func.lower(Facility.name) == func.lower(new_name),
            Facility.id != id
        ).first()

        if existing_facility:
            flash(f'A facility named "{new_name}" already exists.', 'danger')
        else:
            facility.name = new_name
            db.session.commit()
            flash('Facility updated successfully.', 'success')
            return redirect(url_for('admin.list_locations'))

    return render_template('admin/facility_form.html', form=form, title="Edit Facility")


@admin_bp.route('/room/add', methods=['GET', 'POST'])
def add_room():
    form = RoomForm()
    # Manually populate facility choices
    facilities = Facility.query.order_by(Facility.name).all()
    form.facility.choices = [(f.id, f.name) for f in facilities]

    if form.validate_on_submit():
        # --- VALIDATION BLOCK ---
        room_name = form.name.data.strip()
        facility_id = form.facility.data

        # Check if a room with this name already exists in this facility
        existing_room = Room.query.filter(func.lower(Room.name)==func.lower(room_name), Room.facility_id==facility_id).first()

        if existing_room:
            flash(f'A room named "{room_name}" already exists in the selected facility.', 'danger')
        else:
            # ---  VALIDATION BLOCK ---
            room = Room(name=room_name, facility_id=facility_id)
            db.session.add(room)
            db.session.commit()
            flash('Room added.', 'success')
            #return redirect(url_for('admin.list_locations'))

    return render_template('admin/room_form.html', form=form, title="Add Room")


@admin_bp.route('/room/edit/<int:id>', methods=['GET', 'POST'])
def edit_room(id):
    room = Room.query.get_or_404(id)
    form = RoomForm(obj=room)
    facilities = Facility.query.order_by(Facility.name).all()
    form.facility.choices = [(f.id, f.name) for f in facilities]

    if form.validate_on_submit():
        # --- VALIDATION BLOCK ---
        room_name = form.name.data.strip()
        facility_id = form.facility.data

        # Check if another room (with a different ID) has this name in this facility
        existing_room = Room.query.filter(
            func.lower(Room.name) == func.lower(room_name),
            Room.facility_id == facility_id,
            Room.id != id  # Exclude the current room from the check
        ).first()

        if existing_room:
            flash(f'A room named "{room_name}" already exists in the selected facility.', 'danger')
        else:
            # --- END OF VALIDATION BLOCK ---
            room.name = room_name
            room.facility_id = facility_id
            db.session.commit()
            flash('Room updated.', 'success')
            #return redirect(url_for('admin.list_locations'))

    if request.method == 'GET':
        form.facility.data = room.facility_id

    return render_template('admin/room_form.html', form=form, title="Edit Room")

@admin_bp.route('/location/delete/<string:type>/<int:id>', methods=['POST'])
def delete_location(type, id):
    if type == 'facility':
        loc = Facility.query.get_or_404(id)
        # Check if the facility contains any rooms before deleting
        if loc.rooms.first():
            flash('Cannot delete facility. It contains rooms. Please delete or reassign the rooms first.', 'danger')
            return redirect(url_for('admin.list_locations'))
    elif type == 'room':
        loc = Room.query.get_or_404(id)
        # Check if the room contains any assets before deleting
        if loc.assets.first():
            flash('Cannot delete room. It contains assets. Please move the assets first.', 'danger')
            return redirect(url_for('admin.list_locations'))
    else:
        # Failsafe for an invalid type in the URL
        flash('Invalid location type specified.', 'danger')
        return redirect(url_for('admin.list_locations'))

    db.session.delete(loc)
    db.session.commit()
    flash(f'{type.capitalize()} has been deleted.', 'success')
    return redirect(url_for('admin.list_locations'))

@admin_bp.route('/repairs')
def manage_repairs():
    repair_ids_str = request.args.get('repair_ids', type=str)

    query = RepairLog.query.filter(RepairLog.status.notin_(['Completed', 'Cancelled']))

    if repair_ids_str:
        try:

            repair_ids = [int(id) for id in repair_ids_str.split(',')]
            query = RepairLog.query.filter(RepairLog.id.in_(repair_ids))
        except (ValueError, TypeError):
            flash('Invalid repair ID filter provided.', 'warning')
            # Fall back to the default query
            pass

    repairs = query.order_by(RepairLog.report_date.desc()).all()
    # Add a dynamic title for the page
    page_title = "Filtered Repair Log" if repair_ids_str else "Manage Active Repairs"

    return render_template('admin/manage_repairs.html', repairs=repairs, title=page_title)

#Route to edit a specific repair log
@admin_bp.route('/repair/edit/<int:id>', methods=['GET', 'POST'])
def edit_repair(id):
    repair = RepairLog.query.get_or_404(id)
    form = UpdateRepairForm(obj=repair)

    # Populate the technician dropdown
    technicians = Technician.query.order_by(Technician.name).all()
    form.technician.choices = [('0', '-- Select a Technician --')] + [(t.id, t.name) for t in technicians]

    if form.validate_on_submit():

        new_status = form.status.data
        old_status = repair.status
        repair.cost = form.cost.data
        repair.technician_id = form.technician.data if form.technician.data else None
        repair.replaced_parts = form.replaced_parts.data
        repair.cancellation_reason = form.cancellation_reason.data

        # Special handling for cancellation
        if new_status == 'Cancelled':
            repair.cost = 0.0
            repair.completed_date = None

        # If the status is changing TO 'Completed'
        if new_status == 'Completed' and old_status != 'Completed':
            repair.completed_date = datetime.utcnow()  # Set the completion timestamp

        # If the status is changing AWAY from 'Completed' (e.g., reopened to 'In Progress')
        elif old_status == 'Completed' and new_status != 'Completed':
            repair.completed_date = None  # Clear the timestamp

        # Handle status change and its effect on the parent Asset
        if old_status != new_status:
            repair.status = new_status
            asset = repair.asset
            if new_status == 'In Progress':
                asset.status = 'In Repair'
            elif new_status == 'Completed' or new_status == 'Cancelled':
                asset.status = 'In Use' if 'Central Store' not in asset.room.facility.name else 'In Storage'

        db.session.commit()
        flash(f"Repair log for '{repair.asset.asset_tag}' has been updated.", 'success')
        return redirect(url_for('admin.manage_repairs'))

    if request.method == 'GET':
        form.technician.data = repair.technician_id or 0

    return render_template('admin/edit_repair.html', form=form, repair=repair, title="Update Repair Log")


@admin_bp.route('/import_assets', methods=['GET', 'POST'])
def import_assets():
    if request.method == 'POST':
        if 'file' not in request.files or not request.files['file'].filename:
            flash('No file selected.', 'danger')
            return redirect(request.url)

        file = request.files['file']
        if not file.filename.endswith('.csv'):
            flash('Invalid file type. Please upload a CSV file.', 'danger')
            return redirect(request.url)

        try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            csv_reader = csv.reader(stream)
            headers = [h.strip() for h in next(csv_reader)]
            dict_reader = csv.DictReader(stream, fieldnames=headers)

            assets_to_add = []
            errors = []

            for i, row in enumerate(dict_reader):
                line_num = i + 2
                try:
                    # --- CORE VALIDATION ---
                    required_fields = ['asset_tag', 'category', 'status', 'assigned_to', 'department',
                                       'location_room_name', 'location_facility_name']
                    missing_fields = [f for f in required_fields if not row.get(f)]
                    if missing_fields:
                        raise ValueError(f"Missing required columns: {', '.join(missing_fields)}")

                    if Asset.query.filter_by(asset_tag=row['asset_tag']).first():
                        raise ValueError(f"Asset tag '{row['asset_tag']}' already exists.")

                    room = Room.query.join(Facility).filter(Facility.name == row['location_facility_name'],
                                                            Room.name == row['location_room_name']).first()
                    if not room:
                        raise ValueError(
                            f"Location not found: {row['location_facility_name']} - {row['location_room_name']}")
                    # --- VALIDATE THE ASSIGNED_TO FIELD ---
                    owner_name = row.get('assigned_to')
                    if not owner_name:
                        raise ValueError("The 'assigned_to' column cannot be empty.")

                    owner_obj = Staff.query.filter(func.lower(Staff.name) == func.lower(owner_name)).first()
                    if not owner_obj:
                        raise ValueError(
                            f"Staff member (owner) '{owner_name}' not found. Please add them to the Staff list first.")

                    # --- CATEGORY LOOKUP ---
                    category_name = row.get('category')
                    category_obj = AssetCategory.query.filter(
                        func.lower(AssetCategory.name) == func.lower(category_name)).first()
                    if not category_obj:
                        raise ValueError(f"Asset Category '{category_name}' not found. Please create it first.")

                    # --- CONDITIONAL SPECS VALIDATION ---
                    computer_categories = ['Laptop', 'Desktop']
                    if category_name in computer_categories:
                        computer_req_fields = ['processor_type', 'ram_size', 'storage_size', 'storage_type']
                        missing_spec_fields = [f for f in computer_req_fields if not row.get(f)]
                        if missing_spec_fields:
                            raise ValueError(
                                f"Missing computer specs for '{category_name}': {', '.join(missing_spec_fields)}")
                    else:
                        if not row.get('specs'):
                            raise ValueError(
                                f"The 'specs' column is required for non-computer category '{category_name}'.")

                    # --- DATA PARSING ---
                    supplier_id = None
                    if row.get('supplier_name'):
                        supplier = Vendor.query.filter(
                            func.lower(Vendor.name) == func.lower(row.get('supplier_name'))).first()
                        if supplier:
                            supplier_id = supplier.id
                        else:
                            # Create new supplier if it doesn't exist
                            new_supplier = Vendor(name=row.get('supplier_name').strip(), phone_number='N/A')
                            db.session.add(new_supplier)
                            db.session.flush()  # Flush to get the ID before committing
                            supplier_id = new_supplier.id

                    purchase_date = datetime.strptime(row['purchase_date'], '%Y-%m-%d').date() if row.get(
                        'purchase_date') else None
                    purchase_cost = float(row['purchase_cost']) if row.get('purchase_cost') else None
                    warranty_period = int(row['warranty_period']) if row.get('warranty_period') else None


                    asset = Asset(
                        asset_tag=row['asset_tag'],
                        category_id=category_obj.id,
                        status=row['status'],
                        department=row['department'],
                        owner_id=owner_obj.id,
                        room_id=room.id,
                        supplier_id=supplier_id,
                        make_model=row.get('make_model'),
                        serial_number=row.get('serial_number'),
                        purchase_date=purchase_date,
                        purchase_cost=purchase_cost,
                        warranty_period=warranty_period,
                        processor_type=row.get('processor_type'),
                        processor_speed=row.get('processor_speed'),
                        ram_size=row.get('ram_size'),
                        storage_size=row.get('storage_size'),
                        storage_type=row.get('storage_type'),
                        specs=row.get('specs')
                    )
                    assets_to_add.append(asset)

                except Exception as e:
                    errors.append(f"Row {line_num}: {str(e)}")

            if errors:
                db.session.rollback()
                flash(f"Import failed. {len(errors)} error(s) found. No assets were imported.", 'danger')
                for e in errors:
                    flash(e, 'danger')
            else:
                db.session.add_all(assets_to_add)
                db.session.commit()
                flash(f"Successfully imported {len(assets_to_add)} new assets!", 'success')

        except Exception as e:
            db.session.rollback()
            flash(f"A critical error occurred: {str(e)}", 'danger')

        return redirect(url_for('admin.import_assets'))

    return render_template('admin/import_assets.html', title="Import Assets")


# --- UNIFIED VENDOR & TECHNICIAN MANAGEMENT ---
@admin_bp.route('/suppliers')
def manage_suppliers():
    vendors = Vendor.query.order_by(Vendor.name).all()
    technicians = Technician.query.order_by(Technician.name).all()
    return render_template('admin/manage_suppliers.html', vendors=vendors, technicians=technicians, title="Manage Suppliers & Technicians")

# --- Vendor (Supplier) CRUD ---
@admin_bp.route('/vendor/add', methods=['GET', 'POST'])
def add_vendor():
    form = VendorForm()
    if form.validate_on_submit():
        # Standard validation has passed. Now, check for uniqueness.
        name_taken = Vendor.query.filter_by(name=form.name.data).first()
        phone_taken = Vendor.query.filter_by(phone_number=form.phone_number.data).first()

        has_errors = False
        if name_taken:
            form.name.errors.append('A supplier with this name already exists.')
            has_errors = True
        if phone_taken:
            form.phone_number.errors.append('This phone number is already registered.')
            has_errors = True

        # Only proceed to save if there are NO custom errors
        if not has_errors:
            vendor = Vendor(name=form.name.data, contact_person=form.contact_person.data,
                            phone_number=form.phone_number.data)
            db.session.add(vendor)
            db.session.commit()
            flash('Supplier added successfully!', 'success')
            return redirect(url_for('admin.manage_suppliers'))


    return render_template('admin/vendor_form.html', form=form, title="Add New Supplier")


@admin_bp.route('/vendor/edit/<int:id>', methods=['GET', 'POST'])
def edit_vendor(id):
    vendor = Vendor.query.get_or_404(id)
    form = VendorForm(obj=vendor)

    if form.validate_on_submit():
        # Check for uniqueness, excluding the current object itself
        name_taken = Vendor.query.filter(Vendor.name == form.name.data, Vendor.id != id).first()
        phone_taken = Vendor.query.filter(Vendor.phone_number == form.phone_number.data, Vendor.id != id).first()

        has_errors = False
        if name_taken:
            form.name.errors.append('Another supplier already has this name.')
            has_errors = True
        if phone_taken:
            form.phone_number.errors.append('Another supplier already has this phone number.')
            has_errors = True

        if not has_errors:
            # Populate the vendor object from the form data
            vendor.name = form.name.data
            vendor.contact_person = form.contact_person.data
            vendor.phone_number = form.phone_number.data
            db.session.commit()
            flash('Supplier updated successfully!', 'success')
            return redirect(url_for('admin.manage_suppliers'))

    return render_template('admin/vendor_form.html', form=form, title="Edit Supplier")

@admin_bp.route('/vendor/delete/<int:id>', methods=['POST'])
def delete_vendor(id):
    vendor = Vendor.query.get_or_404(id)
    if vendor.supplied_assets:
        flash('Cannot delete supplier. They are associated with existing assets.', 'danger')
    else:
        db.session.delete(vendor)
        db.session.commit()
        flash('Supplier deleted.', 'success')
    return redirect(url_for('admin.manage_suppliers'))

# --- Technician CRUD ---
@admin_bp.route('/technician/add', methods=['GET', 'POST'])
def add_technician():
    form = TechnicianForm()

    # checking for a POST request and running validation.
    if form.validate_on_submit():
        # Standard validation has passed. Now, check for uniqueness.
        name_taken = Technician.query.filter_by(name=form.name.data).first()
        phone_taken = Technician.query.filter_by(phone_number=form.phone_number.data).first()

        has_errors = False
        if name_taken:
            form.name.errors.append('A technician or company with this name already exists.')
            has_errors = True
        if phone_taken:
            form.phone_number.errors.append('This phone number is already registered.')
            has_errors = True

        # Only proceed to save if there are NO custom errors
        if not has_errors:
            technician = Technician(name=form.name.data, contact_person=form.contact_person.data,
                                    phone_number=form.phone_number.data)
            db.session.add(technician)
            db.session.commit()
            flash('Technician added successfully!', 'success')
            return redirect(url_for('admin.manage_suppliers', _anchor='technicians-tab-pane'))

    # The template will be re-rendered with the form, including any error messages.
    return render_template('admin/technician_form.html', form=form, title="Add New Technician")


@admin_bp.route('/technician/edit/<int:id>', methods=['GET', 'POST'])
def edit_technician(id):
    technician = Technician.query.get_or_404(id)
    form = TechnicianForm(obj=technician)

    if form.validate_on_submit():
        # Check for uniqueness, excluding the current object itself
        name_taken = Technician.query.filter(Technician.name == form.name.data, Technician.id != id).first()
        phone_taken = Technician.query.filter(Technician.phone_number == form.phone_number.data,
                                              Technician.id != id).first()

        has_errors = False
        if name_taken:
            form.name.errors.append('Another technician already has this name.')
            has_errors = True
        if phone_taken:
            form.phone_number.errors.append('Another technician already has this phone number.')
            has_errors = True

        if not has_errors:
            # We must populate the technician object from the form data
            technician.name = form.name.data
            technician.contact_person = form.contact_person.data
            technician.phone_number = form.phone_number.data
            db.session.commit()
            flash('Technician updated successfully!', 'success')
            return redirect(url_for('admin.manage_suppliers', _anchor='technicians-tab-pane'))


    return render_template('admin/technician_form.html', form=form, title="Edit Technician")


@admin_bp.route('/technician/delete/<int:id>', methods=['POST'])
def delete_technician(id):
    technician = Technician.query.get_or_404(id)
    if technician.repairs.first():
        flash('Cannot delete technician. They are associated with existing repair logs.', 'danger')
    else:
        db.session.delete(technician)
        db.session.commit()
        flash('Technician deleted.', 'success')
    return redirect(url_for('admin.manage_suppliers', _anchor='technicians-tab-pane'))


# --- STOCK MANAGEMENT ---
@admin_bp.route('/consumables')
@role_required('Super Admin', 'Store Manager')
def manage_consumables():
    stock = ConsumableStock.query.order_by(ConsumableStock.category, ConsumableStock.item_type).all()
    return render_template('admin/manage_consumables.html', stock=stock, title="Manage Consumable Stock")


@admin_bp.route('/consumable/add', methods=['GET', 'POST'])
@role_required('Super Admin', 'Store Manager')
def add_consumable():
    form = ConsumableStockForm()
    if form.validate_on_submit():

        # Check if an identical consumable already exists
        existing_consumable = ConsumableStock.query.filter_by(
            category=func.lower(form.category.data.strip()),
            item_type=func.lower(form.item_type.data.strip()),
            make=func.lower(form.make.data.strip()) ,  # Handle empty strings
            model=func.lower(form.model.data.strip())
        ).first()

        if existing_consumable:
            flash(
                'This exact consumable (Category, Type, Make, and Model) already exists in stock. Please edit the existing entry instead.',
                'danger')
        else:
            # --- END OF VALIDATION ---
            consumable = ConsumableStock(
                category=form.category.data.strip(),
                item_type=form.item_type.data.strip(),
                make=form.make.data.strip() or None,
                model=form.model.data.strip() or None,
                qty_in_stock=form.qty_in_stock.data,
                reorder_level=form.reorder_level.data
            )
            db.session.add(consumable)
            db.session.commit()
            flash('New consumable has been added to stock.', 'success')
            return redirect(url_for('admin.manage_consumables'))

    return render_template('admin/consumable_form.html', form=form, title="Add New Consumable")


@admin_bp.route('/consumable/edit/<int:id>', methods=['GET', 'POST'])
@role_required('Super Admin', 'Store Manager')
def edit_consumable(id):
    consumable = ConsumableStock.query.get_or_404(id)
    form = ConsumableStockForm(obj=consumable)
    if form.validate_on_submit():
        # ---  VALIDATION for the EDIT action ---
        existing_consumable = ConsumableStock.query.filter(
            func.lower(ConsumableStock.category) == func.lower(form.category.data.strip()),
            func.lower(ConsumableStock.item_type) == func.lower(form.item_type.data.strip()),
            func.lower(ConsumableStock.make) == func.lower((form.make.data.strip() or None)),
            func.lower(ConsumableStock.model)== func.lower((form.model.data.strip() or None)),
            ConsumableStock.id != id  # Exclude the current item from the check
        ).first()

        if existing_consumable:
            flash('Another consumable with this exact combination of Category, Type, Make, and Model already exists.',
                  'danger')
        else:
            # --- END OF VALIDATION ---
            consumable.category = form.category.data.strip()
            consumable.item_type = form.item_type.data.strip()
            consumable.make = form.make.data.strip() or None
            consumable.model = form.model.data.strip() or None
            consumable.qty_in_stock = form.qty_in_stock.data
            consumable.reorder_level = form.reorder_level.data
            db.session.commit()
            flash('Consumable stock updated successfully.', 'success')
            return redirect(url_for('admin.manage_consumables'))

    return render_template('admin/consumable_form.html', form=form, title="Edit Consumable")


@admin_bp.route('/consumable/delete/<int:id>', methods=['POST'])
@role_required('Super Admin', 'Store Manager')
def delete_consumable(id):
    consumable = ConsumableStock.query.get_or_404(id)

    # Check if there are any issuance logs linked to this stock item.
    # The `issuances` backref is defined in the ConsumableIssuanceLog model.
    if consumable.issuances:
        flash(
            f'Cannot delete "{consumable.item_type} - {consumable.make} {consumable.model}". It is associated with one or more issuance logs.',
            'danger')
    else:
        db.session.delete(consumable)
        db.session.commit()
        flash(
            f'Consumable stock item "{consumable.item_type} - {consumable.make} {consumable.model}" has been deleted.',
            'success')

    return redirect(url_for('admin.manage_consumables'))

@admin_bp.route('/assets/archived')
@role_required('Super Admin')
def archived_assets():
    assets = Asset.query.filter(Asset.is_archived == True).order_by(Asset.asset_tag).all()
    return render_template('admin/archived_assets.html', assets=assets, title="Archived Assets")


@admin_bp.route('/asset/archive/<int:id>', methods=['POST','GET'])
@role_required('Super Admin')
def archive_asset(id):
    asset = Asset.query.get_or_404(id)
    asset.is_archived = True
    db.session.commit()
    flash(f"Asset '{asset.asset_tag}' has been archived.", 'success')
    return redirect(url_for('main.assets')) # Redirect back to the main asset list

@admin_bp.route('/asset/restore/<int:id>', methods=['POST','GET'])
@role_required('Super Admin')
def restore_asset(id):
    asset = Asset.query.get_or_404(id)
    asset.is_archived = False
    db.session.commit()
    flash(f"Asset '{asset.asset_tag}' has been restored.", 'success')
    return redirect(url_for('admin.archived_assets')) # Stay on the archive page

@admin_bp.route('/asset/delete_permanent/<int:id>', methods=['POST','GET'])
@role_required('Super Admin')
def delete_asset_permanent(id):
    asset = Asset.query.get_or_404(id)
    db.session.delete(asset)
    db.session.commit()
    flash(f"Asset '{asset.asset_tag}' has been permanently deleted.", 'warning')
    return redirect(url_for('admin.archived_assets'))

# --- ASSET CATEGORY MANAGEMENT ---
@admin_bp.route('/categories')
@role_required('Super Admin')
def list_categories():
    categories = AssetCategory.query.order_by(AssetCategory.name).all()
    return render_template('admin/list_categories.html', categories=categories, title="Manage Asset Categories")


@admin_bp.route('/category/add', methods=['GET', 'POST'])
@role_required('Super Admin')
def add_category():
    form = AssetCategoryForm()
    # The validate_name method in the form handles the uniqueness check
    if form.validate_on_submit():
        new_category = AssetCategory(name=form.name.data.strip())
        db.session.add(new_category)
        db.session.commit()
        flash('New asset category created successfully.', 'success')
        return redirect(url_for('admin.list_categories'))
    return render_template('admin/generic_form.html', form=form, title="Add New Category", form_width='col-md-6')


@admin_bp.route('/category/edit/<int:id>', methods=['GET', 'POST'])
@role_required('Super Admin')
def edit_category(id):
    category = AssetCategory.query.get_or_404(id)
    form = AssetCategoryForm(obj=category)


    if form.validate_on_submit():
        new_name = form.name.data.strip()
        # Check if another category already has this name
        existing_category = AssetCategory.query.filter(
            func.lower(AssetCategory.name) == func.lower(new_name),
            AssetCategory.id != id
        ).first()

        if existing_category:
            form.name.errors.append('An asset category with this name already exists.')
        else:
            category.name = new_name
            db.session.commit()
            flash('Asset category updated successfully.', 'success')
            return redirect(url_for('admin.list_categories'))

    return render_template('admin/generic_form.html', form=form, title="Edit Category", form_width='col-md-6')


@admin_bp.route('/category/delete/<int:id>', methods=['POST'])
@role_required('Super Admin')
def delete_category(id):
    category = AssetCategory.query.get_or_404(id)
    # Safety check: prevent deletion if the category is in use
    if category.assets.first():
        flash('Cannot delete category. It is currently in use by one or more assets.', 'danger')
    else:
        db.session.delete(category)
        db.session.commit()
        flash('Asset category deleted successfully.', 'success')
    return redirect(url_for('admin.list_categories'))

# --- STAFF MANAGEMENT ---
@admin_bp.route('/staff')
@role_required('Super Admin')
def list_staff():
    staff_members = Staff.query.order_by(Staff.name).all()
    return render_template('admin/list_staff.html', staff_list=staff_members, title="Manage Staff")

@admin_bp.route('/staff/add', methods=['GET', 'POST'])
@role_required('Super Admin')
def add_staff():
    form = StaffForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if Staff.query.filter(func.lower(Staff.name) == func.lower(name)).first():
            flash('A staff member with this name already exists.', 'danger')
        else:
            new_staff = Staff(name=name)
            db.session.add(new_staff)
            db.session.commit()
            flash('New staff member added successfully.', 'success')
            return redirect(url_for('admin.list_staff'))
    return render_template('admin/generic_form.html', form=form, title="Add New Staff Member", back_url=url_for('admin.list_staff'), form_width='col-md-6')

@admin_bp.route('/staff/edit/<int:id>', methods=['GET', 'POST'])
@role_required('Super Admin')
def edit_staff(id):
    staff_member = Staff.query.get_or_404(id)
    form = StaffForm(obj=staff_member)
    if form.validate_on_submit():
        new_name = form.name.data.strip()
        existing_staff = Staff.query.filter(func.lower(Staff.name) == func.lower(new_name), Staff.id != id).first()
        if existing_staff:
            flash('Another staff member already has this name.', 'danger')
        else:
            staff_member.name = new_name
            db.session.commit()
            flash('Staff member updated successfully.', 'success')
            return redirect(url_for('admin.list_staff'))
    return render_template('admin/generic_form.html', form=form, title="Edit Staff Member", back_url=url_for('admin.list_staff'), form_width='col-md-6')

@admin_bp.route('/staff/delete/<int:id>', methods=['POST'])
@role_required('Super Admin')
def delete_staff(id):
    staff_member = Staff.query.get_or_404(id)
    if staff_member.assets.first():
        flash('Cannot delete staff member. They are currently assigned to one or more assets.', 'danger')
    else:
        db.session.delete(staff_member)
        db.session.commit()
        flash('Staff member deleted successfully.', 'success')
    return redirect(url_for('admin.list_staff'))


@admin_bp.route('/import_staff', methods=['GET', 'POST'])
@role_required('Super Admin')
def import_staff():
    if request.method == 'POST':
        if 'file' not in request.files or not request.files['file'].filename:
            flash('No file selected.', 'danger')
            return redirect(request.url)

        file = request.files['file']
        if not file.filename.endswith('.csv'):
            flash('Invalid file type. Please upload a CSV file.', 'danger')
            return redirect(request.url)

        try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            csv_reader = csv.reader(stream)
            headers = [h.strip().lower() for h in next(csv_reader)]

            if 'name' not in headers:
                flash("Import failed. CSV file must contain a 'name' column.", 'danger')
                return redirect(url_for('admin.import_staff'))

            staff_to_add = []
            errors = []

            # Get existing names to check for duplicates efficiently
            existing_names = {s.name.lower() for s in Staff.query.all()}

            for i, row in enumerate(csv_reader):
                line_num = i + 2
                if not row: continue  # Skip empty rows

                name = row[headers.index('name')].strip()

                if not name:
                    errors.append(f"Row {line_num}: Name cannot be empty.")
                    continue

                if name.lower() in existing_names:
                    errors.append(f"Row {line_num}: Staff member '{name}' already exists.")
                    continue

                staff_to_add.append(Staff(name=name))
                existing_names.add(name.lower())  # Add to set to catch duplicates within the same file

            if errors:
                db.session.rollback()
                flash(f"Import failed with {len(errors)} error(s). No staff members were imported.", 'danger')
                for e in errors:
                    flash(e, 'danger')
            else:
                db.session.add_all(staff_to_add)
                db.session.commit()
                flash(f"Successfully imported {len(staff_to_add)} new staff members!", 'success')

        except Exception as e:
            db.session.rollback()
            flash(f"A critical error occurred during file processing: {str(e)}", 'danger')

        return redirect(url_for('admin.import_staff'))

    return render_template('admin/import_staff.html', title="Import Staff")