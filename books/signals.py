from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Borrowing
from users.utils import send_expo_push_notification

@receiver(post_save, sender=Borrowing)
def send_borrow_status_notification(sender, instance, created, **kwargs):
    """
    Listens for saves on BorrowRequest instances.
    Sends a notification if the status was just changed to 'Approved'.
    """
    print(f"Signal triggered for BorrowRequest ID: {instance.id}, Status: {instance.status}, Created: {created}")

    if created:
        print("Borrowing was just created, skipping notification for now.")
        return

    # Check if the status is 'Approved' (adjust field name if necessary)
    if instance.status == 'approved':
        print(f"Borrowing {instance.id} has status 'Approved'. Attempting to send notification to user {instance.user.username}")
        try:
            # Prepare notification details
            title = "Borrow Request Approved!"
            # Make sure 'instance.book.title' exists or adjust field access
            body = f"Your request to borrow '{instance.book.title}' has been approved by the librarian."
            # Optional data payload
            data_payload = {
                "screen": "MyBorrowsScreen", # Example screen name
                "borrowId": instance.id,
                "message": body
            }

            # Call the utility function
            success = send_expo_push_notification(
                user=instance.user,    # User who made the request
                title=title,
                body=body,
                data=data_payload
            )

            if success:
                print(f"Push notification request sent successfully for Borrowing {instance.id}.")
            else:
                print(f"Failed to send push notification request for Borrowing {instance.id}.")

        except Exception as e:
            print(f"Error triggering push notification for Borrowing {instance.id}: {e}")

    else:
        print(f"Borrowing {instance.id} status is '{instance.status}', not 'Approved'. No notification sent.")
