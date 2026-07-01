from .models import Notification


def create_notification(
    user,
    title,
    message,
    notification_type=Notification.TYPE_REMINDER
):
    valid_types = {
        choice[0]
        for choice in Notification.TYPE_CHOICES
    }

    if notification_type not in valid_types:
        notification_type = Notification.TYPE_REMINDER

    return Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type
    )


def get_latest_notifications(user, limit=5):
    return Notification.objects.filter(
        user=user
    ).order_by('-created_at')[:limit]


def mark_notification_read(notification_id, user):
    updated_count = Notification.objects.filter(
        id=notification_id,
        user=user
    ).update(is_read=True)

    return updated_count > 0
