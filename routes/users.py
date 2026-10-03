import os
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import jwt
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import (ALGORITHM, SECRET_KEY, check_owner_or_admin, create_access_token,
                  get_current_user, hash_password, needs_rehash, verify_password)
from database import get_db

router = APIRouter(prefix="/users", tags=["Users"])

# ── input validation ─────────────────────────────────────────
def is_valid_email(email: str) -> bool:
    """Check if email matches a valid format like user@domain.com"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def is_valid_username(username: str) -> bool:
    # usernames show up all over the site, so keep them to plain characters
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username))

# ── send reset email via SMTP ────────────────────────────────
def send_reset_email(to_email: str, username: str, reset_token: str):
    """Send a password reset email with a branded HTML template."""
    # Re-load or fetch fresh from environment to ensure we don't use stale module-level vars
    smtp_email = os.getenv("SMTP_EMAIL", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    app_url = os.getenv("APP_URL", "http://127.0.0.1:8000")
    
    if not smtp_email or not smtp_password:
        print("[SMTP ERROR] SMTP_EMAIL or SMTP_PASSWORD not set in environment.")
        return False

    reset_link = f"{app_url}/reset-password.html?token={reset_token}"
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🔐 Yellow Umbrella — Password Reset"
    msg["From"] = smtp_email
    msg["To"] = to_email

    # Plain text fallback
    text_body = f"Hi {username},\n\nYou requested a password reset.\n\nClick this link to reset your password:\n{reset_link}\n\nThis link expires in 15 minutes.\n\nIf you didn't request this, ignore this email.\n\n— Yellow Umbrella Team"

    # Branded HTML email
    html_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 520px; margin: 0 auto; background: #0B0C10; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); overflow: hidden;">
        <div style="background: linear-gradient(135deg, #d97706 0%, #fbbf24 100%); padding: 30px; text-align: center;">
            <h1 style="margin: 0; font-size: 28px; font-weight: 800; color: #0B0C10; letter-spacing: 1px;">Yellow<span style="color: #fff;">Umbrella</span></h1>
        </div>
        <div style="padding: 35px 30px;">
            <h2 style="color: #fbbf24; margin: 0 0 15px 0; font-size: 22px;">Password Reset Request</h2>
            <p style="color: #c5c6c7; font-size: 15px; line-height: 1.6; margin: 0 0 25px 0;">
                Hi <strong style="color: #fff;">{username}</strong>,<br><br>
                We received a request to reset your password. Click the button below to set a new one.
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" style="display: inline-block; background: #fbbf24; color: #0B0C10; padding: 14px 40px; border-radius: 10px; font-weight: 700; font-size: 16px; text-decoration: none; letter-spacing: 0.5px;">Reset My Password</a>
            </div>
            <p style="color: #888; font-size: 13px; line-height: 1.5; margin: 25px 0 0 0; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 20px;">
                ⏳ This link expires in <strong style="color: #c5c6c7;">15 minutes</strong>.<br>
                If you didn't request this reset, you can safely ignore this email.
            </p>
        </div>
    </div>
    """

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        # Re-verify SMTP server choice, port 465 for SSL is standard for Gmail
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[SMTP ERROR] Failed to send email to {to_email}: {e}")
        return False

# ── Models ────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

# ── Registration (with email validation) ──────────────────────

@router.post("/register")
def register(user: UserRegister):
    user.username = user.username.strip()
    if not is_valid_username(user.username):
        return {"error": "Username must be 3-30 characters: letters, numbers, _ . or -"}
    if not is_valid_email(user.email):
        return {"error": "Please enter a valid email address (e.g. name@example.com)"}
    
    if len(user.password) < 4:
        return {"error": "Password must be at least 4 characters"}
    conn = get_db()
    try:
        existing = conn.run(
            "SELECT 1 FROM users WHERE LOWER(username)=LOWER(:u) OR LOWER(email)=LOWER(:e);",
            u=user.username, e=user.email)
        if existing:
            return {"error": "Username or email already taken"}
        
        conn.run("BEGIN")
        conn.run(
            "INSERT INTO users (username, email, password) VALUES (:u, :e, :p);",
            u=user.username, e=user.email, p=hash_password(user.password))
        conn.run("COMMIT")

        rows = conn.run("SELECT userid, username, role FROM users WHERE username=:u;", u=user.username)
        # new users always get role="user" default from DB
        token_data = {"sub": str(rows[0][0]), "username": rows[0][1], "role": rows[0][2]}
        access_token = create_access_token(data=token_data)
        
        return {
            "status": "registered", 
            "userid": rows[0][0], 
            "username": rows[0][1],
            "access_token": access_token,
            "token_type": "bearer"
        }
    
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Registration failed: " + str(e)}
    
    finally:
        conn.close()

# ── Login ─────────────────────────────────────────────────────

@router.post("/login")
def login(user: UserLogin):
    conn = get_db()
    try:
        # case-insensitive, but not ILIKE - that would treat % and _ in the
        # username as wildcards
        rows = conn.run(
            "SELECT userid, username, password, role FROM users WHERE LOWER(username)=LOWER(:u);",
            u=user.username.strip())
        # same message either way, so the form can't be used to probe usernames
        if not rows or not verify_password(user.password, rows[0][2]):
            return {"error": "Invalid username or password"}
        r = rows[0]

        if needs_rehash(r[2]):
            conn.run("UPDATE users SET password=:p WHERE userid=:id;",
                     p=hash_password(user.password), id=r[0])

        # generate JWT token with role
        access_token = create_access_token(data={
            "sub": str(r[0]), 
            "username": r[1],
            "role": r[3]
        })
        
        # Return userid and role — frontend stores this
        return {
            "status": "logged in", 
            "userid": r[0], 
            "username": r[1],
            "role": r[3],
            "access_token": access_token,
            "token_type": "bearer"
        }
    finally:
        conn.close()

# ── Forgot Password ──────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    """
    Generates a time-limited reset token and emails it to the user.
    Always returns a generic message for security (never reveal if email exists).
    """
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT userid, username, email FROM users WHERE LOWER(email)=LOWER(:e);",
            e=req.email.strip())
        
        if rows:
            user_id = rows[0][0]
            username = rows[0][1]
            actual_email = rows[0][2]
            
            # Create a short-lived JWT token (15 minutes)
            reset_token = jwt.encode(
                {
                    "sub": str(user_id),
                    "purpose": "password_reset",
                    "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
                },
                SECRET_KEY,
                algorithm=ALGORITHM
            )
            
            # Send the email
            if not send_reset_email(actual_email, username, reset_token):
                print(f"[SMTP] password reset email failed for userid {user_id}")

        # Always return generic message (security best practice)
        return {"status": "If an account with that email exists, a password reset link has been sent."}
    
    finally:
        conn.close()

# ── Reset Password ────────────────────────────────────────────

@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    """
    Validates the reset token and updates the user's password.
    """
    if len(req.new_password) < 4:
        return {"error": "Password must be at least 4 characters"}
    
    try:
        # Decode and verify the token
        payload = jwt.decode(req.token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Ensure this token was specifically for password reset
        if payload.get("purpose") != "password_reset":
            return {"error": "Invalid reset token"}
        
        user_id = int(payload.get("sub"))
        
    except jwt.ExpiredSignatureError:
        return {"error": "This reset link has expired. Please request a new one."}
    except jwt.PyJWTError:
        return {"error": "Invalid or tampered reset token."}
    
    # Token is valid — update the password
    conn = get_db()
    try:
        conn.run("BEGIN")
        # Double check if the user actually exists still
        existing = conn.run("SELECT 1 FROM users WHERE userid=:id;", id=user_id)
        if not existing:
            return {"error": "User no longer exists."}

        conn.run(
            "UPDATE users SET password=:p WHERE userid=:id;",
            p=hash_password(req.new_password), id=user_id)
        conn.run("COMMIT")
        return {"status": "Password has been reset successfully!"}
    except Exception as e:
        conn.run("ROLLBACK")
        return {"error": "Failed to reset password: " + str(e)}
    finally:
        conn.close()

# ── Guest Login ───────────────────────────────────────────────

@router.get("/guest")
def guest_login():
    """Guest gets userid=0 — frontend uses this to block write actions."""
    return {"status": "guest", "userid": 0, "username": "Guest"}

# ── Who am I ──────────────────────────────────────────────────
# Has to sit above /{user_id}, or FastAPI would try to read "me" as an id.

@router.get("/me")
def who_am_i(current_user: dict = Depends(get_current_user)):
    """The logged-in user, with their role read fresh from the database."""
    conn = get_db()
    try:
        rows = conn.run("SELECT userid, username, role FROM users WHERE userid=:id;", id=current_user["userid"])
    finally:
        conn.close()
    if not rows:
        return {"error": "User not found"}
    return {"userid": rows[0][0], "username": rows[0][1], "role": rows[0][2]}

# ── Profile ───────────────────────────────────────────────────

@router.get("/{user_id}")
def get_profile(user_id: int, current_user: dict = Depends(get_current_user)):
    check_owner_or_admin(current_user, user_id)
    conn = get_db()
    try:
        rows = conn.run(
            "SELECT userid, username, email, joindate, photourl FROM users WHERE userid=:id;",
            id=user_id)
        if not rows:
            return {"error": "User not found"}
        r = rows[0]
        return {"id": r[0], "username": r[1], "email": r[2], "joindate": str(r[3]), "photourl": r[4]}
    finally:
        conn.close()

# ── User Stats ────────────────────────────────────────────────

@router.get("/{user_id}/stats")
def get_user_stats(user_id: int, current_user: dict = Depends(get_current_user)):
    check_owner_or_admin(current_user, user_id)
    conn = get_db()
    try:
        reviews_count = conn.run("SELECT COUNT(*) FROM review WHERE userid=:id;", id=user_id)[0][0]
        watchlist_count = conn.run("SELECT COUNT(*) FROM watchlist WHERE userid=:id;", id=user_id)[0][0]
        recommends_count = conn.run("SELECT COUNT(*) FROM customlistitem WHERE userid=:id AND listname='Favorites';", id=user_id)[0][0]
        
        return {
            "reviews_written": reviews_count,
            "items_watchlisted": watchlist_count,
            "total_recommends": recommends_count
        }
    finally:
        conn.close()
