# Project Title: WordDuel

**Project Members**
* Timothy Chan (TimothyChan2912)
* Bushra Asif 
* Aneesh Ramanathan
* Nagi Ebeid

## Brief Description
A competitive twist on the popular game Wordle, adding PvP and various game modes for a more dynamic gaming experience.

## Dependencies
* Python 3.12
* MySQL 8.0.42 (Server + optionally Workbench)
* pip packages: `flask`, `flask-socketio`, `mysql-connector-python`, `werkzeug`, `python-dotenv`

## Setup & Running

### 1. Clone the repository
```bash
git clone <repo-url>
cd WordDuel
```

### 2. Install Python dependencies
```bash
pip install flask flask-socketio mysql-connector-python werkzeug python-dotenv
```

### 3. Configure environment variables

Copy the example below into a `.env` file in the project root and fill in your values:
```
FLASK_SECRET_KEY=your-secret-key-here
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your-mysql-password
DB_NAME=WordDuel
DB_PORT=3306
```

### 4. Set up the database

Start your MySQL server, then run the schema script to create the database and tables:
```bash
mysql -u root -p < database/db.sql
```

### 5. Run the application
```bash
python app.py
```

The server starts on `http://localhost:5001`. Open that URL in your browser to play.