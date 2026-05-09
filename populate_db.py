from app import app, db, Patient, Doctor, Appointment, MedicalRecord, Bill
from datetime import datetime

def populate_db():
    with app.app_context():
        # Sample Doctors
        if not Doctor.query.first():
            doctor1 = Doctor(name='Dr. John Smith', specialization='Cardiology', phone='123-456-7890', email='john@example.com', availability='Mon-Fri 9AM-5PM')
            doctor2 = Doctor(name='Dr. Jane Doe', specialization='Neurology', phone='987-654-3210', email='jane@example.com', availability='Tue-Sat 10AM-6PM')
            db.session.add(doctor1)
            db.session.add(doctor2)
            db.session.commit()

        # Sample Patients
        if not Patient.query.first():
            patient1 = Patient(name='Alice Johnson', age=30, gender='Female', phone='555-1234', email='alice@example.com', address='123 Main St', medical_history='None')
            patient2 = Patient(name='Bob Wilson', age=45, gender='Male', phone='555-5678', email='bob@example.com', address='456 Oak Ave', medical_history='Hypertension')
            db.session.add(patient1)
            db.session.add(patient2)
            db.session.commit()

        # Sample Appointments
        if not Appointment.query.first():
            doctors = Doctor.query.all()
            patients = Patient.query.all()
            if doctors and patients:
                appt1 = Appointment(patient_id=patients[0].id, doctor_id=doctors[0].id, date=datetime(2023, 6, 15, 10, 0))
                appt2 = Appointment(patient_id=patients[1].id, doctor_id=doctors[1].id, date=datetime(2023, 6, 16, 14, 0))
                db.session.add(appt1)
                db.session.add(appt2)
                db.session.commit()

        # Sample Medical Records
        if not MedicalRecord.query.first():
            doctors = Doctor.query.all()
            patients = Patient.query.all()
            if doctors and patients:
                record1 = MedicalRecord(patient_id=patients[0].id, doctor_id=doctors[0].id, diagnosis='Mild chest pain', treatment='Rest and monitoring')
                record2 = MedicalRecord(patient_id=patients[1].id, doctor_id=doctors[1].id, diagnosis='Headache', treatment='Pain medication')
                db.session.add(record1)
                db.session.add(record2)
                db.session.commit()

        # Sample Bills
        if not Bill.query.first():
            patients = Patient.query.all()
            if patients:
                bill1 = Bill(patient_id=patients[0].id, amount=150.00, description='Consultation fee')
                bill2 = Bill(patient_id=patients[1].id, amount=200.00, description='Neurological examination')
                db.session.add(bill1)
                db.session.add(bill2)
                db.session.commit()

        print("Sample data populated")

if __name__ == '__main__':
    populate_db()