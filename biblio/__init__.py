from flask import Flask, render_template, session
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from translations import get_language, tr
from .extensions import db, oauth


def create_app(config_override=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    db.init_app(app)
    oauth.init_app(app)
    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    if app.config.get("FACEBOOK_CLIENT_ID") and app.config.get("FACEBOOK_CLIENT_SECRET"):
        oauth.register(
            name="facebook",
            client_id=app.config["FACEBOOK_CLIENT_ID"],
            client_secret=app.config["FACEBOOK_CLIENT_SECRET"],
            authorize_url="https://www.facebook.com/dialog/oauth",
            access_token_url="https://graph.facebook.com/oauth/access_token",
            api_base_url="https://graph.facebook.com/",
            client_kwargs={"scope": "email,public_profile"},
        )
    CSRFProtect(app)

    from . import models
    from .migrations import (
        migrate_book_detail_schema,
        migrate_order_payment_schema,
        migrate_social_auth_schema,
    )
    from .routes.main import bp as main_bp
    from .routes.auth import bp as auth_bp
    from .routes.books import bp as books_bp
    from .routes.chatbot import bp as chatbot_bp
    from .routes.cart import bp as cart_bp
    from .routes.notifications import bp as notifications_bp
    from .routes.orders import bp as orders_bp
    from .routes.admin import bp as admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)

    @app.template_filter("money")
    def money(value):
        formatted = f"{value:,}"
        if get_language() == "vi":
            formatted = formatted.replace(",", ".")
        return formatted + " ₫"

    @app.context_processor
    def inject_globals():
        user = None
        uid = session.get("user_id")
        if uid:
            user = db.session.get(models.User, uid)
        cart_count = 0
        if user and user.is_active and user.cart:
            cart_count = sum(item.quantity for item in user.cart.items)
        notifications = []
        notification_count = 0
        if user and user.is_active:
            notification_records = (
                models.Notification.query.filter_by(user_id=user.id)
                .order_by(models.Notification.created_at.desc())
                .limit(5)
                .all()
            )
            from .notifications import localize_notification

            notifications = [
                localize_notification(notification)
                for notification in notification_records
            ]
            notification_count = models.Notification.query.filter_by(
                user_id=user.id, is_read=False
            ).count()
        nav_categories = (
            models.Category.query.filter(
                models.Category.name.in_(models.VISIBLE_CATEGORY_NAMES)
            )
            .order_by(models.Category.name)
            .all()
        )

        return dict(
            current_user=user,
            cart_count=cart_count,
            nav_categories=nav_categories,
            current_lang=get_language(),
            current_language=get_language(),
            t=tr,
            notifications=notifications,
            notification_count=notification_count,
            social_providers=[
                provider
                for provider in ("google", "facebook")
                if app.config.get(f"{provider.upper()}_CLIENT_ID")
                and app.config.get(f"{provider.upper()}_CLIENT_SECRET")
            ],
        )

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    with app.app_context():
        migrate_book_detail_schema()
        migrate_social_auth_schema()
        db.create_all()
        migrate_order_payment_schema()

    return app
