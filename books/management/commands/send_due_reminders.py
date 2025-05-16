import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Q
from books.models import Borrowing, Notification
from users.utils import send_expo_push_notification
from django.utils.translation import gettext_lazy as _

class Command(BaseCommand):
    help = 'Sends due date reminders and handles overdue book alerts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days_due_notice',
            type=int,
            default=3,
            help='Number of days before the due date to send a reminder.',
        )
        parser.add_argument(
            '--force_overdue_check',
            action='store_true',
            help='Force check for overdue items even if it is not the primary purpose of this run.'
        )

    def handle(self, *args, **options):
        days_due_notice = options['days_due_notice']
        force_overdue_check = options['force_overdue_check']

        if days_due_notice <= 0:
            raise CommandError(_("Number of days for due notice must be positive."))

        today = timezone.localdate()

        # --- 1. Send Due Date Reminders ---
        self.stdout.write(self.style.SUCCESS(f"\n--- Sending Due Date Reminders (for books due in {days_due_notice} days) ---"))
        target_due_date_for_reminder = today + datetime.timedelta(days=days_due_notice)
        self.stdout.write(f"Checking for borrowings due on {target_due_date_for_reminder}...")

        # Borrowings that are ACTIVE and due on the target date
        borrowings_due_soon = Borrowing.objects.filter(
            due_date=target_due_date_for_reminder, # Filter by exact date
            status='ACTIVE' # Only for currently active loans
        ).select_related('borrower', 'book_copy__book')

        if not borrowings_due_soon.exists():
            self.stdout.write(self.style.SUCCESS(f"No active borrowings found due in exactly {days_due_notice} days."))
        else:
            self.stdout.write(f"Found {borrowings_due_soon.count()} borrowing(s) due in {days_due_notice} days. Processing reminders...")
            success_reminders = 0
            fail_reminders = 0

            for borrowing in borrowings_due_soon:
                user = borrowing.borrower
                book_title = borrowing.book_copy.book.title
                due_date_str = borrowing.due_date.strftime('%Y-%m-%d')

                # Check if a DUE_REMINDER was already created for this borrowing today
                # This helps prevent duplicate notifications if the command runs multiple times a day.
                if Notification.objects.filter(
                    recipient=user,
                    notification_type='DUE_REMINDER',
                    related_borrowing=borrowing, # Assuming you add a ForeignKey 'related_borrowing' to Notification model
                    timestamp__date=today # Checks if created today
                ).exists():
                    self.stdout.write(self.style.NOTICE(f"  - Reminder for Borrowing ID {borrowing.id} ('{book_title}') already sent today. Skipping."))
                    continue

                self.stdout.write(f"  - Preparing reminder for {user.username} for '{book_title}' (Due: {due_date_str})")

                message_body = _(f"Friendly reminder: Your borrowed book '{book_title}' is due on {due_date_str}.")
                
                try:
                    # Create Database Notification
                    Notification.objects.create(
                        recipient=user,
                        notification_type='DUE_REMINDER',
                        message=message_body,
                        # related_borrowing=borrowing # Uncomment if you add this field to Notification model
                    )
                    
                    # Send Push Notification (optional, based on your existing setup)
                    push_title = _("Book Due Soon!")
                    push_data_payload = {
                        "screen": "MyBorrowsScreen", # Example, adjust to your mobile app's navigation
                        "borrowId": borrowing.id,
                        "type": "due_reminder"
                    }
                    # sent_push = send_expo_push_notification( # Assuming users.utils.send_expo_push_notification
                    # user=user, title=push_title, body=message_body, data=push_data_payload
                    # )
                    # if not sent_push:
                    #     self.stderr.write(self.style.WARNING(f"    Failed to send PUSH notification for Borrowing ID {borrowing.id} (DB notification was created)."))

                    success_reminders += 1
                except Exception as e:
                    fail_reminders += 1
                    self.stderr.write(self.style.ERROR(f"    Error processing reminder for Borrowing ID {borrowing.id}: {e}"))
            
            self.stdout.write(self.style.SUCCESS(f"Due date reminder processing complete. Success: {success_reminders}, Failed: {fail_reminders}"))

        # --- 2. Handle Overdue Books ---
        self.stdout.write(self.style.SUCCESS("\n--- Checking for and Processing Overdue Books ---"))
        
        # Find books that are 'ACTIVE' but their due_date has passed
        overdue_borrowings_to_update = Borrowing.objects.filter(
            status='ACTIVE',
            due_date__lt=today # due_date is in the past
        ).select_related('borrower', 'book_copy__book')

        if not overdue_borrowings_to_update.exists():
            self.stdout.write(self.style.SUCCESS("No active borrowings found that are newly overdue."))
        else:
            self.stdout.write(f"Found {overdue_borrowings_to_update.count()} active borrowing(s) that are now overdue. Updating status and sending alerts...")
            updated_to_overdue_count = 0
            success_overdue_alerts = 0
            fail_overdue_alerts = 0

            for borrowing in overdue_borrowings_to_update:
                user = borrowing.borrower
                book_title = borrowing.book_copy.book.title
                due_date_str = borrowing.due_date.strftime('%Y-%m-%d')
                
                # Update status to 'OVERDUE'
                borrowing.status = 'OVERDUE'
                borrowing.save(update_fields=['status'])
                updated_to_overdue_count += 1
                self.stdout.write(f"  - Marked Borrowing ID {borrowing.id} ('{book_title}') as OVERDUE.")

                # Check if an OVERDUE_ALERT was already created today for this borrowing
                if Notification.objects.filter(
                    recipient=user,
                    notification_type='OVERDUE_ALERT',
                    related_borrowing=borrowing, # Assuming 'related_borrowing' field
                    timestamp__date=today
                ).exists():
                    self.stdout.write(self.style.NOTICE(f"  - Overdue alert for Borrowing ID {borrowing.id} already sent today. Skipping new alert."))
                    continue
                
                alert_message = _(f"Alert: Your borrowed book '{book_title}' was due on {due_date_str} and is now overdue. Please return it as soon as possible. Fines may apply.")
                
                try:
                    # Create Database Notification for Overdue Alert
                    Notification.objects.create(
                        recipient=user,
                        notification_type='OVERDUE_ALERT',
                        message=alert_message,
                        # related_borrowing=borrowing # Uncomment if you add this field
                    )

                    # Send Push Notification for Overdue Alert (optional)
                    push_title_overdue = _("Book Overdue!")
                    push_data_overdue = {
                        "screen": "MyBorrowsScreen",
                        "borrowId": borrowing.id,
                        "type": "overdue_alert"
                    }
                    # sent_overdue_push = send_expo_push_notification(
                    #     user=user, title=push_title_overdue, body=alert_message, data=push_data_overdue
                    # )
                    # if not sent_overdue_push:
                    #    self.stderr.write(self.style.WARNING(f"    Failed to send PUSH notification for overdue Borrowing ID {borrowing.id} (DB notification was created)."))
                    
                    success_overdue_alerts += 1
                except Exception as e:
                    fail_overdue_alerts += 1
                    self.stderr.write(self.style.ERROR(f"    Error processing overdue alert for Borrowing ID {borrowing.id}: {e}"))

            self.stdout.write(self.style.SUCCESS(f"Overdue processing complete. Marked as overdue: {updated_to_overdue_count}. Alerts sent: {success_overdue_alerts}, Failed alerts: {fail_overdue_alerts}"))
        
        self.stdout.write(self.style.SUCCESS("\nManagement command finished."))