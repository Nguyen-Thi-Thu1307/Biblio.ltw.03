import re
from datetime import timedelta, timezone

from .extensions import db
from .models import Notification
from translations import get_language, tr

VIETNAM_TIMEZONE = timezone(timedelta(hours=7))


def localize_notification(notification):
    title = notification.title
    message = notification.message
    created_at = notification.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    created_at = created_at.astimezone(VIETNAM_TIMEZONE)

    if get_language() != "en":
        return {"id": notification.id, "title": title, "message": message,
                "is_read": notification.is_read, "created_at": created_at}

    title_keys = {
        "Chào mừng đến với Biblio": "auth.welcome_notification_title",
        "Đã thêm sách vào giỏ hàng": "notification.cart_added_title",
        "Đã cập nhật giỏ hàng": "notification.cart_updated_title",
        "Đã xóa sách khỏi giỏ hàng": "notification.cart_removed_title",
        "Đã làm trống giỏ hàng": "notification.cart_cleared_title",
        "Đã tiếp nhận đơn hàng": "notification.order_received_title",
    }
    message_patterns = (
        (
            r"Tài khoản của bạn đã sẵn sàng\. Chúc bạn tìm được cuốn sách yêu thích!",
            "auth.welcome_notification_message",
            "none",
        ),
        (r"“(.+)” đã được thêm vào giỏ hàng\.", "notification.cart_added_body", "title"),
        (r"Số lượng “(.+)” hiện là (\d+)\.", "notification.cart_updated_body", "title_quantity"),
        (r"“(.+)” đã được xóa khỏi giỏ hàng\.", "notification.cart_removed_body", "title"),
        (r"Tất cả sách đã được xóa khỏi giỏ hàng\.", "notification.cart_cleared_body", "none"),
        (r"Đơn hàng #(\d+) đang chờ xác nhận\.", "notification.order_received_body", "order"),
    )

    localized_title = title_keys.get(title, title)
    order_title = re.fullmatch(r"Đơn hàng #(\d+) đã cập nhật", title)
    if order_title:
        localized_title = tr("notification.order_status_title", order_id=order_title.group(1))
    elif localized_title != title:
        localized_title = tr(localized_title)

    localized_message = message
    for pattern, key, value_kind in message_patterns:
        match = re.fullmatch(pattern, message)
        if not match:
            continue
        if value_kind == "title":
            localized_message = tr(key, title=match.group(1))
        elif value_kind == "title_quantity":
            localized_message = tr(key, title=match.group(1), quantity=match.group(2))
        elif value_kind == "order":
            localized_message = tr(key, order_id=match.group(1))
        else:
            localized_message = tr(key)
        break

    order_status = re.fullmatch(r"Trạng thái đơn hàng hiện là “(.+)”\.", message)
    if order_status:
        status_keys = {
            "Chờ xác nhận": "orders.status.pending",
            "Đang giao": "orders.status.shipping",
            "Đã giao": "orders.status.delivered",
            "Đã hủy": "orders.status.cancelled",
        }
        status = status_keys.get(order_status.group(1))
        if status:
            localized_message = tr("notification.order_status_body", status=tr(status))

    return {
        "id": notification.id,
        "title": localized_title,
        "message": localized_message,
        "is_read": notification.is_read,
        "created_at": created_at,
    }


def create_notification(user_id, title, message, target):
    db.session.add(
        Notification(
            user_id=user_id,
            title=title,
            message=message,
            target=target,
        )
    )
