# 📚 Library Management System (LMS)

A Django-based REST API for managing books, authors, and user interactions like borrowing, user registration, and more. This system supports authentication, user roles, book catalog management, and will be extended with borrowing and notification features.

---

## 🚀 Features

- User authentication (Register, Login, Logout, Change Password)
- Custom user model with roles (User, Admin/Librarian)
- Book and author models with cover image support
- API to list, create, update, and delete books/authors
- Search and filter functionality
- Token-based authentication

---

## 📦 API Endpoints

### 🔐 Authentication – `/api/auth/`
| Method | Endpoint             | Description                         |
|--------|----------------------|-------------------------------------|
| POST   | `/register/`         | Register a new user                 |
| POST   | `/login/`            | Login and get auth token            |
| POST   | `/logout/`           | Logout and invalidate token         |
| POST   | `/change-password/`  | Change user password                |

---

### 📚 Books – `/api/books/`
| Method | Endpoint             | Description                                 |
|--------|----------------------|---------------------------------------------|
| GET    | `/`                  | List all books (supports search/filter)     |
| POST   | `/`                  | Create a new book                           |
| GET    | `/:id/`              | Get details of a specific book              |
| PUT    | `/:id/`              | Update book info                            |
| DELETE | `/:id/`              | Delete a book                               |

🔍 Supports:
- Search by `title`, `summary`:  
  `GET /api/books/?search=harry`
- Filter by `author ID`:  
  `GET /api/books/?authors=1`

---

### ✍️ Authors – `/api/authors/`
| Method | Endpoint             | Description                             |
|--------|----------------------|-----------------------------------------|
| GET    | `/`                  | List all authors (supports name search) |
| POST   | `/`                  | Create a new author                     |
| GET    | `/:id/`              | Get details of a specific author        |
| PUT    | `/:id/`              | Update author info                      |
| DELETE | `/:id/`              | Delete an author                        |

🔍 Supports:
- Search by `name`:  
  `GET /api/authors/?search=rowling`

---

## 💻 Getting Started

### 🔧 Requirements
- Python 3.8+
- pip
- Git

---

### 📥 Installation

```bash
# 1. Clone the repo
git clone https://github.com/dlramos1031/LMS-Django.git
cd lms

# 2. Set up virtual environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply migrations
python manage.py makemigrations
python manage.py migrate

# 5. Create a superuser (admin account)
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver