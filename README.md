# Society Event Management System - System Development Unit
A cloud-native web application for managing society events, user RSVPs, and feedback.
The system showcases secure cloud deployment, hybrid data persistence, RESTful APIs, and role-based access control using Google Cloud Platform.


## 1. Application Overview
The application allows society members to browse events and manage RSVPs, while committee members and administrators can create events, view attendance, and manage users. The system is deployed on Google App Engine and integrates Google Cloud services.

## 2. Technology Stacks
### Technology (layer)
* HTML, Jinja2, Bootstrap 5 (front-end)
* Python, Flask (back-end)
* SQL (via SQLAlchemy) (relational database)
* Google Firestore (NoSQL database)
* Google Cloud Storage (object storage)
* Flask REST endpoints (APIs)
* Google Cloud Functions (cloud functions)
* Google App Engine (deployment)
* Pytest (testing)
* GitHub (version control)

## 3. Data Persistence Strategy
The system uses a hybrid persistence model:

### SQL Database (Structured Data)
* Users
* Events
* RSVPs
* Feedback

Relational storage ensures data integrity, referential constraints, and transactional consistency.

### NoSQL Database (Semi-Structured Data)
* Activity logs
* Admin audit records

Firestore was selected for its flexibility, scalability, and suitability for log-based data with evolving schemas.

### Cloud Storage (Unstructured Data)
* Event images

This separation ensures each data type is stored using the most appropriate technology.

## 4. Cloud Security
Security is implemented using multiple strategies:
* Password hashing before database storage
* Session-based authentication
* Role-based access control (Member, Committee, Admin)
* Restricted route access based on user roles
* Google Cloud IAM enforcing least-privilege access
* Environment variables for sensitive configuration

## 5. Cloud APIs & Cloud Functions
### REST APIs
Custom RESTful endpoints handle RSVP and feedback submission, enabling decoupled and testable application logic.

### Google Cloud Functions
A Cloud Function is used for asynchronous logging of RSVP activity. This improves scalability by decoupling logging from core application logic and demonstrates serverless computing.

## 6. Deployment Model
The application is deployed using Google App Engine, providing:
* Managed infrastructure
* Automatic scaling
* Built-in security
* Seamless integration with Google Cloud services

### Deployment Command
```gcloud app deploy```

### Monitoring
```gcloud app logs tail -s default```

## 7. Testing & Code Quality
Unit tests are implemented using Pytest, covering:
* Authentication
* Role-based access control
* RSVP logic
* API endpoints

Tests can be executed using:
```pytest```

## 8. Version Control
The project uses GitHub for version control with regular commits demonstrating incremental development and feature progression.

9. Future Improvements
* Federated authentication using Google Identity Platform
* Expanded REST API coverage
* Increased test coverage
* Accessibility improvements
* Event analytics dashboard
