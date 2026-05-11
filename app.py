from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import os
import sys

FACE_RECOGNITION_AVAILABLE = False
try:
    import cv2
    import face_recognition
    import numpy as np
    import pickle
    import base64
    from PIL import Image
    FACE_RECOGNITION_AVAILABLE = True
except Exception as e:
    print(f"Face recognition not available: {e}")
    pass

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hospital.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size for uploads

# File size limits for doctor photo registration
MIN_DOCTOR_PHOTO_SIZE = 1024  # 1KB in bytes
MAX_DOCTOR_PHOTO_SIZE = 10 * 1024 * 1024  # 10MB max for face images

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # admin, doctor, patient

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    address = db.Column(db.Text, nullable=False)
    medical_history = db.Column(db.Text)

class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    specialization = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    availability = db.Column(db.String(200))
    face_encoding = db.Column(db.PickleType)  # Store face encoding as pickle

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, accepted, rejected, completed, cancelled
    doctor_approval = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    notes = db.Column(db.Text)
    patient = db.relationship('Patient', backref='appointments')
    doctor = db.relationship('Doctor', backref='appointments')

class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    diagnosis = db.Column(db.Text, nullable=False)
    treatment = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    patient = db.relationship('Patient', backref='medical_records')
    doctor = db.relationship('Doctor', backref='medical_records')

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='unpaid')  # unpaid, paid
    patient = db.relationship('Patient', backref='bills')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')
    appointment = db.relationship('Appointment', backref='messages')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def deny_access():
    flash('Access denied. You do not have permission to access this page.')
    return redirect(url_for('dashboard'))

# Routes
@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.args.get('next') or request.form.get('next')
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            if next_page and urlparse(next_page).netloc == '':
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html', next_page=next_page)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role')
        
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit()
        
        # If registering as doctor, create a doctor profile
        if role == 'doctor':
            # Check if doctor already exists
            existing_doctor = Doctor.query.filter_by(email=username).first()
            if not existing_doctor:
                # Create basic doctor profile - admin can update details later
                doctor = Doctor(
                    name=username.split('@')[0].replace('.', ' ').title(),  # Basic name from email
                    specialization='General Medicine',  # Default specialization
                    phone='Not provided',
                    email=username,
                    availability='Please update availability'
                )
                db.session.add(doctor)
                db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'patient':
        # Patient dashboard
        patient = Patient.query.filter_by(email=current_user.username).first()
        if patient:
            appointments = Appointment.query.filter_by(patient_id=patient.id).all()
            bills = Bill.query.filter_by(patient_id=patient.id).all()
            doctors = Doctor.query.all()
            return render_template('dashboard.html', 
                                 appointments=appointments, 
                                 bills=bills, 
                                 doctors=doctors,
                                 patient=patient)
    elif current_user.role == 'doctor':
        # Redirect doctors to their specific dashboard
        return redirect(url_for('doctor_dashboard'))
    elif current_user.role == 'staff':
        return render_template('dashboard.html')
    
    # Admin dashboard
    return render_template('dashboard.html')

@app.route('/doctor_dashboard')
@login_required
def doctor_dashboard():
    if current_user.role != 'doctor':
        flash('Access denied. Doctor privileges required.')
        return redirect(url_for('dashboard'))
    
    # Get doctor info
    doctor = Doctor.query.filter_by(email=current_user.username).first()
    if not doctor:
        flash('Doctor profile not found.')
        return redirect(url_for('dashboard'))
    
    # Get doctor's appointments
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(Appointment.date.desc()).all()
    
    # Get doctor's patients (through appointments)
    patient_ids = set(appointment.patient_id for appointment in appointments)
    patients = Patient.query.filter(Patient.id.in_(patient_ids)).all()
    
    # Get medical records for this doctor
    medical_records = MedicalRecord.query.filter_by(doctor_id=doctor.id).order_by(MedicalRecord.date.desc()).all()
    
    # Get unread messages for this doctor
    unread_messages = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    
    return render_template('doctor_dashboard.html',
                         doctor=doctor,
                         appointments=appointments,
                         patients=patients,
                         medical_records=medical_records,
                         unread_messages=unread_messages)

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    if request.method == 'POST':
        receiver_id = request.form.get('receiver_id')
        appointment_id = request.form.get('appointment_id')
        message_text = request.form.get('message')
        
        if not message_text or not message_text.strip():
            flash('Message cannot be empty')
            return redirect(request.referrer or url_for('doctor_dashboard'))
        
        message = Message(
            sender_id=current_user.id,
            receiver_id=int(receiver_id),
            appointment_id=int(appointment_id) if appointment_id else None,
            message=message_text.strip()
        )
        db.session.add(message)
        db.session.commit()
        flash('Message sent successfully')
        
    return redirect(request.referrer or url_for('doctor_dashboard'))

@app.route('/chat/<int:appointment_id>')
@login_required
def chat(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Check if user is authorized to view this chat
    if current_user.role == 'doctor':
        doctor = Doctor.query.filter_by(email=current_user.username).first()
        if not doctor or appointment.doctor_id != doctor.id:
            flash('Access denied')
            return redirect(url_for('doctor_dashboard'))
    elif current_user.role == 'patient':
        patient = Patient.query.filter_by(email=current_user.username).first()
        if not patient or appointment.patient_id != patient.id:
            flash('Access denied')
            return redirect(url_for('dashboard'))
    else:
        flash('Access denied')
        return redirect(url_for('dashboard'))
    
    # Get all messages for this appointment
    messages = Message.query.filter_by(appointment_id=appointment_id).order_by(Message.timestamp).all()
    
    # Mark messages as read for current user
    for message in messages:
        if message.receiver_id == current_user.id and not message.is_read:
            message.is_read = True
    db.session.commit()
    
    return render_template('chat.html', appointment=appointment, messages=messages)

@app.route('/doctor_patients')
@login_required
def doctor_patients():
    if current_user.role != 'doctor':
        flash('Access denied. Doctor privileges required.')
        return redirect(url_for('dashboard'))
    
    doctor = Doctor.query.filter_by(email=current_user.username).first()
    if not doctor:
        flash('Doctor profile not found.')
        return redirect(url_for('dashboard'))
    
    # Get patients through appointments
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    patient_ids = set(appointment.patient_id for appointment in appointments)
    patients = Patient.query.filter(Patient.id.in_(patient_ids)).all()
    
    return render_template('doctor_patients.html', patients=patients, doctor=doctor, appointments=appointments)

@app.route('/add_medical_record/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def add_medical_record_for_patient(patient_id):
    if current_user.role != 'doctor':
        flash('Access denied. Doctor privileges required.')
        return redirect(url_for('dashboard'))
    
    doctor = Doctor.query.filter_by(email=current_user.username).first()
    patient = Patient.query.get_or_404(patient_id)
    
    # Check if doctor has access to this patient
    appointment = Appointment.query.filter_by(doctor_id=doctor.id, patient_id=patient_id).first()
    if not appointment:
        flash('You do not have access to this patient.')
        return redirect(url_for('doctor_dashboard'))
    
    if request.method == 'POST':
        diagnosis = request.form.get('diagnosis')
        treatment = request.form.get('treatment')
        
        record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=doctor.id,
            diagnosis=diagnosis,
            treatment=treatment
        )
        db.session.add(record)
        db.session.commit()
        flash('Medical record added successfully')
        return redirect(url_for('doctor_patients'))
    
    return render_template('add_medical_record.html', patient=patient, doctor=doctor)

# Patient routes
@app.route('/patients')
@login_required
def patients():
    if current_user.role == 'staff':
        return deny_access()
    patients = Patient.query.all()
    return render_template('patients.html', patients=patients)

@app.route('/add_patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    if current_user.role not in ['admin', 'staff']:
        return deny_access()
    if request.method == 'POST':
        name = request.form.get('name')
        age = request.form.get('age')
        gender = request.form.get('gender')
        phone = request.form.get('phone')
        email = request.form.get('email')
        address = request.form.get('address')
        medical_history = request.form.get('medical_history')
        patient = Patient(name=name, age=age, gender=gender, phone=phone, email=email, address=address, medical_history=medical_history)
        db.session.add(patient)
        db.session.commit()
        flash('Patient added successfully')
        if current_user.role == 'staff':
            return redirect(url_for('dashboard'))
        return redirect(url_for('patients'))
    return render_template('add_patient.html')

@app.route('/edit_patient/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_patient(id):
    if current_user.role not in ['admin', 'doctor']:
        return deny_access()
    patient = Patient.query.get_or_404(id)
    if request.method == 'POST':
        patient.name = request.form.get('name')
        patient.age = request.form.get('age')
        patient.gender = request.form.get('gender')
        patient.phone = request.form.get('phone')
        patient.email = request.form.get('email')
        patient.address = request.form.get('address')
        patient.medical_history = request.form.get('medical_history')
        db.session.commit()
        flash('Patient updated successfully')
        return redirect(url_for('patients'))
    return render_template('edit_patient.html', patient=patient)

@app.route('/delete_patient/<int:id>', methods=['POST'])
@login_required
def delete_patient(id):
    if current_user.role != 'admin':
        return deny_access()
    patient = Patient.query.get_or_404(id)

    # Remove dependent bills, appointments, medical records, and messages first
    for bill in list(patient.bills):
        db.session.delete(bill)
    for appointment in list(patient.appointments):
        for message in list(appointment.messages):
            db.session.delete(message)
        db.session.delete(appointment)
    for record in list(patient.medical_records):
        db.session.delete(record)

    db.session.delete(patient)
    db.session.commit()
    flash('Patient deleted successfully')
    return redirect(url_for('patients'))

# Doctor routes
@app.route('/doctors')
@login_required
def doctors():
    if current_user.role == 'staff':
        return deny_access()
    doctors = Doctor.query.all()
    return render_template('doctors.html', doctors=doctors)

@app.route('/add_doctor', methods=['GET', 'POST'])
@login_required
def add_doctor():
    if current_user.role != 'admin':
        return deny_access()
    if request.method == 'POST':
        name = request.form.get('name')
        specialization = request.form.get('specialization')
        phone = request.form.get('phone')
        email = request.form.get('email')
        availability = request.form.get('availability')
        doctor = Doctor(name=name, specialization=specialization, phone=phone, email=email, availability=availability)
        db.session.add(doctor)
        db.session.commit()
        flash('Doctor added successfully')
        return redirect(url_for('doctors'))
    return render_template('add_doctor.html')

@app.route('/edit_doctor/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_doctor(id):
    if current_user.role != 'admin':
        return deny_access()
    doctor = Doctor.query.get_or_404(id)
    if request.method == 'POST':
        doctor.name = request.form.get('name')
        doctor.specialization = request.form.get('specialization')
        doctor.phone = request.form.get('phone')
        doctor.email = request.form.get('email')
        doctor.availability = request.form.get('availability')
        db.session.commit()
        flash('Doctor updated successfully')
        return redirect(url_for('doctors'))
    return render_template('edit_doctor.html', doctor=doctor)

@app.route('/delete_doctor/<int:id>', methods=['POST'])
@login_required
def delete_doctor(id):
    if current_user.role != 'admin':
        return deny_access()
    doctor = Doctor.query.get_or_404(id)

    # Delete dependent appointments and related messages first
    for appointment in list(doctor.appointments):
        for message in list(appointment.messages):
            db.session.delete(message)
        db.session.delete(appointment)

    # Delete dependent medical records
    for record in list(doctor.medical_records):
        db.session.delete(record)

    db.session.delete(doctor)
    db.session.commit()
    flash('Doctor deleted successfully')
    return redirect(url_for('doctors'))

@app.route('/register_face/<int:id>', methods=['GET', 'POST'])
@login_required
def register_face(id):
    if not FACE_RECOGNITION_AVAILABLE:
        flash('Face recognition not available in this environment')
        return redirect(url_for('doctors'))
    doctor = Doctor.query.get_or_404(id)
    if request.method == 'POST':
        image_data = request.form.get('image_data', '').strip()
        file = request.files.get('face_image')
        image = None
        
        # Try to process uploaded file first if present and valid
        if file and file.filename:
            try:
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                
                if file_size < MIN_DOCTOR_PHOTO_SIZE:
                    flash('Image size is too small. Minimum size is 1KB.')
                    return render_template('register_face.html', doctor=doctor)
                elif file_size > MAX_DOCTOR_PHOTO_SIZE:
                    flash('Image size is too large. Maximum size is 100MB.')
                    return render_template('register_face.html', doctor=doctor)
                
                image = Image.open(file.stream)
            except Exception as e:
                flash('Invalid image file. Please upload a valid image.')
                return render_template('register_face.html', doctor=doctor)
        # Otherwise try camera capture data
        elif image_data:
            try:
                if ',' in image_data:
                    header, encoded = image_data.split(',', 1)
                else:
                    encoded = image_data
                file_bytes = base64.b64decode(encoded)
                image = Image.open(BytesIO(file_bytes))
            except Exception as e:
                flash('Invalid image data from camera. Please try again.')
                return render_template('register_face.html', doctor=doctor)
        
        if image is not None:
            try:
                image = np.array(image)
                face_locations = face_recognition.face_locations(image)
                if face_locations:
                    face_encoding = face_recognition.face_encodings(image, face_locations)[0]
                    doctor.face_encoding = face_encoding
                    db.session.commit()
                    flash('Face registered successfully')
                    return redirect(url_for('doctors'))
                else:
                    flash('No face detected in the image. Please try with a clearer photo.')
            except Exception as e:
                flash('Error processing face image. Please try again.')
        else:
            flash('Please provide a face image using the camera or upload a file')
    return render_template('register_face.html', doctor=doctor)

@app.route('/face_login', methods=['GET', 'POST'])
def face_login():
    if not FACE_RECOGNITION_AVAILABLE:
        flash('Face recognition not available in this environment')
        return redirect(url_for('login'))
    if request.method == 'POST':
        image_data = request.form.get('image_data')
        file = request.files.get('face_image')
        image = None
        if image_data:
            try:
                header, encoded = image_data.split(',', 1)
                file_bytes = base64.b64decode(encoded)
                image = Image.open(BytesIO(file_bytes))
            except Exception:
                image = None
        elif file:
            image = Image.open(file.stream)

        if image is not None:
            image = np.array(image)
            face_locations = face_recognition.face_locations(image)
            if face_locations:
                face_encoding = face_recognition.face_encodings(image, face_locations)[0]
                doctors = Doctor.query.filter(Doctor.face_encoding.isnot(None)).all()
                for doctor in doctors:
                    matches = face_recognition.compare_faces([doctor.face_encoding], face_encoding)
                    if matches[0]:
                        user = User.query.filter_by(username=doctor.email).first()
                        if not user:
                            user = User(username=doctor.email, password=generate_password_hash('face'), role='doctor')
                            db.session.add(user)
                            db.session.commit()
                            
                            # Ensure doctor profile exists (safety check, though it should already exist)
                            existing_doctor = Doctor.query.filter_by(email=user.username).first()
                            if not existing_doctor:
                                doctor_profile = Doctor(
                                    name=user.username.split('@')[0].replace('.', ' ').title(),
                                    specialization='General Medicine',
                                    phone='Not provided',
                                    email=user.username,
                                    availability='Please update availability'
                                )
                                db.session.add(doctor_profile)
                                db.session.commit()
                        
                        login_user(user)
                        flash('Face login successful')
                        return redirect(url_for('dashboard'))
                flash('Face not recognized')
            else:
                flash('No face detected in the image')
        else:
            flash('Please provide a face image using the camera or upload a file')
    return render_template('face_login.html')

# Appointment routes
@app.route('/appointments')
@login_required
def appointments():
    if current_user.role == 'staff':
        return deny_access()
    appointments = Appointment.query.all()
    return render_template('appointments.html', appointments=appointments)

@app.route('/appointment/<int:id>/accept', methods=['POST'])
@login_required
def accept_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    if current_user.role == 'doctor':
        doctor = Doctor.query.filter_by(email=current_user.username).first()
        if doctor and appointment.doctor_id == doctor.id:
            appointment.doctor_approval = 'accepted'
            appointment.status = 'accepted'
            db.session.commit()
            flash('Appointment accepted successfully')
            return redirect(url_for('appointments'))
    flash('You are not authorized to accept this appointment')
    return redirect(url_for('appointments'))

@app.route('/appointment/<int:id>/reject', methods=['POST'])
@login_required
def reject_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    if current_user.role == 'doctor':
        doctor = Doctor.query.filter_by(email=current_user.username).first()
        if doctor and appointment.doctor_id == doctor.id:
            appointment.doctor_approval = 'rejected'
            appointment.status = 'rejected'
            db.session.commit()
            flash('Appointment rejected')
            return redirect(url_for('appointments'))
    flash('You are not authorized to reject this appointment')
    return redirect(url_for('appointments'))

@app.route('/add_appointment', methods=['GET', 'POST'])
@login_required
def add_appointment():
    if current_user.role not in ['admin', 'doctor', 'patient']:
        return deny_access()
    patients = Patient.query.all()
    doctors = Doctor.query.all()
    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        doctor_id = request.form.get('doctor_id')
        date_str = request.form.get('date')
        date = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        appointment = Appointment(patient_id=patient_id, doctor_id=doctor_id, date=date)
        db.session.add(appointment)
        db.session.commit()
        flash('Appointment scheduled successfully')
        return redirect(url_for('appointments'))
    return render_template('add_appointment.html', patients=patients, doctors=doctors)

# Medical Records
@app.route('/medical_records')
@login_required
def medical_records():
    if current_user.role not in ['admin', 'doctor']:
        return deny_access()
    records = MedicalRecord.query.all()
    return render_template('medical_records.html', records=records)

@app.route('/add_medical_record', methods=['GET', 'POST'])
@login_required
def add_medical_record():
    if current_user.role not in ['admin', 'doctor']:
        return deny_access()
    patients = Patient.query.all()
    doctors = Doctor.query.all()
    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        doctor_id = request.form.get('doctor_id')
        diagnosis = request.form.get('diagnosis')
        treatment = request.form.get('treatment')
        record = MedicalRecord(patient_id=patient_id, doctor_id=doctor_id, diagnosis=diagnosis, treatment=treatment)
        db.session.add(record)
        db.session.commit()
        flash('Medical record added successfully')
        return redirect(url_for('medical_records'))
    return render_template('add_medical_record.html', patients=patients, doctors=doctors)

# Bills
@app.route('/bills')
@login_required
def bills():
    if current_user.role == 'staff':
        return deny_access()
    bills = Bill.query.all()
    return render_template('bills.html', bills=bills)

@app.route('/add_bill', methods=['GET', 'POST'])
@login_required
def add_bill():
    if current_user.role not in ['admin', 'staff', 'doctor']:
        return deny_access()
    patients = Patient.query.all()
    if request.method == 'POST':
        patient_id = request.form.get('patient_id')
        amount = request.form.get('amount')
        description = request.form.get('description')
        bill = Bill(patient_id=patient_id, amount=amount, description=description)
        db.session.add(bill)
        db.session.commit()
        flash('Bill created successfully')
        if current_user.role == 'staff':
            return redirect(url_for('dashboard'))
        return redirect(url_for('bills'))
    return render_template('add_bill.html', patients=patients)

@app.route('/bill/<int:id>/status/<status>', methods=['POST'])
@login_required
def update_bill_status(id, status):
    bill = Bill.query.get_or_404(id)
    if status in ['paid', 'unpaid']:
        bill.status = status
        db.session.commit()
        flash(f'Bill status updated to {status}')
    return redirect(url_for('bills'))

@app.route('/bill/<int:id>/pdf')
@login_required
def generate_bill_pdf(id):
    bill = Bill.query.get_or_404(id)
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#0d6efd'),
        spaceAfter=30,
        alignment=1
    )
    
    # Title
    elements.append(Paragraph("GOVERNMENT HOSPITAL, SHIKARIPURA", title_style))
    elements.append(Paragraph("Bill Receipt", styles['Heading2']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Bill details
    bill_data = [
        ['Bill ID:', str(bill.id)],
        ['Patient Name:', bill.patient.name],
        ['Patient Email:', bill.patient.email],
        ['Patient Phone:', bill.patient.phone],
        ['Date:', bill.date.strftime('%Y-%m-%d %H:%M:%S')],
        ['Description:', bill.description],
        ['Amount:', f'₹{bill.amount:.2f}'],
        ['Status:', bill.status.upper()],
    ]
    
    bill_table = Table(bill_data, colWidths=[2*inch, 4*inch])
    bill_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eef3ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    
    elements.append(bill_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Footer
    status_color = colors.HexColor('#28a745') if bill.status == 'paid' else colors.HexColor('#dc3545')
    elements.append(Paragraph(f"<b>Payment Status: <font color='{status_color.hexval()}'>{bill.status.upper()}</font></b>", styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph("Thank you for your business!", styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'bill_{bill.id}.pdf'
    )

@app.route('/bill/<int:id>/print')
@login_required
def print_bill(id):
    bill = Bill.query.get_or_404(id)
    return render_template('print_bill.html', bill=bill)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
    app.run(debug=True)