# Hospital Management System

A comprehensive Python-based hospital management system built with Flask and SQLAlchemy.

## Features

- User authentication (Admin, Doctor, Patient roles)
- Patient management (Add, view, edit, delete patients)
- Doctor management
- Appointment scheduling
- Medical records management
- Billing system
- User-friendly web interface with Bootstrap

## Installation

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Initialize the database and create admin user:
   ```
   python init_db.py
   ```

3. (Optional) Populate with sample data:
   ```
   python populate_db.py
   ```

4. Run the application:
   ```
   python app.py
   ```

5. Open your browser and go to `http://127.0.0.1:5000/`

## Usage

- Login with admin credentials: username='admin', password='admin123'
- Manage patients, doctors, appointments, medical records, and bills through the web interface

## Database

The application uses SQLite database (`hospital.db`) which is created automatically on first run.

## Technologies Used

- Flask
- SQLAlchemy
- Flask-Login
- Bootstrap 5
- Python 3.x