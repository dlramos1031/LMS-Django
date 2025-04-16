# 📚 Library Management System (LMS)

A Django-based web application and RESTful API for managing a physical library, built with Django REST Framework, Bootstrap 5, and role-based access control.

---

## 🚀 Features

### 👤 User Management
- Register and login (Web and API)
- Token-based authentication for API
- Change password and view user profile
- Roles: `member`, `librarian`/`admin`

### 📚 Book Management
- Admins can add, edit, or delete books
- Books support multiple authors and genres
- Book list with search and filters
- Detail view with availability and borrow modal

### 🔄 Borrowing System
- Members request to borrow books
- Borrow requests require librarian approval
- Return handled in person, confirmed by librarian
- Users choose return date (fixed duration or custom)
- `total_borrows` field tracks popularity of books

### 🧑‍🏫 Librarian Dashboard
- Tabs for pending, active, and completed borrowings
- Add/edit/delete users and books with Bootstrap modals
- Search and pagination in dashboard tables

### 🔍 Real-Time Validation
- Live username and email availability check on registration
- Password match and strength feedback
- Frontend validation synced with backend logic

---

## 🔌 API Endpoints

### 🔐 Authentication (`/api/auth/`)
| Method | Endpoint             | Description                   |
|--------|----------------------|-------------------------------|
| POST   | `/register/`         | Register new user             |
| POST   | `/login/`            | Get token                     |
| POST   | `/logout/`           | Logout and revoke token       |
| POST   | `/change-password/`  | Change password               |
| GET    | `/check-username/`   | Check if username is taken    |
| GET    | `/check-email/`      | Check if email is registered  |

### 📚 Books API (`/api/`)
| Method | Endpoint             | Description                   |
|--------|----------------------|-------------------------------|
| GET    | `/books/`            | List books with filters       |
| GET    | `/books/<id>/`       | Get book details              |
| GET    | `/authors/`          | List authors (name filter)    |
| GET    | `/genres/`           | List genres                   |
| GET    | `/borrow/`           | List borrow records           |
| POST   | `/borrow/`           | Submit borrow request         |

---

## 🖥️ Web Routes

| Route                         | Description                         |
|-------------------------------|-------------------------------------|
| `/register/`                  | Web register page                   |
| `/login/`                     | Login page                          |
| `/logout/`                    | Logout (redirects to login)         |
| `/change-password/`           | Change password                     |
| `/books/`                     | Book list view                      |
| `/books/<id>/`                | Book detail page                    |
| `/books/<id>/borrow/`         | Submit borrow request (form modal)  |
| `/profile/<user_id>/`         | User profile and borrow history     |
| `/dashboard/`                 | Librarian dashboard                 |
| `/dashboard/users/...`        | Add/edit/delete users               |
| `/dashboard/books/...`        | Add/edit/delete books               |
| `/dashboard/approve/...`      | Approve borrow request              |
| `/dashboard/reject/...`       | Reject borrow request               |
| `/dashboard/return/...`       | Confirm book return                 |

---

## 🛠️ Setup & Installation

```bash
# Clone the repo
git clone https://github.com/dlramos1031/LMS-Django.git
cd lms-django

# Set up a virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py makemigrations
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Run the development server
python manage.py runserver
