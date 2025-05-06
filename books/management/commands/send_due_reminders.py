import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import FieldError
from books.models import Borrowing
from users.utils import send_expo_push_notification

class Command(BaseCommand):
    help = 'Sends push notification reminders for books due within a specified number of days.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=3, # Default to 3 days notice
            help='Number of days before the due date to send the reminder.',
        )

    def handle(self, *args, **options):
        days_notice = options['days']
        if days_notice <= 0:
            raise CommandError("Number of days must be positive.")

        today = timezone.localdate()
        target_due_date = today + datetime.timedelta(days=days_notice)

        self.stdout.write(f"Checking for borrowings due on {target_due_date}...")

        try:
            # Find borrowing records that are:
            # - Due exactly on the target date
            # - Currently marked as 'approved' (meaning borrowed)
            # - Have not been actually returned yet (actual_return_date is NULL)
            borrowings_due_soon = Borrowing.objects.filter(
                due_date__date=target_due_date,
                status='approved', 
                actual_return_date__isnull=True 
            ).select_related('user', 'book') 

            if not borrowings_due_soon.exists():
                self.stdout.write(self.style.SUCCESS(f"No approved borrowings found due in exactly {days_notice} days that haven't been returned."))
                return

            self.stdout.write(f"Found {borrowings_due_soon.count()} borrowing(s) due soon. Sending notifications...")
            success_count = 0
            fail_count = 0

            for borrowing in borrowings_due_soon:
                user = borrowing.user
                book_title = borrowing.book.title
                due_date_str = borrowing.due_date.strftime('%Y-%m-%d')

                self.stdout.write(f"  - Sending reminder to {user.username} for '{book_title}' (Due: {due_date_str})")

                try:
                    title = "Book Due Soon!"
                    body = f"Reminder: '{book_title}' is due on {due_date_str}."
                    data_payload = {
                        "screen": "MyBorrowsScreen",
                        "borrowId": borrowing.id,
                        "message": body,
                        "type": "due_reminder"
                    }

                    sent = send_expo_push_notification(
                        user=user,
                        title=title,
                        body=body,
                        data=data_payload
                    )

                    if sent:
                        success_count += 1
                    else:
                        fail_count += 1
                        self.stderr.write(f"    Failed to send notification for Borrowing ID {borrowing.id}")

                except Exception as e:
                    fail_count += 1
                    self.stderr.write(f"    Error sending notification for Borrowing ID {borrowing.id}: {e}")

            self.stdout.write(self.style.SUCCESS(f"Finished sending reminders. Success: {success_count}, Failed: {fail_count}"))

        except FieldError as e:
             raise CommandError(f"A field error occurred: {e}")
        except Exception as e:
            raise CommandError(f"An error occurred during the process: {e}")

