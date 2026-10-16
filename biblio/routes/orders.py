from flask import Blueprint, flash, redirect, render_template, request, url_for
from ..decorators import get_current_user, login_required
from ..extensions import db
from ..models import Cart, CartItem, Order, OrderItem
from ..notifications import create_notification
from translations import tr


bp = Blueprint("orders", __name__)
ORDER_STATUSES = {
    "pending": "orders.status.pending",
    "shipping": "orders.status.shipping",
    "delivered": "orders.status.delivered",
    "cancelled": "orders.status.cancelled",
}
PAYMENT_METHODS = {
    "cash_on_delivery": "checkout.payment_cash_on_delivery",
    "bank_transfer": "checkout.payment_bank_transfer",
}


def localized_order_statuses():
    return {status: tr(translation_key) for status, translation_key in ORDER_STATUSES.items()}


@bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    user = get_current_user()
    cart = Cart.query.filter_by(user_id=user.id).first()
    items = cart.items if cart else []
    if not items:
        flash(tr("flash.checkout_empty_cart"), "warning")
        return redirect(url_for("cart.view_cart"))

    form_data = {
        "receiver_name": request.form.get(
            "receiver_name", user.full_name or user.username
        ).strip(),
        "phone": request.form.get("phone", "").strip(),
        "address": request.form.get("address", "").strip(),
        "payment_method": request.form.get(
            "payment_method", "cash_on_delivery"
        ).strip(),
    }

    if request.method == "POST":
        if (
            not all(
                form_data[field] for field in ("receiver_name", "phone", "address")
            )
            or form_data["payment_method"] not in PAYMENT_METHODS
        ):
            flash(tr("flash.checkout_required"), "error")
            return render_template(
                "orders/checkout.html",
                items=items,
                total=sum(item.book.price * item.quantity for item in items),
                form_data=form_data,
                payment_methods=localized_payment_methods(),
            )

        for item in items:
            if item.quantity > (item.book.stock or 0):
                flash(
                    tr(
                        "flash.checkout_stock_limit",
                        title=item.book.title,
                        stock=item.book.stock or 0,
                    ),
                    "warning",
                )
                return redirect(url_for("cart.view_cart"))

        total = sum(item.book.price * item.quantity for item in items)
        order = Order(
            user_id=user.id,
            receiver_name=form_data["receiver_name"],
            phone=form_data["phone"],
            address=form_data["address"],
            payment_method=form_data["payment_method"],
            total=total,
            status="pending",
        )
        db.session.add(order)
        db.session.flush()

        for item in items:
            db.session.add(
                OrderItem(
                    order_id=order.id,
                    book_id=item.book_id,
                    quantity=item.quantity,
                    unit_price=item.book.price,
                )
            )
            item.book.stock -= item.quantity

        CartItem.query.filter_by(cart_id=cart.id).delete(synchronize_session=False)
        create_notification(
            user.id,
            tr("notification.order_received_title"),
            tr("notification.order_received_body", order_id=order.id),
            url_for("orders.detail", order_id=order.id),
        )
        db.session.commit()
        flash(tr("flash.order_placed", order_id=order.id), "success")
        return redirect(url_for("orders.detail", order_id=order.id))

    return render_template(
        "orders/checkout.html",
        items=items,
        total=sum(item.book.price * item.quantity for item in items),
        form_data=form_data,
        payment_methods=localized_payment_methods(),
    )


def localized_payment_methods():
    return {method: tr(translation_key) for method, translation_key in PAYMENT_METHODS.items()}


@bp.route("/my-orders")
@login_required
def my_orders():
    user = get_current_user()
    orders = (
        Order.query.filter_by(user_id=user.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .all()
    )
    return render_template(
        "orders/list.html", orders=orders, order_statuses=localized_order_statuses()
    )


@bp.route("/orders/<int:order_id>")
@login_required
def detail(order_id):
    user = get_current_user()
    order = Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()
    return render_template(
        "orders/detail.html",
        order=order,
        order_statuses=localized_order_statuses(),
        payment_methods=localized_payment_methods(),
    )
