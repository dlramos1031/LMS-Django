from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Borrowing
from users.utils import send_expo_push_notification

@receiver(post_save, sender=Borrowing)
def send_borrow_status_notification(sender, instance, created, **kwargs):
    """
    Listens for saves on Borrowing instances.
    Sends a notification if the status was just changed to 'approved' OR 'rejected'.
    Assumes the status change happens atomically (e.g., in an admin action or API call).
    """
    # instance here is the Borrowing object that was saved
    print(f"Signal triggered for Borrowing ID: {instance.id}, Status: {instance.status}, Created: {created}")

    # Avoid sending notifications for newly created 'pending' requests
    if created and instance.status == 'pending':
        print("New pending Borrowing record created, skipping notification.")
        return

    # Check if the status is 'approved'
    # Consider checking 'update_fields' if available and relevant for more robustness
    if instance.status == 'approved':
        # Check if it was *just* approved (e.g., wasn't already approved before this save)
        # This requires more complex state tracking, often handled in the view/action
        # For simplicity, we send if status is 'approved' and not 'created'
        if not created:
            print(f"Borrowing {instance.id} status is 'Approved'. Attempting to send notification to user {instance.user.username}")
            try:
                title = "Borrow Request Approved!"
                due_date_str = instance.due_date.strftime('%Y-%m-%d') if instance.due_date else 'N/A'
                body = f"Your request to borrow '{instance.book.title}' has been approved! Please return by {due_date_str}."
                data_payload = {
                    "screen": "MyBorrowsScreen",
                    "borrowId": instance.id,
                    "message": body,
                    "status": "Approved"
                }
                success = send_expo_push_notification(
                    user=instance.user, title=title, body=body, data=data_payload
                )
                if success:
                    print(f"Push notification request (Approved) sent successfully for Borrowing {instance.id}.")
                else:
                    print(f"Failed to send push notification request (Approved) for Borrowing {instance.id}.")
            except Exception as e:
                print(f"Error triggering push notification (Approved) for Borrowing {instance.id}: {e}")

    # Check if the status is 'rejected'
    elif instance.status == 'rejected':
        # Similar robustness check needed as above if rejection can be saved multiple times
        if not created:
            print(f"Borrowing {instance.id} status is 'Rejected'. Attempting to send notification to user {instance.user.username}")
            try:
                title = "Borrow Request Rejected"
                body = f"Unfortunately, your request to borrow '{instance.book.title}' was rejected."
                data_payload = {
                    "screen": "MyBorrowsScreen",
                    "borrowId": instance.id,
                    "message": body,
                    "status": "Rejected"
                }
                success = send_expo_push_notification(
                    user=instance.user, title=title, body=body, data=data_payload
                )
                if success:
                    print(f"Push notification request (Rejected) sent successfully for Borrowing {instance.id}.")
                else:
                    print(f"Failed to send push notification request (Rejected) for Borrowing {instance.id}.")
            except Exception as e:
                print(f"Error triggering push notification (Rejected) for Borrowing {instance.id}: {e}")
    else:
        # Handle other statuses if needed
        print(f"Borrowing {instance.id} status is '{instance.status}'. No approval/rejection notification sent by this signal.")
