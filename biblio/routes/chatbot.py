import re
import unicodedata

from flask import Blueprint, jsonify, request, url_for
from sqlalchemy import or_

from ..models import Book, Category, book_image_exists
from translations import get_language, tr

bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

_STOP_WORDS = {
    "cho", "có", "cuốn", "gì", "hay", "là", "loại", "nào", "nhé",
    "sách", "tôi", "tìm", "từ", "và", "về", "với", "muốn", "một",
    "cần", "được", "gợi", "ý", "tham", "khảo", "bạn", "mình", "xin",
    "co", "cuon", "gi", "la", "loai", "nao", "nha", "toi", "tim",
    "va", "ve", "voi", "mot", "duoc", "goi", "khao", "ban", "minh",
}
_SEARCH_FIELDS = (
    Book.title,
    Book.author,
    Book.description,
    Book.description_en,
    Category.name,
    Category.name_en,
)


def _plain_text(value):
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )
    return normalized.replace("đ", "d")


def _has_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def _book_cards(books):
    return [
        {
            "title": book.title,
            "author": book.author,
            "category": (
                (book.category.name_en if get_language() == "en" and book.category.name_en else book.category.name)
                if book.category
                else ""
            ),
            "publisher": book.publisher or "",
            "description": (
                book.description_en if get_language() == "en" and book.description_en else book.description
            )
            or "",
            "stock": book.stock or 0,
            "price": f"{book.price:,}".replace(",", ".") + " ₫",
            "url": url_for("books.detail", book_id=book.id),
        }
        for book in books
    ]


@bp.post("/message")
def message():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error=tr("chatbot.invalid_message")), 400

    text = payload.get("message", "")
    if not isinstance(text, str):
        return jsonify(error=tr("chatbot.invalid_message")), 400

    text = text.strip()
    if not text or len(text) > 240:
        return jsonify(error=tr("chatbot.invalid_length")), 400

    plain_text = _plain_text(text)
    if _has_any(plain_text, ("giao hang", "ship", "van chuyen", "bao lau")):
        return jsonify(reply=tr("chatbot.delivery_info"), books=[])
    if _has_any(plain_text, ("thanh toan", "cod", "chuyen khoan", "qr", "vi dien tu")):
        return jsonify(reply=tr("chatbot.payment_info"), books=[])
    if _has_any(
        plain_text,
        (
            "dieu khoan",
            "chinh sach bao mat",
            "bao mat",
            "cookie",
            "luu tru",
            "quyen cua ban",
            "tre em",
            "thay doi chinh sach",
        ),
    ):
        return jsonify(reply=tr("chatbot.legal_info"), books=[])
    if _has_any(plain_text, ("lien he", "hotline", "email", "dia chi")):
        return jsonify(reply=tr("chatbot.contact_info"), books=[])
    if _has_any(
        plain_text,
        ("gio hang", "dat hang", "don hang", "mua sach", "dich vu", "ho tro mua"),
    ):
        return jsonify(reply=tr("chatbot.order_info"), books=[])
    if _has_any(plain_text, ("tai khoan", "dang ky", "dang nhap", "quen mat khau")):
        return jsonify(reply=tr("chatbot.account_info"), books=[])
    if _has_any(plain_text, ("biblio la gi", "du an", "gioi thieu")):
        return jsonify(reply=tr("chatbot.project_info"), books=[])

    terms = list(
        dict.fromkeys(
            term
            for term in re.findall(r"[a-z0-9À-ỹ]+", text.lower())
            if len(term) > 1 and term not in _STOP_WORDS
        )
    )[:8]

    if not terms:
        return jsonify(
            reply=tr("chatbot.ask_preferences"),
            books=[],
        )

    matches = (
        Book.query.outerjoin(Category, Book.category_id == Category.id)
        .filter(
            or_(
                *(field.ilike(f"%{term}%") for term in terms for field in _SEARCH_FIELDS)
            )
        )
        .limit(50)
        .all()
    )
    matches = [book for book in matches if book_image_exists(book)]

    def relevance(book):
        fields = (
            (book.title or "", 5),
            (book.author or "", 4),
            (book.category.name if book.category else "", 3),
            (book.description or "", 1),
            (book.description_en or "", 1),
        )
        return sum(
            weight
            for term in terms
            for value, weight in fields
            if term in value.lower()
        )

    matches.sort(key=lambda book: (relevance(book), book.stock), reverse=True)
    recommendations = _book_cards(matches[:3])

    if recommendations:
        if any((book["stock"] or 0) < 1 for book in recommendations):
            reply = tr("chatbot.book_info_found")
        else:
            reply = tr("chatbot.recommendations_found")
    else:
        reply = tr("chatbot.no_recommendations")

    return jsonify(reply=reply, books=recommendations)