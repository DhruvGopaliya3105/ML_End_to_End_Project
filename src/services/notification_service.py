from sqlalchemy.orm import Session

from src.models.notification import Notification


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str,
    appointment_id: int | None = None
):

    notification = Notification(

        user_id=user_id,

        appointment_id=appointment_id,

        title=title,

        message=message,

        notification_type=notification_type,

        is_read=False
    )

    db.add(notification)

    db.commit()

    db.refresh(notification)

    return notification