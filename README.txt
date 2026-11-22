# Employee Attendance & PC Activity Tracker
## MVP Requirements & Development Specification

Version: 1.0
Project Type: Internal Employee Attendance and PC Activity Tracking System
MVP Scope: Small, focused application

---

## 1. PROJECT OVERVIEW

Build a small web-based employee attendance and PC activity tracking application.

The application has two primary purposes:

1. Track employee attendance using GPS-based check-in/check-out.
2. Track basic employee PC usage through a lightweight Windows desktop agent.

The system should be simple, lightweight, and reliable.

The MVP must NOT become a full HR, payroll, project management, or invasive employee surveillance platform.

---

## 2. CORE MVP FEATURES

### Employee Management
- Admin login
- Add employee
- Edit employee
- Disable employee
- Employee department/designation
- Employee work schedule
- Leave balance

### Attendance
- GPS-based check-in
- GPS-based check-out
- Check-in location
- Check-out location
- Office location configuration
- Office radius configuration
- On-time/late detection
- Late minutes
- Present/absent/leave status
- Attendance history
- Attendance dashboard

### PC Activity
- Windows desktop agent
- PC online/offline tracking
- PC startup/shutdown tracking
- Active time tracking
- Idle time tracking
- Application/software usage tracking
- Website/domain usage tracking
- Application usage duration
- Website usage duration
- Daily activity timeline

### Dashboard & Reports
- Admin dashboard
- Employee dashboard
- Employee activity page
- Attendance reports
- PC activity reports
- Date filtering
- Basic CSV/Excel export

---

## 3. USER TYPES

### Admin

Admin can:
- Login
- Manage employees
- Configure office location
- Configure work hours
- Set leave balances
- View all attendance
- View employee GPS check-in locations
- View PC activity
- View application usage
- View website usage
- View reports
- Export reports

### Employee

Employee can:
- Login
- Check in
- Check out
- Allow GPS location
- View own attendance
- View own leave balance
- View own PC activity summary

Employees cannot view other employees' information.

---

## 4. EMPLOYEE MANAGEMENT

Required employee fields:

- Employee ID
- Full name
- Email
- Phone
- Department
- Designation
- Joining date
- Work start time
- Work end time
  (a second start/end pair where split shifts are enabled, D7)
- Leave balance
- Status

Employee status:
- Active
- Inactive

Example:

Employee ID: EMP-001
Name: Rahim Ahmed
Department: Development
Work Time: 09:00 AM - 06:00 PM
Leave Balance: 12 days
Status: Active

---

## 5. OFFICE CONFIGURATION

Admin can configure the primary office location.

Required settings:
- Office name
- Latitude
- Longitude
- Allowed radius

Example:

Office: Main Office
Latitude: 23.XXXX
Longitude: 90.XXXX
Allowed Radius: 200 meters

The system calculates the distance between the employee GPS location and the office location.

Attendance should indicate:
- Inside office radius
- Outside office radius

The initial MVP should allow the company to decide whether remote/outside-radius check-ins are permitted.

---

## 6. GPS ATTENDANCE

Employees use a responsive web page from their phone or browser.

No separate mobile application is required.

When the employee presses CHECK IN, the browser requests GPS permission.

The system records:
- Employee
- Date
- Time
- Latitude
- Longitude
- GPS accuracy
- Office distance
- Location status

Example:

Employee: Rahim Ahmed
Check-in: 09:08 AM
Latitude: 23.XXXX
Longitude: 90.XXXX
Accuracy: 15 meters
Office distance: 83 meters
Location: Inside Office

---

## 7. CHECK-OUT

Employee presses CHECK OUT.

The system records:
- Check-out time
- Latitude
- Longitude
- GPS accuracy
- Office distance

Example:

Check-in: 09:08 AM
Check-out: 06:04 PM
Total duration: 8h 56m

---

## 8. LATE ATTENDANCE

Each employee has a scheduled work start time.

Example:

Scheduled start: 09:00 AM
Actual check-in: 09:17 AM

Result:
Status: LATE
Late: 17 minutes

If check-in is at or before 09:00:
Status: ON TIME

The system calculates late minutes automatically.

---

## 9. ATTENDANCE STATUS

Supported statuses:
- Present
- Late
- Absent
- Leave

Basic logic:

If employee checks in:
Present or Late

If marked as leave:
Leave

If no check-in exists for a working day:
Absent

A day may hold more than one check-in/check-out pair where split shifts are enabled
(D7). The status rules above are unchanged: they are decided from the day as a whole,
not from any single punch.

Admin can manually correct an attendance record. Corrections are made against an
individual punch, and the day's totals and status are recalculated from it.

---

## 10. LEAVE BALANCE

The MVP requires only a simple leave balance.

Example:

Total Leave: 12
Used: 4
Remaining: 8

Admin can:
- Set initial balance
- Add leave balance
- Deduct leave balance
- Mark employee as on leave

No complex leave approval workflow is required.

Employee can only view their balance.

---

## 11. WINDOWS PC AGENT

A lightweight Windows desktop application/service must be created.

The agent is installed on each employee's PC.

After installation it should:
1. Register the computer.
2. Associate the computer with an employee.
3. Start automatically with Windows.
4. Detect PC status.
5. Detect active/idle status.
6. Detect active applications.
7. Detect browser activity.
8. Store activity locally if offline.
9. Synchronize with the backend.

The agent should run quietly in the background.

---

## 12. COMPUTER REGISTRATION

Each PC should be registered with the backend.

Computer information:
- Computer ID
- Computer name
- Employee
- Operating system
- Agent version
- Last heartbeat
- Status

Example:

Computer: DEV-PC-01
Employee: Rahim Ahmed
OS: Windows 11
Agent: 1.0.0
Status: Online

---

## 13. PC ONLINE/OFFLINE TRACKING

The desktop agent sends periodic heartbeats to the backend.

Recommended heartbeat interval:
30-60 seconds.

The system should detect:
- Windows startup
- Shutdown
- Sleep
- Wake

Example:

09:01 - PC started
09:01-18:05 - PC online
18:05 - PC shutdown

Daily:
PC On Time: 9h 04m

---

## 14. ACTIVE/IDLE TRACKING

The agent detects keyboard/mouse inactivity.

Default idle threshold:
5 minutes.

Example:

09:00-10:30 Active
10:30-10:45 Idle
10:45-12:30 Active
12:30-13:30 Idle
13:30-18:00 Active

Daily:
PC On: 9h 00m
Active: 7h 30m
Idle: 1h 30m

The idle threshold should be configurable.

---

## 15. APPLICATION TRACKING

The agent identifies the currently active application and calculates usage duration.

Example:

09:05-10:30
Visual Studio Code
1h 25m

10:30-10:45
Google Chrome
15m

10:45-12:00
Visual Studio Code
1h 15m

Daily summary:

Visual Studio Code: 4h 12m
Google Chrome: 2h 18m
Microsoft Word: 42m
Slack: 31m
Other: 17m

Required application information:
- Application name
- Executable name where available
- Start time
- End time
- Duration

---

## 16. WEBSITE TRACKING

The desktop agent tracks websites used through supported browsers.

Initial browser support:
- Google Chrome
- Microsoft Edge
- Firefox

The system should primarily store the domain.

Example:

github.com: 2h 12m
google.com: 35m
stackoverflow.com: 28m
youtube.com: 14m
facebook.com: 7m

Only the active browser tab should normally count toward website usage.

---

## 17. WEBSITE PRIVACY

The system should NOT collect:
- Passwords
- Form contents
- Credit card information
- Cookies
- Authentication tokens
- Private messages
- Full sensitive URLs containing personal information

Prefer storing:

example.com

instead of:

https://example.com/private/account?id=123&token=xxxxx

The goal is to know which website/domain was used and for how long.

---

## 18. ACTIVITY SESSION MODEL

Activity should be stored as sessions instead of creating a database record every second.

Example:

Application:
VS Code

Start: 09:15:00
End: 10:05:00
Duration: 50 minutes

Website:
github.com

Start: 10:05:00
End: 10:35:00
Duration: 30 minutes

This reduces database size and improves performance.

---

## 19. OFFLINE AGENT SUPPORT

If Internet access is unavailable:

PC
|
v
Local Activity Storage
|
Internet unavailable
|
Internet restored
|
v
Synchronize with Server

The agent must retain unsynchronized activity locally and upload it later.

The agent must avoid duplicate records during synchronization.

---

## 20. ADMIN DASHBOARD

Example:

Today's Attendance

Employees: 50
Present: 42
Late: 5
Absent: 2
Leave: 1

PC Status

Online: 39
Active: 34
Idle: 5
Offline: 11

---

## 21. EMPLOYEE LIST

Admin should see:

- Employee
- Department
- Attendance status
- Check-in
- Check-out
- PC status
- Active time
- Idle time

---

## 22. EMPLOYEE ACTIVITY PAGE

Admin selects an employee.

The page displays:
- Employee name
- Date selector
- Attendance summary
- PC summary
- Application usage
- Website usage
- Activity timeline

Example:

Rahim Ahmed
18 August 2026

Attendance:
09:02 - 18:03

PC On:
9h 01m

Active:
7h 22m

Idle:
1h 39m

Top Applications:
VS Code - 4h 12m
Chrome - 2h 01m
Slack - 32m

Top Websites:
github.com - 1h 42m
google.com - 31m
stackoverflow.com - 27m

---

## 23. ACTIVITY TIMELINE

Example:

09:02 - PC Started
09:05 - Chrome / github.com
09:42 - VS Code
10:30 - Idle
10:38 - VS Code
12:45 - Chrome / google.com
13:00 - Idle
14:00 - VS Code
18:03 - PC Shutdown

---

## 24. EMPLOYEE DASHBOARD

Today's Attendance:
Check-in: 09:02 AM
Check-out: 06:03 PM
Status: Present

Leave Balance:
8 days

Today's PC Activity:
PC On: 9h 01m
Active: 7h 22m
Idle: 1h 39m

Employees can only view their own information.

---

## 25. REPORTS

### Attendance Report

Filters:
- Employee
- Department
- Date
- Date range
- Status

Columns:
- Employee
- Date
- Check-in
- Check-out
- Late minutes
- Status
- Check-in location

### PC Activity Report

Filters:
- Employee
- Date
- Date range

Columns:
- Employee
- PC On Time
- Active Time
- Idle Time
- Top Application
- Top Website

---

## 26. EXPORT

MVP exports:
- CSV
- Excel

PDF is optional and can be added later.

---

## 27. DATABASE STRUCTURE

### Employee

- id
- employee_id
- name
- email
- phone
- department
- designation
- joining_date
- leave_balance          (leave_total and leave_used; remaining is derived)
- status
- authentication information

### EmployeeShift

The work window. One row for a normal employee, two where split shifts are enabled
(D7), which is why the times are not columns on Employee.

- id
- employee_id
- sequence
- start_time
- end_time

### Attendance

One row per employee per day. The GPS fields moved to AttendancePunch when split
shifts were added (D7): a day can hold more than one check-in/check-out pair, so a
single check_in column could not describe it. An employee who punches once a day
has exactly one punch, and the single-shift behaviour is unchanged.

- id
- employee_id
- date
- first_check_in_at
- last_check_out_at
- worked_seconds        (sum of the punches, so a lunch gap is not counted as work)
- late_minutes
- status
- leave_fraction        (0.5 steps when half-day leave is enabled, D6)
- needs_review          (set when a punch matched no scheduled shift)
- is_manually_adjusted, adjusted_by, adjustment_note

### AttendancePunch

One check-in/check-out pair. The location fields §6 and §7 require live here.

- id
- attendance_id
- sequence
- check_in_at
- check_in_latitude
- check_in_longitude
- check_in_accuracy
- check_in_distance
- check_in_location_status
- check_out_at
- check_out_latitude
- check_out_longitude
- check_out_accuracy
- check_out_distance
- check_out_location_status
- matched_shift, scheduled_start, late_minutes

### Computer

- id
- employee_id
- computer_name
- operating_system
- agent_version
- device_token
- last_seen
- status

### Activity

- id
- employee_id
- computer_id
- activity_type
- application_name
- executable_name
- website_domain
- start_time
- end_time
- duration

Activity types:
- PC_ON
- PC_OFF
- ACTIVE
- IDLE
- APPLICATION
- WEBSITE

---

## 28. API REQUIREMENTS

Minimum agent APIs:

POST /api/agent/register/
POST /api/agent/heartbeat/
POST /api/agent/activity/
POST /api/agent/sync/
GET /api/agent/config/

Attendance APIs:

POST /api/attendance/check-in/
POST /api/attendance/check-out/
GET /api/attendance/my/

Admin APIs:

GET /api/employees/
POST /api/employees/
GET /api/employees/{id}/
GET /api/attendance/
GET /api/activity/
GET /api/reports/

Exact URL structure may be adjusted during implementation.

---

## 29. AUTHENTICATION

Admin and employee web access should use normal authentication.

Desktop agents should use a unique device token.

Each device must be associated with one employee.

The server must reject activity submissions from invalid or disabled devices.

All communication must use HTTPS.

---

## 30. SECURITY

Required:
- HTTPS
- Secure authentication
- Device authentication
- Password hashing
- Role-based access
- Employee data isolation
- Input validation
- API rate limiting where appropriate
- Audit logging for important admin actions

If multi-company support is enabled, organization-level data isolation is required.

---

## 31. PRIVACY

The MVP must NOT implement:
- Keylogging
- Screen recording
- Webcam
- Microphone
- Clipboard monitoring
- Password collection
- Private chat monitoring
- Email content collection
- File content monitoring

Screenshots are permitted as of 2026-11-22, by deliberate decision of the
project owner — this reverses the prior blanket prohibition on screenshot
capture specifically, and only that item. Every other prohibition above is
unchanged. Screenshot capture must be admin/HR-viewable only, subject to a
redaction/review gate before first view, and subject to its own retention
policy distinct from other PC-activity data (see
docs/designs/screenshot-based-activity-tracking.md). Before this capability
is enabled against any real, non-test employee, the organization must
reissue the employee privacy notice describing it explicitly and obtain a
positive re-acknowledgment from each affected employee, and should confirm
the applicable jurisdiction's legal requirements for screen-content capture
of employees.

The organization should inform employees that GPS attendance and PC activity tracking are enabled and define an appropriate data-retention policy.

---

## 32. TECHNOLOGY STACK

Recommended:

Backend:
- Django
- Django REST Framework
- PostgreSQL

Frontend:
- Vue.js

Desktop Agent:
- Python
- psutil
- pywin32
- Windows APIs

Optional:
- Redis
- Celery

Use a single backend application for the MVP. Avoid unnecessary microservices.

---

## 33. PROJECT STRUCTURE

backend/
    manage.py
    config/
    accounts/
    employees/
    attendance/
    computers/
    activities/
    reports/
    api/
    requirements.txt

desktop-agent/
    agent/
    services/
    collectors/
    sync/
    storage/
    config/
    installer/

frontend/
    src/
    components/
    views/
    services/

---

## 34. DESKTOP AGENT COMPONENTS

### Agent Service
Starts and stops the agent.

### Activity Collector
Detects active/idle state.

### Application Collector
Detects active application.

### Browser Collector
Detects active website/domain.

### System Collector
Detects startup, shutdown, sleep, wake, lock/unlock where practical.

### Local Storage
Temporarily stores activity while offline.

### Sync Service
Sends activity to the backend.

### Configuration
Stores:
- Server URL
- Device token
- Idle threshold
- Sync interval

---

## 35. ADMIN SETTINGS

### Office
- Office latitude
- Office longitude
- Allowed radius

### Work Schedule
- Default start time
- Default end time

### Activity
- Idle threshold
- Agent heartbeat interval
- Activity sync interval

Recommended defaults:

Idle threshold: 5 minutes
Heartbeat: 60 seconds
Activity synchronization: 60 seconds

---

## 36. MVP USER FLOW

### Admin

1. Login
2. Add employees
3. Configure office location
4. Configure working hours
5. Set employee leave balance
6. Register/assign employee computers
7. View dashboard
8. View attendance
9. View PC activity
10. Generate reports

### Employee

1. Login
2. Open attendance page
3. Allow GPS
4. Check in
5. Work normally
6. Check out
7. View attendance
8. View leave balance
9. View PC activity summary

### Desktop Agent

1. Start with Windows
2. Authenticate device
3. Send heartbeat
4. Monitor active/idle state
5. Detect active application
6. Detect active website
7. Create activity sessions
8. Store offline activity
9. Synchronize activity
10. Continue running in background

---

## 37. MVP SUCCESS CRITERIA

### Attendance

[ ] Admin can create employees.
[ ] Employee can login.
[ ] Employee can check in using GPS.
[ ] GPS coordinates are stored.
[ ] Office distance is calculated.
[ ] Employee can check out using GPS.
[ ] Late attendance is automatically calculated.
[ ] Attendance history is available.
[ ] Leave balance is available.
[ ] Admin can correct attendance.

### PC Tracking

[ ] Windows agent can be installed.
[ ] Agent automatically starts with Windows.
[ ] Computer is registered with employee.
[ ] PC online status is available.
[ ] PC offline status is detected.
[ ] Active time is calculated.
[ ] Idle time is calculated.
[ ] Application usage is tracked.
[ ] Application duration is calculated.
[ ] Website/domain usage is tracked.
[ ] Website duration is calculated.
[ ] Activity is stored when offline.
[ ] Offline activity synchronizes when Internet returns.

### Dashboard

[ ] Admin dashboard shows attendance.
[ ] Admin dashboard shows PC status.
[ ] Admin can view employee activity.
[ ] Admin can view application usage.
[ ] Admin can view website usage.
[ ] Admin can view activity timeline.
[ ] Employee can view own attendance.
[ ] Employee can view own leave balance.
[ ] Employee can view own PC activity summary.

### Reports

[ ] Attendance can be filtered by date.
[ ] PC activity can be filtered by date.
[ ] Attendance can be exported.
[ ] Activity can be exported.

---

## 38. NON-GOALS

Do not add the following to the MVP:

- Task management
- Project management
- Payroll
- Recruitment
- Performance reviews
- Chat
- Messaging
- Screenshot system
- Video recording
- Keylogger
- AI productivity scoring
- Complex HR workflows
- Complex mobile application
- Facial recognition
- Biometric attendance
- Slack/Teams integrations
- Email integrations
- Billing/subscriptions

These can be considered after the core MVP is stable.

---

## 39. FINAL MVP DEFINITION

The finished application should be a small employee attendance and computer activity tracker.

It should answer:

1. Did the employee check in?
2. When did they check in/out?
3. Where did they check in from?
4. Were they late?
5. How much leave do they have?
6. Was their PC on or off?
7. How long was the PC actively being used?
8. How long was it idle?
9. Which software was used?
10. How long was each software used?
11. Which websites were visited?
12. How long was each website used?

Everything else is outside the MVP scope.

Priority:

RELIABILITY > SIMPLICITY > FEATURES
