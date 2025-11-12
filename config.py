import os

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.environ.get('DATABASE_PATH') or os.path.join(basedir, 'instance', 'assets.db')
#db_path = 'C:/database/instance/assets.db'
SECRET_KEY = os.environ.get('SECRET_KEY')

#SECRET_KEY='S9bVHrdJtFUy5wvahknpbByF2F4bRKQWb3LUI1ApPNgTV6mD1CK5Uww4ogiA_xfr'

class Config:
    SECRET_KEY = SECRET_KEY
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + db_path
    SQLALCHEMY_TRACK_MODIFICATIONS = False
