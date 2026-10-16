import re
import smtplib
import ssl
from email.message import EmailMessage

from authlib.integrations.base_client.errors import OAuthError
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from requests import RequestException
from sqlalchemy.exc import IntegrityError

from ..decorators import get_current_user, login_required
from ..extensions import db, oauth
from ..models import SocialAccount, User
from ..notifications import create_notification
from translations import tr

bp = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
OAUTH_PROVIDERS = {"google", "facebook"}


def _redirect_after_authentication(next_url=""):
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(url_for("main.home"))


def _establish_session(user, next_url=None):
    if next_url is None:
        next_url = request.args.get("next", "")
    language = session.get("language")
    session.clear()
    if language in {"vi", "en"}:
        session["language"] = language
    session["user_id"] = user.id
    flash(tr("flash.login_success", name=user.full_name or user.username), "success")
    return _redirect_after_authentication(next_url)


def _provider_redirect():
    return url_for("auth.profile") if get_current_user() else url_for("auth.login")


def _provider_unavailable(provider):
    flash(
        tr("auth.provider_unavailable", provider=tr(f"auth.{provider}")),
        "error",
    )
    return redirect(_provider_redirect())


def _password_reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _send_password_reset_email(user):
    token = _password_reset_serializer().dumps(user.id, salt="password-reset")
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    message = EmailMessage()
    message["Subject"] = tr("auth.reset_email_subject")
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = user.email
    message.set_content(
        tr(
            "auth.reset_email_body",
            reset_url=reset_url,
            minutes=current_app.config["PASSWORD_RESET_MAX_AGE"] // 60,
        )
    )

    server = current_app.config["MAIL_SERVER"]
    port = current_app.config["MAIL_PORT"]
    username = current_app.config["MAIL_USERNAME"]
    password = current_app.config["MAIL_PASSWORD"]
    if not server or not message["From"]:
        raise RuntimeError("Thiếu cấu hình máy chủ email đặt lại mật khẩu.")

    context = ssl.create_default_context()
    with smtplib.SMTP(server, port, timeout=15) as smtp:
        if current_app.config["MAIL_USE_TLS"]:
            smtp.starttls(context=context)
        if username:
            smtp.login(username, password or "")
        smtp.send_message(message)


def _normalized_profile(provider, data):
    if not isinstance(data, dict):
        raise ValueError("Nhà cung cấp trả về dữ liệu tài khoản không hợp lệ.")
    provider_user_id = data.get("sub") if provider == "google" else data.get("id")
    if not isinstance(provider_user_id, (str, int)) or not str(provider_user_id):
        raise ValueError("Nhà cung cấp không trả về mã tài khoản hợp lệ.")

    email = data.get("email")
    if isinstance(email, str):
        email = email.strip().lower()
    else:
        email = None

    avatar = data.get("picture")
    if isinstance(avatar, dict):
        picture_data = avatar.get("data")
        avatar = picture_data.get("url") if isinstance(picture_data, dict) else None
    if not isinstance(avatar, str):
        avatar = None

    return {
        "provider": provider,
        "provider_user_id": str(provider_user_id),
        "email": email,
        "email_verified": data.get("email_verified") is True
        or (provider == "facebook" and bool(email)),
        "name": str(data.get("name") or "")[:100],
        "avatar": avatar[:500] if avatar else None,
    }


def _new_social_username(provider, provider_user_id):
    suffix = re.sub(r"[^a-zA-Z0-9]", "", provider_user_id).lower()[:40]
    base = f"{provider}_{suffix or 'user'}"[:50]
    username = base
    number = 1
    while User.query.filter_by(username=username).first():
        ending = f"_{number}"
        username = f"{base[:50 - len(ending)]}{ending}"
        number += 1
    return username


def _save_social_account(user, profile):
    db.session.add(
        SocialAccount(
            user_id=user.id,
            provider=profile["provider"],
            provider_user_id=profile["provider_user_id"],
            email=profile["email"],
            avatar=profile["avatar"],
        )
    )


def _finish_oauth(provider, profile, email_verified):
    user = get_current_user()
    if user and not user.is_active:
        flash(tr("flash.account_disabled"), "error")
        return redirect(url_for("auth.login"))

    account = SocialAccount.query.filter_by(
        provider=provider, provider_user_id=profile["provider_user_id"]
    ).first()
    if account:
        if user and account.user_id != user.id:
            flash(tr("auth.social_account_in_use"), "error")
            return redirect(url_for("auth.profile"))
        if not account.user.is_active:
            flash(tr("flash.account_disabled"), "error")
            return redirect(url_for("auth.login"))
        if user:
            session.pop("oauth_next", None)
            flash(tr("auth.account_linked", provider=tr(f"auth.{provider}")), "success")
            return redirect(url_for("auth.profile"))
        return _establish_session(account.user, session.pop("oauth_next", ""))

    if user:
        session.pop("oauth_next", None)
        _save_social_account(user, profile)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(tr("auth.social_account_in_use"), "error")
            return redirect(url_for("auth.profile"))
        flash(tr("auth.account_linked", provider=tr(f"auth.{provider}")), "success")
        return redirect(url_for("auth.profile"))

    email = profile["email"]
    if not email:
        if provider == "facebook":
            session["pending_social_profile"] = profile
            return render_template("auth/oauth_email.html", provider=provider)
        flash(tr("auth.email_unavailable"), "error")
        return redirect(url_for("auth.login"))
    if len(email) > 120 or not EMAIL_PATTERN.fullmatch(email):
        flash(tr("flash.email_invalid"), "error")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if user:
        if not email_verified:
            flash(tr("auth.email_link_requires_login"), "error")
            return redirect(url_for("auth.login"))
        if not user.is_active:
            flash(tr("flash.account_disabled"), "error")
            return redirect(url_for("auth.login"))
        _save_social_account(user, profile)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(tr("auth.social_account_in_use"), "error")
            return redirect(url_for("auth.login"))
        return _establish_session(user, session.pop("oauth_next", ""))

    user = User(
        username=_new_social_username(provider, profile["provider_user_id"]),
        email=email,
        full_name=profile["name"] or tr(f"auth.{provider}"),
        password_hash=None,
        role="customer",
    )
    db.session.add(user)
    try:
        db.session.flush()
        _save_social_account(user, profile)
        create_notification(
            user.id,
            tr("auth.welcome_notification_title"),
            tr("auth.welcome_notification_message"),
            url_for("main.home"),
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(tr("auth.email_link_requires_login"), "error")
        return redirect(url_for("auth.login"))
    return _establish_session(user, session.pop("oauth_next", ""))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = get_current_user()
    form_data = {
        "full_name": request.form.get("full_name", user.full_name or "").strip(),
        "username": request.form.get("username", user.username).strip(),
        "email": request.form.get("email", user.email).strip().lower(),
    }

    if request.method == "POST":
        error = None
        if not form_data["username"] or not form_data["email"]:
            error = tr("flash.register_required")
        elif (
            len(form_data["username"]) > 50
            or len(form_data["email"]) > 120
            or len(form_data["full_name"]) > 100
        ):
            error = tr("flash.profile_too_long")
        elif not EMAIL_PATTERN.fullmatch(form_data["email"]):
            error = tr("flash.email_invalid")
        elif User.query.filter(
            User.id != user.id, User.username == form_data["username"]
        ).first():
            error = tr("flash.username_exists")
        elif User.query.filter(
            User.id != user.id, User.email == form_data["email"]
        ).first():
            error = tr("flash.email_exists")

        if error:
            flash(error, "error")
        else:
            user.full_name = form_data["full_name"] or None
            user.username = form_data["username"]
            user.email = form_data["email"]
            db.session.commit()
            flash(tr("flash.profile_saved"), "success")
            return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", form_data=form_data)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not username or not email or not password:
            error = tr("flash.register_required")
        elif len(password) < 6:
            error = tr("flash.password_short")
        elif password != confirm:
            error = tr("flash.password_mismatch")
        elif User.query.filter_by(username=username).first():
            error = tr("flash.username_exists")
        elif User.query.filter_by(email=email).first():
            error = tr("flash.email_exists")

        if error:
            flash(error, "error")
        else:
            user = User(username=username, email=email, full_name=full_name, role="customer")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(tr("flash.register_success"), "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash(tr("flash.login_invalid"), "error")
        elif not user.is_active:
            flash(tr("flash.account_disabled"), "error")
        else:
            return _establish_session(user)
    return render_template("auth/login.html")


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.is_active:
            try:
                _send_password_reset_email(user)
            except (OSError, smtplib.SMTPException, RuntimeError):
                current_app.logger.exception(
                    "Không thể gửi email đặt lại mật khẩu cho user_id=%s.", user.id
                )
                flash(tr("flash.password_reset_unavailable"), "error")
                return render_template("auth/forgot_password.html", email=email)
        else:
            flash(tr("flash.password_reset_sent"), "success")
            return redirect(url_for("auth.login"))
        flash(tr("flash.password_reset_sent"), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", email="")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        user_id = _password_reset_serializer().loads(
            token,
            salt="password-reset",
            max_age=current_app.config["PASSWORD_RESET_MAX_AGE"],
        )
    except (BadSignature, SignatureExpired):
        flash(tr("flash.password_reset_invalid"), "error")
        return redirect(url_for("auth.forgot_password"))

    user = db.session.get(User, user_id)
    if not user or not user.is_active:
        flash(tr("flash.password_reset_invalid"), "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(password) < 6:
            flash(tr("flash.password_short"), "error")
        elif password != confirm:
            flash(tr("flash.password_mismatch"), "error")
        else:
            user.set_password(password)
            db.session.commit()
            flash(tr("flash.password_reset_success"), "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")


@bp.route("/auth/<provider>")
def oauth_login(provider):
    if provider not in OAUTH_PROVIDERS:
        abort(404)
    client = oauth.create_client(provider)
    if not client:
        return _provider_unavailable(provider)
    user = get_current_user()
    if user and not user.is_active:
        flash(tr("flash.account_disabled"), "error")
        return redirect(url_for("auth.login"))
    session.pop("pending_social_profile", None)
    session["oauth_next"] = request.args.get("next", "")
    callback = url_for("auth.oauth_callback", provider=provider, _external=True)
    return client.authorize_redirect(callback)


@bp.route("/auth/<provider>/callback", methods=["GET", "POST"])
def oauth_callback(provider):
    if provider not in OAUTH_PROVIDERS:
        abort(404)
    client = oauth.create_client(provider)
    if not client:
        return _provider_unavailable(provider)

    if request.method == "POST":
        profile = session.pop("pending_social_profile", None)
        if not profile or profile.get("provider") != provider or get_current_user():
            flash(tr("auth.oauth_failed"), "error")
            return redirect(url_for("auth.login"))
        email = request.form.get("email", "").strip().lower()
        if not email or len(email) > 120 or not EMAIL_PATTERN.fullmatch(email):
            flash(tr("flash.email_invalid"), "error")
            session["pending_social_profile"] = profile
            return render_template("auth/oauth_email.html", provider=provider)
        profile["email"] = email
        return _finish_oauth(provider, profile, email_verified=False)

    try:
        client.authorize_access_token()
        if provider == "google":
            response = client.get("https://openidconnect.googleapis.com/v1/userinfo")
        else:
            response = client.get("me", params={"fields": "id,name,email,picture.type(large)"})
        response.raise_for_status()
        profile = _normalized_profile(provider, response.json())
    except (OAuthError, RequestException, ValueError):
        current_app.logger.exception("Không thể xác thực tài khoản qua %s.", provider)
        flash(tr("auth.oauth_failed"), "error")
        return redirect(_provider_redirect())

    return _finish_oauth(provider, profile, profile["email_verified"])


@bp.route("/unlink/<int:account_id>", methods=["POST"])
@login_required
def unlink_social_account(account_id):
    user = get_current_user()
    account = SocialAccount.query.filter_by(id=account_id, user_id=user.id).first_or_404()
    if not user.password_hash and len(user.social_accounts) <= 1:
        flash(tr("auth.last_login_method"), "error")
        return redirect(url_for("auth.profile"))
    db.session.delete(account)
    db.session.commit()
    flash(tr("auth.account_unlinked", provider=tr(f"auth.{account.provider}")), "success")
    return redirect(url_for("auth.profile"))


@bp.route("/logout")
def logout():
    language = session.get("language")
    session.clear()
    if language in {"vi", "en"}:
        session["language"] = language
    flash(tr("flash.logout_success"), "success")
    return redirect(url_for("main.home"))
