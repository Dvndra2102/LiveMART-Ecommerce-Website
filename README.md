# LiveMART - Multi-Role E-Commerce Platform

A comprehensive Django-based e-commerce platform with support for multiple user roles: Customers, Retailers, and Wholesalers.

## Features

### User Roles
- **Customer**: Browse products, add to cart, place orders, track deliveries, give feedback
- **Retailer**: Manage products, view orders, respond to customer feedback
- **Wholesaler**: Manage wholesale products, receive orders from retailers
- **Admin**: Full access to the platform via Django Admin

### Core Features
- User authentication (email + password, Google OAuth, OTP login)
- Product management with categories
- Shopping cart functionality
- Order management with progress tracking
- Payment integration (Razorpay)
- Cash on Delivery option
- Feedback system
- Wholesale ordering for retailers

## Tech Stack

- **Backend**: Django 4.x
- **Database**: SQLite (default)
- **Authentication**: django-allauth
- **Payment Gateway**: Razorpay
- **Python**: 3.x

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd LiveMART
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1  # Windows
   source venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies**
   ```bash
   pip install django django-allauth
   ```

4. **Run migrations**
   ```bash
   python manage.py migrate
   ```

5. **Create a superuser**
   ```bash
   python manage.py createsuperuser
   ```

6. **Start the development server**
   ```bash
   python manage.py runserver
   ```

7. **Visit the application**
   - Frontend: http://localhost:8000
   - Admin panel: http://localhost:8000/admin

## Project Structure

```
LiveMART/
├── livemart/          # Main project directory
│   ├── settings.py    # Project settings
│   ├── urls.py        # Main URL config
│   └── wsgi.py
├── users/             # User management app
├── store/             # Product and store management
├── orders/            # Order management
├── wholesale/         # Wholesale functionality
├── templates/         # HTML templates
└── manage.py          # Django management script
```

## Configuration

### Environment Variables
- `SECRET_KEY`: Django secret key
- `RAZORPAY_KEY_ID`: Razorpay API key
- `RAZORPAY_KEY_SECRET`: Razorpay API secret
- Google OAuth credentials (optional)

## License

This project is for educational purposes.
