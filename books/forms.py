from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Book, BookCopy, Category, Author, Borrowing
from users.models import CustomUser
from django.utils import timezone
from datetime import timedelta

class BookForm(forms.ModelForm):
    """Form for creating and updating Book instances."""
    class Meta:
        model = Book
        fields = [
            'isbn', 'title', 'authors', 'categories', 'publisher',
            'publication_date', 'edition', 'page_count', 'description',
            'cover_image'
        ]
        widgets = {
            'authors': forms.SelectMultiple(attrs={'class': 'form-select select2-multiple', 'data-placeholder': _('Select Authors')}),
            'categories': forms.SelectMultiple(attrs={'class': 'form-select select2-multiple', 'data-placeholder': _('Select Categories')}),
            'publication_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'isbn': forms.TextInput(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'publisher': forms.TextInput(attrs={'class': 'form-control'}),
            'edition': forms.TextInput(attrs={'class': 'form-control'}),
            'page_count': forms.NumberInput(attrs={'class': 'form-control'}),
            'cover_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'authors': _('Hold down "Control", or "Command" on a Mac, to select more than one.'),
            'categories': _('Hold down "Control", or "Command" on a Mac, to select more than one.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # For create view, ISBN should be editable. For update, it's usually not.
        if self.instance and self.instance.pk: # If instance exists (editing)
            self.fields['isbn'].disabled = True
            self.fields['isbn'].help_text = _('ISBN cannot be changed after creation.')


class BookCopyForm(forms.ModelForm):
    """Form for creating and updating BookCopy instances.
       The 'book' field is intended to be set by the view, not directly by the user in this form.
    """
    class Meta:
        model = BookCopy
        fields = ['copy_id', 'status', 'date_acquired', 'condition_notes']
        widgets = {
            'copy_id': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'date_acquired': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'condition_notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CategoryForm(forms.ModelForm):
    """Form for creating and updating Category instances."""
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = [
            'name', 'biography', 'date_of_birth', 'date_of_death', 
            'nationality', 'alternate_names', 'author_website', 'author_photo'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'biography': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_of_death': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'nationality': forms.TextInput(attrs={'class': 'form-control'}),
            'alternate_names': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('e.g., Mark Twain, J.K. Rowling')}),
            'author_website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': _('https://example.com')}),
            'author_photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

class IssueBookForm(forms.Form):
    """Form for staff to issue a book copy to a borrower."""
    borrower = forms.ModelChoiceField(
        queryset=CustomUser.objects.filter(role='BORROWER', is_active=True).order_by('username'),
        widget=forms.Select(attrs={'class': 'form-select select2-searchable'}),
        label=_("Select Borrower"),
        help_text=_("Select the registered borrower.")
    )
    book_copy = forms.ModelChoiceField(
        queryset=BookCopy.objects.filter(status='Available').select_related('book').order_by('book__title', 'copy_id'),
        widget=forms.Select(attrs={'class': 'form-select select2-searchable'}),
        label=_("Select Available Book Copy"),
        help_text=_("Only copies currently marked 'Available' are listed.")
    )
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label=_("Due Date"),
        required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial due date, e.g., 2 weeks from today
        self.fields['due_date'].initial = timezone.now().date() + timedelta(days=14)

    def clean_due_date(self):
        due_date = self.cleaned_data.get('due_date')
        if due_date and due_date < timezone.now().date():
            raise forms.ValidationError(_("Due date cannot be in the past."))
        return due_date
    
    def clean_book_copy(self):
        book_copy = self.cleaned_data.get('book_copy')
        if book_copy and book_copy.status != 'Available':
            raise forms.ValidationError(_(f"The selected book copy '{book_copy.copy_id}' is no longer available. Its status is {book_copy.get_status_display()}."))
        return book_copy

class ReturnBookForm(forms.Form):
    """Form for staff to process a book return using the BookCopy ID."""
    book_copy_identifier = forms.CharField(
        label=_("Book Copy ID or Barcode"),
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Scan or enter Book Copy ID')}),
        help_text=_("Enter the unique identifier of the copy being returned.")
    )

    def clean_book_copy_identifier(self):
        identifier = self.cleaned_data.get('book_copy_identifier')
        try:
            book_copy = BookCopy.objects.get(copy_id=identifier)
            if not Borrowing.objects.filter(book_copy=book_copy, status__in=['ACTIVE', 'OVERDUE']).exists():
                raise forms.ValidationError(_("This book copy does not appear to be on an active loan."))
        except BookCopy.DoesNotExist:
            raise forms.ValidationError(_("No book copy found with this identifier."))
        return identifier

# You might also need forms for staff to manage borrow requests if you want more than just buttons:
# class ApproveRejectRequestForm(forms.Form):
# notes = forms.CharField(widget=forms.Textarea, required=False, label=_("Notes for Borrower (Optional)"))