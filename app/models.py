from enum import UNIQUE

from app import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, date
from dateutil.relativedelta import relativedelta


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False)  # 'Super Admin', 'Branch Manager', 'Store Manager', 'Finance'
    facility_id = db.Column(db.Integer, db.ForeignKey('facility.id'))  # For Branch Managers
    department = db.Column(db.String(50), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


class Facility(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True,
                     nullable=False)  # e.g., 'Central Store', 'General Hospital', 'Support Office'
    rooms = db.relationship('Room', backref='facility', lazy='dynamic')
    managers = db.relationship('User', backref='facility', lazy='dynamic')


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    facility_id = db.Column(db.Integer, db.ForeignKey('facility.id'), nullable=False)
    assets = db.relationship('Asset', backref='room', lazy='dynamic')
    # This tells the database that the combination of 'name' and 'facility_id' must be unique.
    __table_args__ = (db.UniqueConstraint('name', 'facility_id', name='_room_facility_uc'),)


class AssetCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    assets = db.relationship('Asset', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<AssetCategory {self.name}>'
class Asset(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    asset_tag = db.Column(db.String(50), unique=True, nullable=False)
    make_model = db.Column(db.String(50))
    specs = db.Column(db.Text) # This will be for non-computer items
    processor_type = db.Column(db.String(50), nullable=True)  # e.g., i5, i7, Ryzen 5
    processor_speed = db.Column(db.String(50), nullable=True) # e.g., 2.4GHz
    ram_size = db.Column(db.String(20), nullable=True)         # e.g., 8GB, 16GB
    storage_size = db.Column(db.String(20), nullable=True)    # e.g., 256GB, 1TB
    storage_type = db.Column(db.String(10), nullable=True)  # SSD or HDD
    serial_number = db.Column(db.String(100), unique=True)
    purchase_date = db.Column(db.Date)
    warranty_period = db.Column(db.Integer)
    purchase_cost = db.Column(db.Float)
    category_id = db.Column(db.Integer, db.ForeignKey('asset_category.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='In Storage', nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
    owner_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    supplier = db.relationship('Vendor', backref='supplied_assets', foreign_keys=[supplier_id])
    repairs = db.relationship('RepairLog', backref='asset', lazy='dynamic', cascade="all, delete-orphan")
    movements = db.relationship('MovementLog', backref='asset', lazy='dynamic', cascade="all, delete-orphan")
    department = db.Column(db.String(50), nullable=False, server_default='IT')
    disposal_notes = db.Column(db.Text, nullable=True)  # For Retirement/Lost reasons
    DEPARTMENT_CHOICES = [
        ('IT', 'IT'),
        ('Repairs and Maintenance', 'Repairs and Maintenance')
    ]
    STATUS_CHOICES = [
        ('In Storage', 'In Storage'),
        ('In Use', 'In Use'),
        ('Awaiting Repair', 'Awaiting Repair'),
        ('In Repair', 'In Repair'),
        ('Proposed for Retirement', 'Proposed for Retirement'),
        ('Retired', 'Retired'),
        ('Lost', 'Lost')
    ]
    MANUAL_STATUS_CHOICES = [
        ('In Storage', 'In Storage'),
        ('In Use', 'In Use'),
        ('Proposed for Retirement', 'Proposed for Retirement'),
        ('Retired', 'Retired'),
        ('Lost', 'Lost')
    ]
    LOCKED_STATUSES = ['Retired', 'Lost']
    is_archived = db.Column(db.Boolean, default=False, nullable=False, index=True)


    @property
    def total_repair_cost(self):
        return sum(repair.cost or 0 for repair in self.repairs)

    @property
    def total_cost_of_ownership(self):
        return (self.purchase_cost or 0) + self.total_repair_cost

    @property
    def warranty_expiry_date(self):
        """Calculates the warranty expiration date."""
        if self.purchase_date and self.warranty_period:
            return self.purchase_date + relativedelta(months=self.warranty_period)
        return None

    @property
    def warranty_status(self):
        """Determines the current warranty status."""
        expiry_date = self.warranty_expiry_date
        if not expiry_date:
            return "Unknown"

        today = date.today()

        if today > expiry_date:
            return "Expired"

        # Define "Expiring Soon" as within the next 30 days
        expiring_soon_date = expiry_date - relativedelta(days=30)
        if today >= expiring_soon_date:
            return "Expiring Soon"

        return "Active"


class MovementLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    from_room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
    to_room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    movement_date = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.String(200))
    moved_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    from_room = db.relationship('Room', foreign_keys=[from_room_id])
    to_room = db.relationship('Room', foreign_keys=[to_room_id])
    moved_by = db.relationship('User', foreign_keys=[moved_by_user_id])

class OwnershipLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    previous_owner_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)
    new_owner_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    previous_owner = db.relationship('Staff', foreign_keys=[previous_owner_id])
    new_owner = db.relationship('Staff', foreign_keys=[new_owner_id])
    change_date = db.Column(db.DateTime, default=datetime.utcnow)
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    asset = db.relationship('Asset', backref=db.backref('ownership_history', cascade="all, delete-orphan"))
    changed_by = db.relationship('User')

class RepairLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    report_date = db.Column(db.DateTime, default=datetime.utcnow)
    problem_description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Float)
    technician_id = db.Column(db.Integer, db.ForeignKey('technician.id'))
    replaced_parts = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pending', nullable=False)
    cancellation_reason = db.Column(db.Text, nullable=True)
    completed_date = db.Column(db.DateTime, nullable=True)
    updated_date = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled')
    ]


class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    contact_person = db.Column(db.String(150))
    phone_number = db.Column(db.String(20), unique=True, nullable=False)

    def __repr__(self):
        return f'<Vendor {self.name}>'

class Technician(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    contact_person = db.Column(db.String(150))
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    repairs = db.relationship('RepairLog', backref='technician', lazy='dynamic')

    def __repr__(self):
        return f'<Technician {self.name}>'


# --- CONSUMABLE MODELS ---

class ConsumableStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)  # e.g., 'Input Device', 'Storage', 'Power'
    item_type = db.Column(db.String(100), nullable=False)  # e.g., 'Mouse', 'Keyboard', 'SSD', 'Charger'
    make = db.Column(db.String(100))
    model = db.Column(db.String(100))
    qty_in_stock = db.Column(db.Integer, nullable=False, default=0)
    reorder_level = db.Column(db.Integer, nullable=False, default=5)

    # This creates a unique constraint across multiple columns
   # __table_args__ = (db.UniqueConstraint('category', 'item_type', 'make', 'model', name='_consumable_uc'),)

    def __repr__(self):
        return f'{self.make} {self.model} ({self.item_type})'


class ConsumableIssuanceLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    consumable_id = db.Column(db.Integer, db.ForeignKey('consumable_stock.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    issued_for_asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)  # Optional asset link
    issued_date = db.Column(db.DateTime, default=datetime.utcnow)
    issued_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    consumable = db.relationship('ConsumableStock', backref='issuances')
    issued_for_asset = db.relationship('Asset', backref='consumable_issuances')
    issued_by = db.relationship('User', backref='consumables_issued')

    transaction_type = db.Column(db.String(20), nullable=False, default='Issue')  # 'Issue' or 'Return'
    notes = db.Column(db.Text, nullable=True)  # For return reasons, etc.


class AssetConsumableLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('asset.id'), nullable=False)
    consumable_id = db.Column(db.Integer, db.ForeignKey('consumable_stock.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    install_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    asset = db.relationship('Asset', backref=db.backref('linked_consumables', cascade="all, delete-orphan"))
    consumable = db.relationship('ConsumableStock')


class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    assets = db.relationship('Asset', backref='owner', lazy='dynamic')

    def __repr__(self):
        return f'<Staff {self.name}>'

