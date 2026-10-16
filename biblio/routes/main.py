from urllib.parse import urlsplit
import re

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from ..extensions import db
from ..models import Book, Category, Contact, book_image_exists
from translations import tr

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    newest = [
        book
        for book in Book.query.order_by(Book.id.desc()).all()
        if book_image_exists(book)
    ][:8]
    return render_template("index.html", books=newest)


@bp.route("/about", methods=["GET", "POST"])
def about():
    catalog_categories = {}
    for category in Category.query.all():
        catalog_categories[category.name] = category
        if category.name_en:
            catalog_categories[category.name_en] = category

    form_data = {
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "message": request.form.get("message", "").strip(),
    }

    if request.method == "POST":
        error = None
        if not all(form_data.values()):
            error = tr("about.contact_required")
        elif (
            len(form_data["name"]) > 100
            or len(form_data["email"]) > 120
            or len(form_data["message"]) > 2000
        ):
            error = tr("about.contact_too_long")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", form_data["email"]):
            error = tr("about.contact_email_invalid")

        if error:
            flash(error, "error")
        else:
            db.session.add(
                Contact(
                    name=form_data["name"],
                    email=form_data["email"],
                    message=form_data["message"],
                )
            )
            db.session.commit()
            flash(tr("about.contact_success"), "success")
            return redirect(url_for("main.about", _anchor="contact"))

    return render_template(
        "about.html",
        form_data=form_data,
        catalog_categories=catalog_categories,
    )


@bp.route("/privacy")
def privacy_policy():
    return render_template(
        "privacy.html",
        privacy_sections=(
            {"title": "legal.privacy.purpose_title", "body": "legal.privacy.purpose", "items": ()},
            {
                "title": "legal.privacy.collection_title",
                "body": "",
                "items": (
                    "legal.privacy.collection_item_1",
                    "legal.privacy.collection_item_2",
                    "legal.privacy.collection_item_3",
                    "legal.privacy.collection_item_4",
                    "legal.privacy.collection_item_5",
                    "legal.privacy.collection_item_6",
                ),
            },
            {
                "title": "legal.privacy.use_title",
                "body": "",
                "items": (
                    "legal.privacy.use_item_1",
                    "legal.privacy.use_item_2",
                    "legal.privacy.use_item_3",
                    "legal.privacy.use_item_4",
                    "legal.privacy.use_item_5",
                ),
            },
            {"title": "legal.privacy.cookies_title", "body": "legal.privacy.cookies", "items": ()},
            {
                "title": "legal.privacy.sharing_title",
                "body": "",
                "items": (
                    "legal.privacy.sharing_item_1",
                    "legal.privacy.sharing_item_2",
                    "legal.privacy.sharing_item_3",
                ),
            },
            {"title": "legal.privacy.security_title", "body": "legal.privacy.security", "items": ()},
            {"title": "legal.privacy.retention_title", "body": "legal.privacy.retention", "items": ()},
            {"title": "legal.privacy.rights_title", "body": "legal.privacy.rights", "items": ()},
            {"title": "legal.privacy.children_title", "body": "legal.privacy.children", "items": ()},
            {"title": "legal.privacy.changes_title", "body": "legal.privacy.changes", "items": ()},
            {"title": "legal.privacy.contact_title", "body": "legal.privacy.contact", "items": ()},
        ),
    )


@bp.route("/terms")
def terms():
    return render_template(
        "terms.html",
        terms_sections=(
            {"title": "legal.terms.introduction_title", "body": "legal.terms.introduction", "items": ()},
            {
                "title": "legal.terms.project_title",
                "body": "legal.terms.project",
                "items": (
                    "legal.terms.project_item_1",
                    "legal.terms.project_item_2",
                    "legal.terms.project_item_3",
                ),
            },
            {
                "title": "legal.terms.account_title",
                "body": "",
                "items": (
                    "legal.terms.account_item_1",
                    "legal.terms.account_item_2",
                    "legal.terms.account_item_3",
                    "legal.terms.account_item_4",
                ),
            },
            {
                "title": "legal.terms.usage_title",
                "body": "legal.terms.usage",
                "items": (
                    "legal.terms.usage_item_1",
                    "legal.terms.usage_item_2",
                    "legal.terms.usage_item_3",
                ),
            },
            {
                "title": "legal.terms.content_title",
                "body": "",
                "items": (
                    "legal.terms.content_item_1",
                    "legal.terms.content_item_2",
                    "legal.terms.content_item_3",
                ),
            },
            {"title": "legal.terms.liability_title", "body": "legal.terms.liability", "items": ()},
            {"title": "legal.terms.third_party_title", "body": "legal.terms.third_party", "items": ()},
            {"title": "legal.terms.changes_title", "body": "legal.terms.changes", "items": ()},
            {"title": "legal.terms.contact_title", "body": "legal.terms.contact", "items": ()},
        ),
    )


@bp.route("/set-language/<lang>")
def set_language(lang):
    if lang not in {"vi", "en"}:
        abort(404)

    session["language"] = lang
    flash(tr("flash.language_changed"), "success")
    referrer = request.referrer
    if referrer:
        parsed = urlsplit(referrer)
        if (
            (not parsed.netloc or parsed.netloc == request.host)
            and parsed.path.startswith("/")
            and not parsed.path.startswith("//")
        ):
            return redirect(parsed.path + (f"?{parsed.query}" if parsed.query else ""))
    return redirect(url_for("main.home"))