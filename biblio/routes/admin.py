from flask import Blueprint, flash, redirect, render_template, request, url_for
from ..decorators import admin_required
from ..extensions import db
from ..models import Order
from ..notifications import create_notification
from translations import tr
from .orders import (
    ORDER_STATUSES,
    localized_order_statuses,
    localized_payment_methods,
)


bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/orders")
@admin_required
def orders():
    orders = Order.query.order_by(Order.created_at.desc(), Order.id.desc()).all()
    return render_template(
        "admin/orders.html",
        orders=orders,
        order_statuses=localized_order_statuses(),
        payment_methods=localized_payment_methods(),
    )


@bp.route("/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    status = request.form.get("status", "")
    if status not in ORDER_STATUSES:
        flash(tr("flash.order_status_invalid"), "error")
        return redirect(url_for("admin.orders"))

    if status != order.status:
        order.status = status
        create_notification(
            order.user_id,
            tr("notification.order_status_title", order_id=order.id),
            tr("notification.order_status_body", status=tr(ORDER_STATUSES[status])),
            url_for("orders.detail", order_id=order.id),
        )
        db.session.commit()
        flash(tr("flash.order_status_updated", order_id=order.id), "success")
    else:
        flash(tr("flash.order_status_unchanged"), "info")
    return redirect(url_for("admin.orders"))
