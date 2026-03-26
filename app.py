import re
from flask import Flask, flash, render_template, request, redirect, session, jsonify
import random, smtplib, ssl, sqlite3, os, uuid, threading, time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai 
from google.genai import types
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# ---------------------- NEW GEMINI SDK CLIENT ----------------------
client = genai.Client(api_key="AIzaSyCzs0B_V2Xv1IcZOT03Fdw3SWjvslAnb28")

# ---------------------- CONFIGURATION ----------------------
UPLOAD_FOLDER = 'static/recordings'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------------- DATABASE ----------------------
def get_db():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    return conn

def create_table():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT,
            address TEXT,
            country TEXT,
            state TEXT,
            dob TEXT,
            age INTEGER,
            blood_group TEXT,
            organ_donor TEXT,
            height TEXT,
            weight TEXT,
            primary_emergency_phone TEXT,
            physician_phone TEXT,
            allergies TEXT,
            current_meds TEXT,
            medical_history TEXT,
            physical_limitations TEXT,
            otp_attempts INTEGER DEFAULT 0,
blocked_until DATETIME
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT,
            file_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            name TEXT,
            phone TEXT,
            relation TEXT,
            contact_email TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            expiry_time DATETIME,
            lat REAL,
            lon REAL,
            start_lat REAL,
            start_lon REAL,
            status TEXT DEFAULT 'ACTIVE'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            trigger_phrase TEXT DEFAULT 'HELP HELP'
        )
    """)

    cur.execute("""
CREATE TABLE IF NOT EXISTS live_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    lat REAL,
    lon REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
    con.commit()
    con.close()

create_table()

# ---------------------- DATA INTEGRITY CHECK ----------------------
def initialize_voice_triggers():
    """Ensures all existing users have a default voice trigger entry."""
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT email FROM users 
        WHERE email NOT IN (SELECT user_email FROM voice_triggers)
    """)
    missing_users = cur.fetchall()
    
    for user in missing_users:
        cur.execute("INSERT INTO voice_triggers (user_email) VALUES (?)", (user['email'],))
    
    con.commit()
    con.close()

initialize_voice_triggers()

def get_emergency_contacts(email):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT name, phone, contact_email FROM emergency_contacts WHERE user_email=?", (email,))
    contacts = cur.fetchall()
    con.close()
    return contacts

# ---------------------- NEIGHBORHOOD UTILITY ----------------------
def notify_nearby_users(lat, lon, current_user_email):
    con = get_db()
    cur = con.cursor()
    cur.execute("""
    SELECT user_email FROM active_watches 
    WHERE status='ACTIVE' 
    AND user_email != ? 
    AND (ABS(CAST(lat AS REAL) - ?) < 0.005 AND ABS(CAST(lon AS REAL) - ?) < 0.005)
""", (current_user_email, lat, lon))
    nearby = cur.fetchall()
    for person in nearby:
        send_email_otp(person['user_email'], "URGENT: Someone near you is in danger. Check your map.")
    con.close()

# ---------------------- WHATSAPP LINK GENERATOR ----------------------
def get_whatsapp_link(phone, message):
    clean_phone = ''.join(filter(str.isdigit, phone))
    return f"https://wa.me/{clean_phone}?text={message.replace(' ', '%20')}"

# ---------------------- SEND EMAIL (OTP & ALERTS) ----------------------
def send_email_otp(receiver_email, content):
    sender_email = "crystalcharm1230@gmail.com"
    app_password = "apxx xvza fybo bewm"

    msg = MIMEText(content)
    msg["Subject"] = "Safety Assistant Notification"
    msg["From"] = sender_email
    msg["To"] = receiver_email

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        print("Email sent to:", receiver_email)

    except Exception as e:
        print("SMTP Error:", e)

# ---------------------- AUTH ROUTES ----------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        f_name = request.form.get('first_name')
        l_name = request.form.get('last_name')
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        address = request.form.get('address')
        country = request.form.get('country')
        state = request.form.get('state')
        dob = request.form.get('dob')
        age = request.form.get('age')
        blood_group = request.form.get('blood_group')
        organ_donor = request.form.get('organ_donor')
        height = request.form.get('height')
        weight = request.form.get('weight')
        primary_emergency_phone = request.form.get('primary_emergency_phone')
        physician_phone = request.form.get('physician_phone')
        allergies = request.form.get('allergies')
        current_meds = request.form.get('current_meds')
        medical_history = request.form.get('medical_history')
        physical_limitations = request.form.get('physical_limitations')
        try:
            con = get_db()
            cur = con.cursor()
            cur.execute("""
                INSERT INTO users (
                    first_name, last_name, username, email, password, address, country, state,
                    dob, age, blood_group, organ_donor, height, weight, 
                    primary_emergency_phone, physician_phone, allergies, 
                    current_meds, medical_history, physical_limitations
                ) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                f_name, l_name, username, email, password, address, country, state,
                dob, age, blood_group, organ_donor, height, weight,
                primary_emergency_phone, physician_phone, allergies,
                current_meds, medical_history, physical_limitations
            ))
            cur.execute("INSERT INTO voice_triggers (user_email) VALUES (?)", (email,))
            con.commit()
            con.close()
            otp = random.randint(100000, 999999)
            session['otp'] = str(otp)
            session['otp_time'] = time.time() 
            session['temp_email'] = email
            send_email_otp(email, f"Your verification code is: {otp}")
            return redirect('/otp_verify')
        except sqlite3.IntegrityError:
            return "User already exists"
    return render_template("signup.html")

@app.route('/login')
def login():
    return render_template("login.html")

@app.route('/login_password', methods=['POST'])
def login_password():
    data = request.get_json()
    identifier = data['email']
    password = data['password']
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE email=? OR username=?", (identifier, identifier))
    user = cur.fetchone()
    con.close()
    if user and check_password_hash(user['password'], password):
        session['email'] = user['email']
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.route('/login_otp', methods=['POST'])
def login_otp():
    try:
        data = request.get_json(silent=True)
        email = data.get('email') if data else session.get('temp_email')

        if not email:
            return jsonify({"status": "error", "message": "No email provided"})

        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT blocked_until FROM users WHERE email=?", (email,))
        user = cur.fetchone()

        if not user:
            con.close()
            return jsonify({"status": "error", "message": "User not found"})

        # ✅ FIXED BLOCK CHECK
        if user["blocked_until"]:
            try:
                if datetime.now() < datetime.fromisoformat(user["blocked_until"]):
                    con.close()
                    return jsonify({"status": "error", "message": "Account temporarily blocked"})
            except (ValueError, TypeError):
                pass 

        otp = str(random.randint(100000, 999999))
        session['otp'] = otp
        session['otp_time'] = time.time()
        session['temp_email'] = email

        send_email_otp(email, f"Your Safety App OTP is: {otp}")
        con.close()
        return jsonify({"status": "success"})

    except Exception as e:
        print("ERROR in /login_otp:", e)   # 🔥 VERY IMPORTANT
        return jsonify({"status": "error", "message": "Server error"})

@app.route('/otp_verify')
def otp_verify():
    return render_template("otp_verify.html")

@app.route('/validate_otp', methods=['POST'])
def validate_otp():
    user_otp = request.form.get('otp')
    stored_otp = session.get('otp')
    temp_email = session.get('temp_email')

    if not stored_otp or not temp_email:
        return render_template("otp_verify.html", error="Session expired. Please request a new OTP.")

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT otp_attempts, blocked_until FROM users WHERE email=?", (temp_email,))
    user = cur.fetchone()

    # Safety check if user exists in DB
    if not user:
        con.close()
        return render_template("otp_verify.html", error="User record not found.")
    
    if time.time() - session.get('otp_time', 0) > 300:
        return render_template("otp_verify.html", error="OTP expired. Please request a new one.")

    # ✅ FIXED COMPARISON AND ATTEMPTS
    if str(user_otp) == str(stored_otp):
        cur.execute("UPDATE users SET otp_attempts=0, blocked_until=NULL WHERE email=?", (temp_email,))
        con.commit()
        con.close()
        session['email'] = temp_email
        return redirect('/home')
    else:
        attempts = (user["otp_attempts"] or 0) + 1
        if attempts >= 3:
            # Block for 1 hour (you can change days=2 to minutes=60 for testing)
            block_time = (datetime.now() + timedelta(days=2)).isoformat()
            cur.execute("UPDATE users SET otp_attempts=?, blocked_until=? WHERE email=?", (attempts, block_time, temp_email))
            error_msg = "Too many attempts. Account blocked for 2 days."
        else:
            cur.execute("UPDATE users SET otp_attempts=? WHERE email=?", (attempts, temp_email))
            error_msg = f"Invalid OTP. {3 - attempts} attempts left."
        
        con.commit()
        con.close()
        return render_template("otp_verify.html", error=error_msg)
    
    # ---------------------- FORGOT PASSWORD ----------------------

@app.route('/forgot_password')
def forgot_password():
    return render_template("forgot_password.html")


@app.route('/send_reset_otp', methods=['POST'])
def send_reset_otp():
    data = request.get_json()
    email = data.get('email')

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cur.fetchone()

    if not user:
        con.close()
        return jsonify({"status": "error", "message": "Email not registered"})

    otp = str(random.randint(100000, 999999))

    session['reset_otp'] = otp
    session['reset_email'] = email

    send_email_otp(email, f"Your password reset OTP is: {otp}")

    con.close()
    return jsonify({"status": "success"})


@app.route('/verify_reset_otp')
def verify_reset_otp():
    return render_template("verify_reset_otp.html")


@app.route('/validate_reset_otp', methods=['POST'])
def validate_reset_otp():
    user_otp = request.form.get('otp')

    if user_otp == session.get('reset_otp'):
        return redirect('/reset_password')

    return render_template("verify_reset_otp.html", error="Invalid OTP")


@app.route('/reset_password')
def reset_password():
    return render_template("reset_password.html")


@app.route('/update_password', methods=['POST'])
def update_password():
    new_password = request.form.get('password')
    email = session.get('reset_email')

    hashed_password = generate_password_hash(new_password)

    con = get_db()
    cur = con.cursor()
    cur.execute("UPDATE users SET password=? WHERE email=?", (hashed_password, email))
    con.commit()
    con.close()

    session.pop('reset_email', None)
    session.pop('reset_otp', None)

    return redirect('/login')
# ---------------------- PROFILE & MEDICAL HISTORY ----------------------

@app.route('/profile')
def profile():
    if "email" not in session: return redirect('/login')
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (session['email'],))
    user = cur.fetchone()
    cur.execute("SELECT trigger_phrase FROM voice_triggers WHERE user_email=?", (session['email'],))
    trigger_row = cur.fetchone()
    con.close()
    return render_template("profile.html", user=user, trigger=trigger_row)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if "email" not in session: return redirect('/login')
    blood_group = request.form.get('blood_group')
    organ_donor = request.form.get('organ_donor')
    allergies = request.form.get('allergies')
    medical_history = request.form.get('medical_history')
    current_meds = request.form.get('current_meds')
    emergency_phone = request.form.get('primary_emergency_phone')
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        UPDATE users SET 
            blood_group=?, organ_donor=?, allergies=?, 
            medical_history=?, current_meds=?, primary_emergency_phone=?
        WHERE email=?
    """, (blood_group, organ_donor, allergies, medical_history, current_meds, emergency_phone, session['email']))
    con.commit()
    con.close()
    return redirect('/home')

# ---------------------- SILENT ALARM ROUTE ----------------------
@app.route('/trigger_silent_alarm', methods=['POST'])
def silent_alarm():
    if "email" not in session: 
        return jsonify({"status": "error"}), 401
    data = request.get_json()
    lat = data.get('lat')
    lon = data.get('lon')
    user_email = session['email']
    contacts = get_emergency_contacts(user_email)
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    alert_message = f"SILENT EMERGENCY ALERT: I am in danger but cannot speak. My current location: {map_url}"
    for contact in contacts:
        if contact['contact_email']:
            send_email_otp(contact['contact_email'], alert_message)
    notify_nearby_users(lat, lon, user_email)
    return jsonify({"status": "success", "message": "Silent alert sent to contacts."})

# ---------------------- BATTERY & VOICE ROUTES ----------------------

@app.route('/trigger_battery_alert', methods=['POST'])
def battery_alert():
    if "email" not in session: return jsonify({"status": "error"}), 401
    data = request.get_json()
    level = data.get('level')
    lat = data.get('lat', 'Unknown')
    lon = data.get('lon', 'Unknown')
    user_email = session['email']
    contacts = get_emergency_contacts(user_email)
    map_url = f"https://www.google.com/maps?q={lat},{lon}"
    msg = f"CRITICAL BATTERY ALERT: User {user_email} phone is at {level}%. It may shut down soon. Last location: {map_url}"
    for contact in contacts:
        if contact['contact_email']:
            send_email_otp(contact['contact_email'], msg)
    return jsonify({"status": "contacts_notified"})

@app.route('/process_voice_command', methods=['POST'])
def process_voice():
    if "email" not in session: return jsonify({"status": "error"}), 401
    data = request.get_json()
    heard_text = data.get('text', '').upper()
    user_email = session['email']
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT trigger_phrase FROM voice_triggers WHERE user_email=?", (user_email,))
    phrase_row = cur.fetchone()
    con.close()
    trigger = phrase_row['trigger_phrase'].upper() if phrase_row else "HELP HELP"
    if trigger in heard_text:
        return jsonify({"status": "trigger_sos", "message": "Emergency phrase detected!"})
    return jsonify({"status": "no_match"})

@app.route('/update_voice_phrase', methods=['POST'])
def update_voice_phrase():
    if "email" not in session: return redirect('/login')
    new_phrase = request.form.get('trigger_phrase').upper()
    user_email = session['email']
    con = get_db()
    cur = con.cursor()
    cur.execute("UPDATE voice_triggers SET trigger_phrase=? WHERE user_email=?", (new_phrase, user_email))
    con.commit()
    con.close()
    return redirect('/profile')

# ---------------------- PAGES ----------------------
@app.route('/')
def splash():
    return render_template("splash.html")

@app.route('/welcome')
def welcome():
    return render_template("welcome.html")

@app.route('/response')
def response_page():
    return render_template("response.html")

@app.route('/reli')
def reli_page():
    return render_template("reli.html")

@app.route('/start')
def start_page():
    return render_template("start.html")

@app.route('/admin')
def admin():
    return render_template("admin.html")

@app.route('/admin-login', methods=['POST'])
def admin_login():
    username = request.form.get('username')
    password = request.form.get('password')

    # 🔐 simple admin credentials
    if username == "admin" and password == "admin123":
        session['admin'] = True
        return redirect('/admin-dashboard')
    else:
        flash("Invalid admin credentials")
        return redirect('/admin')

@app.route('/admin-dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin')
    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    cur.execute("SELECT * FROM emergency_contacts")
    contacts = cur.fetchall()

    cur.execute("SELECT * FROM recordings")
    recordings = cur.fetchall()

    cur.execute("SELECT * FROM live_locations ORDER BY id DESC LIMIT 50")
    locations = cur.fetchall()

    cur.execute("SELECT * FROM voice_triggers")
    triggers = cur.fetchall()

    cur.execute("SELECT * FROM active_watches")
    watches = cur.fetchall()

    con.close()

    return render_template("admin-dashboard.html",
                           users=users,
                           contacts=contacts,
                           recordings=recordings,
                           locations=locations,
                           triggers=triggers,
                           watches=watches)

@app.route('/admin-logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')

@app.route('/home')
@login_required
def home():
    if "email" not in session: return redirect('/login')
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (session['email'],))
    user = cur.fetchone()
    con.close()
    return render_template("home.html", user=user)

@app.route('/record')
def record():
    if "email" not in session: return redirect('/login')
    return render_template("record.html")

@app.route('/my_recordings')
def my_recordings():
    if "email" not in session: return redirect('/login')
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM recordings WHERE email=? ORDER BY timestamp DESC", (session['email'],))
    user_recs = cur.fetchall()
    con.close()
    return render_template("record_history.html", recordings=user_recs)

#---------------------- MAP & TRACKING ----------------------
@app.route('/map')
def map_page():
    if "email" not in session:
        return redirect('/login')
    return render_template("map.html")

@app.route('/send_live_location', methods=['POST'])
def send_live_location():

    if "email" not in session:
        return jsonify({"status": "error"}), 401

    data = request.get_json()

    lat = float(data.get("lat"))
    lon = float(data.get("lon"))

    user_email = session['email']

    # Google Maps link
    map_link = f"https://www.google.com/maps?q={lat},{lon}"

    # Live tracking page of your app
    tracking_link = f"{request.host_url}track"

    message = f"""
🚨 EMERGENCY ALERT

User may be in danger.

📍 Live Location:
{map_link}

📡 Track Live Location:
{tracking_link}

Please contact the user immediately.
"""

    contacts = get_emergency_contacts(user_email)

    # Send to ALL emergency contacts
    for contact in contacts:
        if contact["contact_email"]:
            send_email_otp(contact["contact_email"], message)
            time.sleep(1)

    return jsonify({"status": "sent"})


@app.route('/update_live_location', methods=['POST'])
def update_live_location():

    if "email" not in session:
        return jsonify({"status": "error"}), 401

    data = request.get_json()

    try:
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
    except:
        return jsonify({"status": "error", "message": "Invalid location"})

    con = get_db()
    cur = con.cursor()

    cur.execute(
        "INSERT INTO live_locations (user_email, lat, lon) VALUES (?, ?, ?)",
        (session['email'], lat, lon)
    )

    con.commit()
    con.close()

    return jsonify({"status": "updated"})

@app.route('/get_live_location/<email>')
def get_live_location(email):

    con = get_db()
    cur = con.cursor()

    cur.execute(
        "SELECT lat, lon FROM live_locations WHERE user_email=? ORDER BY id DESC LIMIT 1",
        (email,)
    )

    location = cur.fetchone()

    con.close()

    if location:
        return jsonify({
            "lat": float(location["lat"]),
            "lon": float(location["lon"])
        })

    return jsonify({
        "lat": None,
        "lon": None
    })

@app.route('/track')
def track():
    if "email" not in session:
        return redirect('/login')
    return render_template("track.html", email=session['email'])
# ---------------------- CONTACTS ----------------------
@app.route('/contacts')
def contacts():
    if "email" not in session: return redirect('/login')
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM emergency_contacts WHERE user_email=?", (session['email'],))
    user_contacts = cur.fetchall()
    con.close()
    return render_template("contacts.html", user_contacts=user_contacts)

@app.route('/add_contact', methods=['POST'])
def add_contact():
    if "email" not in session: return redirect('/login')
    name = request.form['name']
    phone = request.form['phone']
    relation = request.form['relation']
    c_email = request.form.get('contact_email', '') 
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM emergency_contacts WHERE user_email=?", (session['email'],))
    if cur.fetchone()[0] >= 5:
        con.close()
        return "Limit reached (Max 5 contacts)"
    cur.execute("INSERT INTO emergency_contacts (user_email, name, phone, relation, contact_email) VALUES (?,?,?,?,?)", 
                (session['email'], name, phone, relation, c_email))
    con.commit()
    con.close()
    return redirect('/contacts')

@app.route('/delete_contact/<int:contact_id>', methods=['POST'])
def delete_contact(contact_id):
    if "email" not in session: return redirect('/login')
    
    con = get_db()
    cur = con.cursor()
    # Ensure the user can only delete their own contacts
    cur.execute("DELETE FROM emergency_contacts WHERE id=? AND user_email=?", (contact_id, session['email']))
    con.commit()
    con.close()
    return redirect('/contacts')

# ---------------------- WATCHDOG LOGIC ----------------------
@app.route('/start_watchdog', methods=['POST'])
def start_watchdog():
    if "email" not in session: return jsonify({"status": "error"}), 401
    data = request.get_json()
    minutes = int(data.get('minutes', 10))
    start_lat = float(data.get('lat'))
    start_lon = float(data.get('lon'))
    
    expiry = datetime.now() + timedelta(minutes=minutes)
    con = get_db()
    cur = con.cursor()
    cur.execute("INSERT INTO active_watches (user_email, expiry_time, lat, lon, start_lat, start_lon) VALUES (?, ?, ?, ?, ?, ?)",
                (session['email'], expiry, start_lat, start_lon, start_lat, start_lon))
    con.commit()
    con.close()
    return jsonify({"status": "watchdog_started", "expiry": expiry.strftime("%H:%M:%S")})

@app.route('/stop_watchdog', methods=['POST'])
def stop_watchdog():
    if "email" not in session: return jsonify({"status": "error"}), 401
    con = get_db()
    cur = con.cursor()
    cur.execute("UPDATE active_watches SET status='SAFE' WHERE user_email=? AND status='ACTIVE'", (session['email'],))
    con.commit()
    con.close()
    return jsonify({"status": "safe"})

def monitor_watches():
    while True:
        time.sleep(30)
        try:
            conn = sqlite3.connect("users.db")
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            now = datetime.now()
            cur.execute("SELECT * FROM active_watches WHERE status='ACTIVE' AND expiry_time < ?", (now,))
            expired_watches = cur.fetchall()
            for watch in expired_watches:
                user_email = watch['user_email']
                cur.execute("SELECT name, phone, contact_email FROM emergency_contacts WHERE user_email=?", (user_email,))
                contacts = cur.fetchall()
                map_link = f"https://www.google.com/maps?q={watch['lat']},{watch['lon']}"
                alert_body = f"CRITICAL WATCHDOG ALERT: User {user_email} failed to check in! Last known location: {map_link}"
                for contact in contacts:
                    if contact['contact_email']:
                        send_email_otp(contact['contact_email'], alert_body)
                send_email_otp("crystalcharm1230@gmail.com", f"WATCHDOG EXPIRED: {alert_body}")
                cur.execute("UPDATE active_watches SET status='ALERTED' WHERE id=?", (watch['id'],))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Watchdog Error: {e}")

# ---------------------- EMERGENCY EVIDENCE VIEWER ----------------------

@app.route('/view_evidence/<filename>')
def view_evidence(filename):
    return render_template("view_evidence.html", filename=filename)

# ---------------------- RECORDING & EMERGENCY ALERTS (UPDATED) ----------------------

@app.route('/save_recording', methods=['POST'])
def save_recording():
    if "email" not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    file = request.files['video_data']
    lat = request.form.get('lat')
    lon = request.form.get('lon')

    unique_filename = f"{uuid.uuid4()}.webm"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))

    user_email = session['email']

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT username FROM users WHERE email=?", (user_email,))
    user_row = cur.fetchone()

    # Safe username fetch
    username = user_row['username'] if user_row else "Unknown"

    cur.execute(
        "INSERT INTO recordings (username, email, file_name) VALUES (?, ?, ?)",
        (username, user_email, unique_filename)
    )

    contacts = get_emergency_contacts(user_email)

    video_url = f"{request.host_url}view_evidence/{unique_filename}?lat={lat}&lon={lon}"
    map_url = f"https://www.google.com/maps?q={lat},{lon}"

    alert_message = f"EMERGENCY: I am in danger! \nView Video: {video_url} \nMy Location: {map_url}"

    for contact in contacts:
        if contact['contact_email']:
            send_email_otp(contact['contact_email'], alert_message)

    notify_nearby_users(lat, lon, user_email)

    wa_link = ""
    if contacts:
        wa_link = get_whatsapp_link(contacts[0]['phone'], alert_message)

    con.commit()
    con.close()

    return jsonify({"status": "success", "whatsapp_link": wa_link})

@app.route('/aichats', methods=['GET', 'POST'])
def aichats_page():
    if "email" not in session:
        return redirect('/login')

    if request.method == 'POST':
        data = request.get_json()
        user_msg = data.get("message", "").strip().lower()

        # --- ADVANCED LOGIC ENGINE ---

        # 1. IMMEDIATE DANGER / SOS
        if any(word in user_msg for word in ["help", "emergency", "sos", "danger", "attacked", "scared"]):
            reply = (
                "⚠️ EMERGENCY DETECTED. Tap the RED SOS button now. "
                "I'm ready to share your live location with trusted contacts."
            )
            action = "trigger_sos"

        # 2. FOLLOWED / SUSPICIOUS PERSON
        elif any(word in user_msg for word in ["follow", "following", "someone behind me", "stalker"]):
            reply = (
                "Stay calm. Try to move to a crowded or well-lit area. "
                "Would you like me to start live tracking and alert your contacts?"
            )
            action = "none"

        # 3. TRAVEL SAFETY
        elif any(word in user_msg for word in ["cab", "taxi", "uber", "auto", "ride"]):
            reply = (
                "Before your ride, share your trip details with a trusted contact. "
                "Avoid isolated routes. I can enable live tracking for your journey."
            )
            action = "none"

        # 4. FAKE CALL ESCAPE
        elif any(word in user_msg for word in ["call", "fake", "excuse", "leave", "pretend"]):
            reply = (
                "I can trigger a fake call to help you exit safely. "
                "Stay natural and act like it's important."
            )
            action = "none"

        # 5. FEELING ANXIOUS / PANIC
        elif any(word in user_msg for word in ["panic", "anxious", "afraid", "nervous"]):
            reply = (
                "You're not alone. Take a deep breath. "
                "If you feel unsafe, I can alert your contacts or start tracking."
            )
            action = "none"

        # 6. NIGHT WALK / SAFETY
        elif any(word in user_msg for word in ["night", "dark", "alone", "walking"]):
            reply = (
                "Please stay in well-lit areas and avoid isolated paths. "
                "Would you like to start live tracking for safety?"
            )
            action = "none"

        # 7. DOMESTIC SAFETY
        elif any(word in user_msg for word in ["home", "family", "unsafe at home"]):
            reply = (
                "If you feel unsafe at home, try to reach a safe space or contact help. "
                "I can trigger SOS if needed."
            )
            action = "trigger_sos"

        # 8. BATTERY
        elif any(word in user_msg for word in ["battery", "low battery"]):
            reply = (
                "Keep power-saving mode on and inform someone about your location."
            )
            action = "info_only"

        # 9. LEGAL
        elif any(word in user_msg for word in ["law", "rights", "police"]):
            reply = (
                "You can file an FIR at any police station. Women can request female officers."
            )
            action = "info_only"

        # DEFAULT
        else:
            reply = (
                "I'm here to help you stay safe. You can ask about emergencies, tracking, or fake calls."
            )
            action = "none"

        return jsonify({
            "reply": reply,
            "action": action
        })

    return render_template("aichats.html")
# ---------------------- FAKE CALL ROUTE ----------------------
@app.route('/fake_call')
def fake_call():
    if "email" not in session: 
        return redirect('/login')
    return render_template("fake_call.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == "__main__":
    threading.Thread(target=monitor_watches, daemon=True).start()
    app.run()