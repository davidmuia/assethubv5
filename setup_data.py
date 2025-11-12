from app import db
from app.models import User, Facility, Room, AssetCategory, Vendor, Technician


# Create Facilities
f1 = Facility(name='Warehouse')
f2 = Facility(name='Pipeline')
f3 = Facility(name='Tassia')
f4 = Facility(name='Embakasi')
f5 = Facility(name='Sunton')
f6 = Facility(name='Support Office')
db.session.add_all([f1, f2, f3, f4, f5, f6])
db.session.commit()
print("Facilities created.")

# Create Rooms
r1 = Room(name='Warehouse', facility=f1)
r2 = Room(name='Reception', facility=f2)
r3 = Room(name='Room 1', facility=f2)
r4 = Room(name='Room 2', facility=f2)
r5 = Room(name='Reception', facility=f3)
r6 = Room(name='Room 1', facility=f3)
r7 = Room(name='Room 2', facility=f3)
r8 = Room(name='Reception', facility=f4)
r9 = Room(name='Room 1', facility=f4)
r10 = Room(name='Room 2', facility=f4)
r11 = Room(name='HR', facility=f6)
r12 = Room(name='IT', facility=f6)
r13 = Room(name='Finance', facility=f4)

db.session.add_all([r1, r2, r3, r4,r5,r6,r7,r8,r9,r10,r11,r12,r13])
db.session.commit()
print("Rooms created.")

# Create Asset Categories
c1 = AssetCategory(name='Laptop')
c2 = AssetCategory(name='Desktop')
c3 = AssetCategory(name='Monitor')
c4 = AssetCategory(name='Printer')

db.session.add_all([c1, c2, c3, c4])
db.session.commit()
print("Asset Categories created.")

# Create an initial Vendor and Technician
v1 = Vendor(name='Dell Inc.', phone_number='123-456-7890')
t1 = Technician(name='In-House IT', phone_number='098-765-4321')
db.session.add_all([v1, t1])
db.session.commit()
print("Initial Vendor and Technician created.")

# Create Users
admin = User(username='david', email='david.mwinzia@pendahealth.com', role='Super Admin')
admin.set_password('david')
db.session.add(admin)


db.session.commit()
print("Users created.")

exit()