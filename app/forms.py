from datetime import date
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, DateField, FloatField, IntegerField, TextAreaField, HiddenField
from wtforms.validators import InputRequired, DataRequired, Length, Email, EqualTo, Optional, Regexp, NumberRange, \
    ValidationError, disabled
from wtforms_sqlalchemy.fields import QuerySelectField
from app.models import Asset, User, RepairLog, AssetCategory

# --- Helper function for the QuerySelectField ---
def category_query():
    return AssetCategory.query.order_by(AssetCategory.name)

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class AssetForm(FlaskForm):
    id = HiddenField('id')
    asset_tag = StringField('Asset Tag', validators=[DataRequired()])
    category = SelectField('Category', coerce=int, validators=[DataRequired()])
    make_model = StringField('Make/Model',validators=[DataRequired()])
    specs = TextAreaField('Specifications', validators=[Optional()])
    processor_type = StringField('Processor (Core)', validators=[Optional()])
    processor_speed = StringField('Processor Speed', validators=[Optional()])
    ram_size = StringField('RAM Size', validators=[Optional()])
    storage_size = StringField('Storage Size', validators=[Optional()])
    storage_type = SelectField('Storage Type', choices=[('', ''), ('SSD', 'SSD'), ('HDD', 'HDD')],
                               validators=[Optional()])
    serial_number = StringField('Serial Number',validators=[DataRequired()])
    purchase_date = DateField('Purchase Date', format='%Y-%m-%d', validators=[DataRequired()])

    def validate_purchase_date(self, field):
        if field.data and field.data > date.today():
            raise ValidationError("Purchase date cannot be in the future.")

    warranty_period = IntegerField('Warranty (Months)',
                                   validators=[Optional(), NumberRange(min=0, message="Warranty cannot be negative.")])
    purchase_cost = FloatField('Purchase Cost',
                               validators=[Optional(), NumberRange(min=0, message="Cost cannot be negative.")])
    #owner_id = SelectField('Asset Owner (Assigned To)', coerce=int, validators=[DataRequired()])
    owner_id = SelectField('Asset Owner (Assigned To)', coerce=int, validators=[
        NumberRange(min=1, message="Please select a valid staff member.")
    ])
    status = SelectField('Status', choices=Asset.MANUAL_STATUS_CHOICES, validators=[DataRequired()])
    status_readonly = StringField('Status', render_kw={'readonly': True, 'class': 'form-control-plaintext'})
    disposal_notes = TextAreaField('Reason for Retirement/Loss', validators=[Optional(), Length(max=1000)])
    room_id = SelectField('Location (Room)', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save Asset')
    supplier_id = SelectField('Purchased From (Vendor/Supplier)', coerce=int, validators=[Optional()])
    department = SelectField('Department', choices=Asset.DEPARTMENT_CHOICES, validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        self.original_asset = kwargs.pop('original_asset', None)
        self.original_status = kwargs.pop('original_status', None)
        super(AssetForm, self).__init__(*args, **kwargs)

    def validate_asset_tag(self, asset_tag):
        query = Asset.query.filter(func.lower(Asset.asset_tag) == func.lower(asset_tag.data))
        if self.original_asset: # Use the ID
            query = query.filter(Asset.id != self.original_asset.id)
        if query.first():
            raise ValidationError('This Asset Tag is already in use.')

    def validate_serial_number(self, serial_number):
        if serial_number.data:
            query = Asset.query.filter(func.lower(Asset.serial_number) == func.lower(serial_number.data))
            if self.original_asset: # Use the ID
                query = query.filter(Asset.id != self.original_asset.id)
            if query.first():
                raise ValidationError('This Serial Number is already in use by another asset.')

    def validate_status(self, field):
        """Custom validator for the status field."""
        # This validator is automatically called by form.validate()
        new_status = field.data

        # Rule 1: You cannot move an asset to 'Retired' unless it was already 'Proposed for Retirement'
        if new_status == 'Retired' and self.original_status != 'Proposed for Retirement':
            raise ValidationError("An asset must be 'Proposed for Retirement' before it can be retired.")

        # Rule 2: You cannot change the status FROM a locked state
        if self.original_status in Asset.LOCKED_STATUSES:
            if new_status != self.original_status:
                raise ValidationError(
                    f"This asset is already '{self.original_status}' and its status cannot be changed.")

    def validate(self, extra_validators=None):
        initial_validation = super(AssetForm, self).validate(extra_validators)
        if not initial_validation:
            return False

        has_errors = False

        # We need to look up the category object to get its name.
        category_name = None
        if self.category.data:
            category_obj = AssetCategory.query.get(self.category.data)
            if category_obj:
                category_name = category_obj.name

        # Rule 1: Conditional validation for computer specs
        if category_name in ['Laptop', 'Desktop']:
            if not self.processor_type.data:
                self.processor_type.errors.append('Processor is required for this category.')
                has_errors = True
            if not self.ram_size.data:
                self.ram_size.errors.append('RAM is required for this category.')
                has_errors = True
            if not self.storage_size.data:
                self.storage_size.errors.append('Storage Size is required for this category.')
                has_errors = True
            if not self.storage_type.data:
                self.storage_type.errors.append('Storage Type is required for this category.')
                has_errors = True

        # Rule 2: Conditional validation for the generic specs field
        elif category_name and category_name not in ['Laptop', 'Desktop']:
            if not self.specs.data:
                self.specs.errors.append('Specifications are required for this category.')
                has_errors = True

        # Rule 3: Existing validation for disposal notes
        end_of_life_statuses = ['Proposed for Retirement', 'Retired', 'Lost']
        if self.status.data in end_of_life_statuses:
            if not self.disposal_notes.data:
                self.disposal_notes.errors.append('A reason is required for this status.')
                has_errors = True

        return not has_errors

class MoveAssetForm(FlaskForm):
    to_room = SelectField('Move to Location', coerce=int, validators=[
        NumberRange(min=1, message="Please select a valid location.")
    ])
    new_owner = SelectField('New Asset Owner', coerce=int, validators=[DataRequired()])
    reason = StringField('Reason for Movement', validators=[DataRequired(), Length(max=200)])
    submit = SubmitField('Move Asset')

    def __getstate__(self):
        # This method is called by pickle. It removes the non-pickleable
        # parts of the form before saving to the session.
        state = self.__dict__.copy()
        for key, field in state['_fields'].items():
            if hasattr(field, 'query'):
                del field.query
        return state

class InitialRepairForm(FlaskForm):
    """Form for initially logging a problem."""
    problem_description = TextAreaField('Problem Description', validators=[DataRequired()])
    submit = SubmitField('Log Repair Issue')


class UpdateRepairForm(FlaskForm):
    """Form for updating a repair log with resolution details."""
    problem_description = TextAreaField('Problem Description', validators=[DataRequired()],
                                        render_kw={'readonly': True})
    cost = FloatField('Repair Cost', validators=[Optional(), NumberRange(min=0)])
    technician = SelectField('Technician', coerce=int, validators=[Optional()])
    replaced_parts = TextAreaField('Replaced Parts')
    cancellation_reason = TextAreaField('Reason for Cancellation', validators=[
        Optional(),
        Length(max=500)
    ])
    status = SelectField('Repair Status', choices=RepairLog.STATUS_CHOICES, validators=[DataRequired()])
    submit = SubmitField('Update Repair Log')

    def validate(self, extra_validators=None):
        # Perform standard validation first
        initial_validation = super(UpdateRepairForm, self).validate(extra_validators)
        if not initial_validation:
            return False
        has_errors = False

        # Custom validation: If status is 'Completed', other fields are mandatory
        if self.status.data == 'Completed':
            if not self.cost.data or self.cost.data <= 0:
                self.cost.errors.append('Cost is required to complete a repair.')
                has_errors = True
            if not self.technician.data or self.technician.data == 0:
                self.technician.errors.append('Technician is required to complete a repair.')
                has_errors = True


        if self.status.data == 'Cancelled':
            if not self.cancellation_reason.data:
                self.cancellation_reason.errors.append('A reason is required to cancel a repair.')
                has_errors = True

        return not has_errors


from app.models import Facility
def facility_query():
    return Facility.query

class SearchForm(FlaskForm):
    class Meta:
        csrf = False
    q = StringField('Search', render_kw={"placeholder": "Search..."})
    status = SelectField('Status', choices=[('', 'All Statuses')] + Asset.STATUS_CHOICES,
                         validators=[], default='')
    category = QuerySelectField('Category', query_factory=category_query, get_label='name', allow_blank=True,
                                blank_text='All Categories')
    facility = QuerySelectField('Facility', query_factory=facility_query, get_label='name',
                                allow_blank=True, blank_text='All Facilities')
    submit = SubmitField('Filter')


# --- ADMIN FORMS ---
class FacilityForm(FlaskForm):
    name = StringField('Facility Name', validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('Save Facility')

class RoomForm(FlaskForm):
    name = StringField('Room Name', validators=[DataRequired(), Length(max=100)])
    # We use a standard SelectField and will populate its choices in the route
    facility = SelectField('Parent Facility', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Save Room')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    role = SelectField('Role', choices=[
        ('Super Admin', 'Super Admin'),
        ('Branch Manager', 'Branch Manager'),
        ('Store Manager', 'Store Manager'),
        ('Department Manager', 'Department Manager'),
        ('Finance', 'Finance')
    ], validators=[DataRequired()])

    department = SelectField('Managed Department', choices=[('0', '-- Select a Department --')] + Asset.DEPARTMENT_CHOICES, validators=[Optional()])
    facility = SelectField('Managed Facility (if Branch Manager)', coerce=int, validators=[Optional()])
    password = PasswordField('Password', validators=[
        Optional(),
        EqualTo('password2', message='Passwords must match.')
    ])
    password2 = PasswordField('Confirm Password')
    submit = SubmitField('Save User')

class VendorForm(FlaskForm):
    name = StringField('Vendor Name', validators=[DataRequired(), Length(max=150)])
    contact_person = StringField('Contact Person', validators=[Optional(), Length(max=150)])
    phone_number = StringField('Phone Number', validators=[
        DataRequired(),
        Length(max=20),
        Regexp(r'^[0-9\s\+\-\(\)]+$', message="Invalid characters in phone number.")
    ])
    submit = SubmitField('Save Vendor')

class TechnicianForm(FlaskForm):
    name = StringField('Technician/Company Name', validators=[DataRequired(), Length(max=150)])
    contact_person = StringField('Contact Person', validators=[Optional(), Length(max=150)])
    phone_number = StringField('Phone Number', validators=[
        DataRequired(),
        Length(max=20),
        Regexp(r'^[0-9\s\+\-\(\)]+$', message="Invalid characters in phone number.")
    ])
    submit = SubmitField('Save Technician')

class ConsumableStockForm(FlaskForm):
    category = StringField('Category (e.g., Input Device, Storage)', validators=[DataRequired(), Length(max=100)])
    item_type = StringField('Item Type (e.g., Mouse, SSD)', validators=[DataRequired(), Length(max=100)])
    make = StringField('Make', validators=[Optional(), Length(max=100)])
    model = StringField('Model', validators=[Optional(), Length(max=100)])
    qty_in_stock = IntegerField('Quantity in Stock', validators=[DataRequired(), NumberRange(min=0)])
    reorder_level = IntegerField('Reorder Level', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Save Consumable')

class IssueConsumableForm(FlaskForm):
    consumable_id = SelectField('Consumable Item',coerce=int ,validators=[DataRequired(), NumberRange(min=1, message="Please select a valid consumable.")])
    quantity = IntegerField('Quantity to Issue', default=1, validators=[DataRequired(), NumberRange(min=1)])
    issued_for_asset_id = SelectField('Link to Asset', coerce=int,validators=[DataRequired(),NumberRange(min=1, message="Please select a valid asset.")])
    submit = SubmitField('Issue Consumable')


class AssetCategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired(), Length(max=100)])
    submit = SubmitField('Save Category')

    def validate_name(self, name):
        # Check for uniqueness, ignoring case
        existing_category = AssetCategory.query.filter(func.lower(AssetCategory.name) == func.lower(name.data)).first()
        if existing_category:
            raise ValidationError('An asset category with this name already exists.')

class ReturnConsumableForm(FlaskForm):
    quantity = IntegerField('Quantity to Return', validators=[DataRequired(), NumberRange(min=1)])
    notes = TextAreaField('Reason for Return', validators=[DataRequired(), Length(max=500)])
    submit = SubmitField('Confirm Return')

class StaffForm(FlaskForm):
    name = StringField('Staff Name', validators=[DataRequired(), Length(max=150)])
    submit = SubmitField('Save Staff Member')