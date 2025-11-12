from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from sqlalchemy.schema import MetaData
from datetime import datetime
import pytz



naming_convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

db = SQLAlchemy(
    metadata=MetaData(naming_convention=naming_convention)
)
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    LOCAL_TIMEZONE = pytz.timezone('Africa/Nairobi')

    @app.template_filter('localdatetime')
    def localdatetime_filter(dt, fmt='%Y-%m-%d %H:%M'):
        if dt is None:
            return "N/A"
        utc_dt = pytz.utc.localize(dt)
        local_dt = utc_dt.astimezone(LOCAL_TIMEZONE)
        return local_dt.strftime(fmt)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)

    # This makes the dictionary available in all templates
    @app.context_processor
    def inject_status_colors():
        STATUS_BADGE_MAP = {
            'In Use': 'bg-success',
            'In Storage': 'bg-primary',
            'Awaiting Repair': 'bg-info text-dark',
            'In Repair': 'bg-warning text-dark',
            'Lost': 'bg-danger',
            'Retired': 'bg-secondary'
        }
        # The 'get' method provides a default if the status is not in the map
        return dict(get_status_badge_class=lambda status: STATUS_BADGE_MAP.get(status, 'bg-primary'))

    @app.context_processor
    def inject_status_icons():
        STATUS_ICON_MAP = {
            'In Use': 'bi bi-check-circle-fill',
            'In Storage': 'bi bi-box-seam-fill',
            'Awaiting Repair': 'bi bi-tools',
            'In Repair': 'bi bi-gear-wide-connected',
            'Proposed for Retirement': 'bi bi-box-arrow-in-down-right',
            'Retired': 'bi bi-trash2-fill',
            'Lost': 'bi bi-question-diamond-fill'
        }
        # The 'get' method provides a default icon if the status is not in the map
        return dict(get_status_icon_class=lambda status: STATUS_ICON_MAP.get(status, 'bi bi-info-circle-fill'))

    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin_routes import admin_bp
    app.register_blueprint(admin_bp)

    from app.reports_routes import reports_bp
    app.register_blueprint(reports_bp)


    return app

