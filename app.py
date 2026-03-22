from flask import Flask, render_template, request, session, jsonify, url_for, redirect, flash
import os
import mysql.connector.pooling
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

pool_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": os.getenv("DB_PORT"),
    "autocommit": True,
    "pool_size": 10,
    "pool_reset_session": True
}

connection_pool = mysql.connector.pooling.MySQLConnectionPool(**pool_config)

def get_db_connection():
    return connection_pool.get_connection()


@app.route('/')
def index():
    return render_template('auth.html')


@app.route('/auth', methods=['GET', 'POST'])

def auth():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'login':
            username = request.form.get('username')
            password = request.form.get('password')

            try:
                with get_db_connection() as db:
                    cursor = db.cursor(dictionary=True)
                    cursor.execute("SELECT * FROM players WHERE username = %s", (username,))
                    user = cursor.fetchone()
                    cursor.close()

                    if user:
                        if check_password_hash(user['password_hash'], password):
                            session['user_id'] = user['id']
                            session['username'] = user['username']
                            flash(f"Welcome back, {username}!", "success")
                            return redirect(url_for('game'))
                        else:
                            flash("Incorrect password. Please try again.", "danger")
                            return render_template('auth.html')
                    else:
                        flash("User not found. Please register first.", "warning")
                        return render_template('auth.html')
            except Exception as e:
                print(f"Database error: {e}")
                flash("An error occurred. Please try again later.", "danger")
                return render_template('auth.html')
        else:
            username = request.form.get('username')
            email    = request.form.get('email')
            password = request.form.get('password')

            hashed_password = generate_password_hash(password)
            try:
                with get_db_connection() as db:
                    cursor = db.cursor()
                    cursor.execute("INSERT INTO players (username, email, password_hash) VALUES (%s, %s, %s)", 
                                   (username, email, hashed_password))
                    user_id = cursor.lastrowid
                    cursor.close()
            except Exception as e:
                print(f"Database error: {e}")
                flash("An error occurred. Please try again later.", "danger")
                return render_template('auth.html')
            
            session['user_id'] = user_id
            session['username'] = username
            flash(f"Welcome, {username}! You've been registered successfully.", "success")
            return redirect(url_for('game'))
    return render_template('auth.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/game')
def game():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('game.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
