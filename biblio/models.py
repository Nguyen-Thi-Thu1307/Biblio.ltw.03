from datetime import datetime
from pathlib import Path

from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db


VISIBLE_CATEGORY_NAMES = (
    "Khoa học - Công nghệ",
    "Kinh tế - Kỹ năng",
    "Lịch sử - Triết học - Văn hoá",
    "Sách tham khảo",
    "Thiếu nhi",
    "Văn học",
)


def book_image_exists(book):
    if not book.image or book.image == "placeholder.png":
        return False
    image_root = Path(current_app.static_folder) / "images"
    return (image_root / book.image).is_file() or (
        image_root / "books" / book.image
    ).is_file()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    full_name = db.Column(db.String(100))
    role = db.Column(db.String(20), default="customer")  # Vai trò: customer hoặc admin.
    is_active = db.Column(db.Boolean, default=True)
    orders = db.relationship("Order", backref="user", lazy=True)
    notifications = db.relationship(
        "Notification", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    cart = db.relationship(
        "Cart", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    social_accounts = db.relationship(
        "SocialAccount", back_populates="user", cascade="all, delete-orphan", lazy=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(
            self.password_hash, password
        )


class SocialAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider = db.Column(db.String(20), nullable=False)
    provider_user_id = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120))
    avatar = db.Column(db.String(500))
    user = db.relationship("User", back_populates="social_accounts")
    __table_args__ = (
        db.UniqueConstraint(
            "provider", "provider_user_id", name="uq_social_account_provider_user"
        ),
        db.UniqueConstraint("user_id", "provider", name="uq_social_account_user_provider"),
    )


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    name_en = db.Column(db.String(100))
    books = db.relationship("Book", backref="category", lazy=True)


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    publisher = db.Column(db.String(100))
    price = db.Column(db.Integer, nullable=False)  # Giá tính bằng đồng Việt Nam.
    stock = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    description_en = db.Column(db.Text)
    image = db.Column(db.String(200))
    edition_type = db.Column(db.String(100))
    origin = db.Column(db.String(100))
    language = db.Column(db.String(50))
    cover_type = db.Column(db.String(100))
    distributor = db.Column(db.String(150))
    publication_year = db.Column(db.String(50))
    page_count = db.Column(db.String(100))
    shipping_from = db.Column(db.String(100))
    size = db.Column(db.String(50))
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))


class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", back_populates="cart")
    items = db.relationship(
        "CartItem", back_populates="cart", cascade="all, delete-orphan", lazy=True
    )


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey("cart.id"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    cart = db.relationship("Cart", back_populates="items")
    book = db.relationship("Book")
    __table_args__ = (
        db.UniqueConstraint("cart_id", "book_id", name="uq_cart_item_cart_book"),
    )


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    receiver_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    payment_method = db.Column(
        db.String(30), nullable=False, default="cash_on_delivery"
    )
    total = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="pending")  # pending (chờ xác nhận), shipping (đang giao), delivered (đã giao), cancelled (đã hủy).
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("OrderItem", backref="order", lazy=True, cascade="all, delete-orphan")


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Integer, nullable=False)
    book = db.relationship("Book")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    target = db.Column(db.String(255), nullable=False, default="/")
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)