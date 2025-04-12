# 📚 Library Management System (LMS)

A Django-based REST API and admin interface for managing books, authors, genres, and user interactions like borrowing, user registration, and more. This system supports authentication, user roles, book catalog management, and admin/librarian dashboards.

---

## 🚀 Features

- User authentication (Register, Login, Logout, Change Password)
- Custom user model with roles (User, Admin/Librarian)
- Book, author, and genre models with cover image support
- Admin dashboard to manage books, genres, and authors
- API to list, create, update, and delete books/authors/genres
- Search and filter functionality
- Token-based authentication
- HTML views for book listings and details (Django templates)

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
| Method | Endpoint     | Description                                 |
|--------|--------------|---------------------------------------------|
| GET    | `/`          | List all books (supports search/filter)     |
| POST   | `/`          | Create a new book                           |
| GET    | `/:id/`      | Get details of a specific book              |
| PUT    | `/:id/`      | Update book info                            |
| DELETE | `/:id/`      | Delete a book                               |

🔍 Supports:
- Search by `title`, `summary`:  
  `GET /api/books/?search=harry`
- Filter by `author ID`:  
  `GET /api/books/?authors=1`
- Filter by `genre ID`:  
  `GET /api/books/?genres=1`

---

### ✍️ Authors – `/api/authors/`
| Method | Endpoint             | Description                             |
|--------|----------------------|-----------------------------------------|
| GET    | `/`                  | List all authors (supports name search) |
| POST   | `/`                  | Create a new author                     |
| GET    | `/:id/`              | Get details of a specific author        |
| PUT    | `/:id/`              | Update author info                      |
| DELETE | `/:id/`              | Delete an author                        |

---

### 🎨 Genres – `/api/genres/`
| Method | Endpoint             | Description                             |
|--------|----------------------|-----------------------------------------|
| GET    | `/`                  | List all genres                         |
| POST   | `/`                  | Create a new genre                      |
| GET    | `/:id/`              | Get details of a specific genre         |
| PUT    | `/:id/`              | Update genre info                       |
| DELETE | `/:id/`              | Delete a genre                          |

---

## 🖥️ Admin Panel

Visit `/admin/` with a superuser account to:
- Manage Books, Authors, and Genres via dashboard
- Use search, filters, and inline ManyToMany management
- Upload and preview book cover images

---

## 🌐 HTML Views

| Route            | Description                 |
|------------------|-----------------------------|
| `/books/`        | Book list with search       |
| `/books/<id>/`   | Book detail page            |

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

# 2. Set up virtual environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply migrations
python manage.py makemigrations users
python manage.py makemigrations books
python manage.py migrate

# 5. Create a superuser (admin account)
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
