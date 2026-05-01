from flask import Flask, render_template, request, session, jsonify, url_for, redirect, flash
from flask_socketio import SocketIO, emit, join_room
import os, random, time
from datetime import date, timedelta
import mysql.connector.pooling
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps
from words import WORDS, VALID_WORDS, CATEGORY_WORDS

# Bot constants
BOT_WAIT_TIME = 12       # seconds before spawning a bot if no match found
BOT_USER_ID   = "bot"
BOT_USERNAME  = "WordBot"
BOT_ELO       = 1000
BOT_DELAY_MIN = 3        # min seconds between bot guesses
BOT_DELAY_MAX = 8        # max seconds between bot guesses
STREAK_DURATION = 180    # seconds for a streak match (3 minutes)

ELO_COL = {"classic": "elo", "timed": "elo_timed", "streak": "elo_streak"}

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-in-prod")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

pool_config = {
    "host":             os.getenv("DB_HOST", "localhost"),
    "user":             os.getenv("DB_USER", "root"),
    "password":         os.getenv("DB_PASSWORD", ""),
    "database":         os.getenv("DB_NAME", "WordDuel"),
    "port":             int(os.getenv("DB_PORT", 3306)),
    "autocommit":       True,
    "pool_size":        10,
    "pool_reset_session": True,
}
connection_pool = mysql.connector.pooling.MySQLConnectionPool(**pool_config)

def get_db():
    return connection_pool.get_connection()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated

# ── In-memory state ──────────────────────────────────────────────────────────
CATEGORIES = ["general", "sports", "science", "movies", "food", "animals", "geography", "music"]
matchmaking_queues = {
    mode: {cat: [] for cat in CATEGORIES}
    for mode in ("classic", "timed", "streak")
}
active_matches  = {}   # match_id  → match dict
player_to_match = {}   # user_id   → match_id
sid_to_user     = {}   # socket id → user_id
post_match_rooms   = {}  # user_id   → match_id (for post-game chat)
user_to_sids       = {}  # user_id   → set of active sids (for challenge notifications)
pending_challenges = {}  # cid (str) → challenge dict
private_waiting    = {}  # match_key → lobby dict

# ── Wordle core logic ─────────────────────────────────────────────────────────
def check_guess(guess, answer):
    result = ["absent"] * 5
    answer_chars = list(answer)
    guess_chars  = list(guess)
    for i in range(5):
        if guess_chars[i] == answer_chars[i]:
            result[i]       = "correct"
            answer_chars[i] = None
            guess_chars[i]  = None
    for i in range(5):
        if guess_chars[i] is not None and guess_chars[i] in answer_chars:
            result[i] = "present"
            answer_chars[answer_chars.index(guess_chars[i])] = None
    return result

def calculate_score(guess_number, time_taken, won):
    if not won:
        return 0
    base        = 700 - (guess_number - 1) * 100
    speed_bonus = max(0, int(120 - time_taken))
    return max(100, base + speed_bonus)

def elo_delta(winner_elo, loser_elo, k=32):
    expected   = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    win_delta  =  int(k * (1 - expected))
    lose_delta = -int(k * expected)
    return win_delta, lose_delta

def get_rank(elo):
    if elo < 800:   return "Bronze",   "#cd7f32"
    if elo < 1000:  return "Silver",   "#c0c0c0"
    if elo < 1200:  return "Gold",     "#ffd700"
    if elo < 1400:  return "Platinum", "#a0e8d0"
    if elo < 1600:  return "Diamond",  "#b9f2ff"
    return           "Master",          "#ff6ec7"

def get_daily_word():
    rng = random.Random(date.today().toordinal())
    category = rng.choice(CATEGORIES)
    word = rng.choice(CATEGORY_WORDS.get(category, WORDS)).upper()
    return word, category

def _remove_from_queue(user_id):
    for mode in matchmaking_queues:
        for cat in matchmaking_queues[mode]:
            matchmaking_queues[mode][cat] = [
                p for p in matchmaking_queues[mode][cat] if p["user_id"] != user_id
            ]

# ── HTTP routes ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("auth.html")

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "login":
            username = request.form.get("username")
            password = request.form.get("password")
            try:
                with get_db() as db:
                    cur = db.cursor(dictionary=True)
                    cur.execute("SELECT * FROM players WHERE username = %s", (username,))
                    user = cur.fetchone()
                    cur.close()
                if user and check_password_hash(user["password_hash"], password):
                    session["user_id"]  = user["id"]
                    session["username"] = user["username"]
                    flash(f"Welcome back, {username}!", "success")
                    return redirect(url_for("dashboard"))
                flash("Invalid username or password.", "danger")
            except Exception as e:
                print(e)
                flash("Database error. Please try again.", "danger")
        else:
            username = request.form.get("username")
            email    = request.form.get("email")
            password = request.form.get("password")
            try:
                with get_db() as db:
                    cur = db.cursor()
                    cur.execute(
                        "INSERT INTO players (username, email, password_hash) VALUES (%s, %s, %s)",
                        (username, email, generate_password_hash(password)),
                    )
                    user_id = cur.lastrowid
                    cur.close()
                session["user_id"]  = user_id
                session["username"] = username
                flash(f"Welcome, {username}!", "success")
                return redirect(url_for("dashboard"))
            except Exception as e:
                print(e)
                flash("Registration failed. Username or email may already exist.", "danger")
    return render_template("auth.html")

@app.route("/logout")
def logout():
    _remove_from_queue(session.get("user_id"))
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                "SELECT id, username, elo, elo_timed, elo_streak, wins, losses, games_played FROM players WHERE id = %s",
                (user_id,),
            )
            player = cur.fetchone()
            cur.execute(
                """
                SELECT m.id, m.game_mode, m.completed_at,
                       p1.username AS player1, p2.username AS player2,
                       mr.winner_id, mr.player1_score, mr.player2_score
                FROM   matches m
                JOIN   players p1 ON m.player1_id = p1.id
                JOIN   players p2 ON m.player2_id = p2.id
                LEFT JOIN match_results mr ON m.id = mr.match_id
                WHERE  (m.player1_id = %s OR m.player2_id = %s)
                  AND  m.status = 'completed'
                ORDER  BY m.completed_at DESC LIMIT 5
                """,
                (user_id, user_id),
            )
            recent = cur.fetchall()
            # Mode breakdown (classic vs timed)
            cur.execute(
                """
                SELECT m.game_mode,
                       COUNT(*) AS games,
                       SUM(CASE WHEN mr.winner_id = %s THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN mr.winner_id IS NOT NULL AND mr.winner_id != %s THEN 1 ELSE 0 END) AS losses
                FROM matches m
                LEFT JOIN match_results mr ON m.id = mr.match_id
                WHERE (m.player1_id = %s OR m.player2_id = %s) AND m.status = 'completed'
                GROUP BY m.game_mode
                """,
                (user_id, user_id, user_id, user_id),
            )
            mode_stats = {r["game_mode"]: r for r in cur.fetchall()}

            # Activity last 14 days
            cur.execute(
                """
                SELECT DATE(m.completed_at) AS day,
                       COUNT(*) AS games,
                       SUM(CASE WHEN mr.winner_id = %s THEN 1 ELSE 0 END) AS wins
                FROM matches m
                LEFT JOIN match_results mr ON m.id = mr.match_id
                WHERE (m.player1_id = %s OR m.player2_id = %s)
                  AND m.status = 'completed'
                  AND m.completed_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
                GROUP BY DATE(m.completed_at)
                ORDER BY day
                """,
                (user_id, user_id, user_id),
            )
            activity_rows = {r["day"]: r for r in cur.fetchall()}
            cur.close()
    except Exception as e:
        print(e)
        player = {"username": session["username"], "elo": 1000, "wins": 0, "losses": 0, "games_played": 0}
        recent = []
        mode_stats = {}
        activity_rows = {}

    # Fill in all 14 days (including days with no games)
    today = date.today()
    activity = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        row = activity_rows.get(d, {})
        activity.append({
            "label": d.strftime("%b %d"),
            "games": int(row.get("games", 0) or 0),
            "wins":  int(row.get("wins",  0) or 0),
        })

    elo_classic = (player["elo"]        if player else None) or 1000
    elo_timed   = (player["elo_timed"]  if player else None) or 1000
    elo_streak  = (player["elo_streak"] if player else None) or 1000
    rank_name,        rank_color        = get_rank(elo_classic)
    rank_timed_name,  rank_timed_color  = get_rank(elo_timed)
    rank_streak_name, rank_streak_color = get_rank(elo_streak)
    return render_template(
        "dashboard.html",
        player=player,
        recent_matches=recent,
        user_id=user_id,
        rank_name=rank_name,               rank_color=rank_color,
        rank_timed_name=rank_timed_name,   rank_timed_color=rank_timed_color,
        rank_streak_name=rank_streak_name, rank_streak_color=rank_streak_color,
        mode_stats=mode_stats,
        activity=activity,
    )

@app.route("/game")
@login_required
def game():
    mode = request.args.get("mode", "classic")
    if mode not in ("classic", "timed", "streak"):
        mode = "classic"
    player_to_match.pop(session["user_id"], None)
    return render_template("game.html", username=session["username"], mode=mode)

@app.route("/leaderboard")
@login_required
def leaderboard():
    mode = request.args.get("mode", "classic")
    if mode not in ELO_COL:
        mode = "classic"
    col = ELO_COL[mode]
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                f"""
                SELECT username, elo, elo_timed, elo_streak, wins, losses, games_played,
                       ROUND(wins / NULLIF(games_played, 0) * 100, 1) AS win_rate
                FROM   players
                ORDER  BY {col} DESC
                LIMIT  50
                """
            )
            players = cur.fetchall()
            cur.close()
    except Exception as e:
        print(e)
        players = []

    for i, p in enumerate(players):
        display_elo = p[col] or 1000
        p["display_elo"] = display_elo
        p["rank_name"], p["rank_color"] = get_rank(display_elo)
        p["position"] = i + 1

    return render_template(
        "leaderboard.html",
        players=players,
        current_user=session["username"],
        mode=mode,
    )

@app.route("/friends")
@login_required
def friends():
    return render_template("friends.html")


@app.route("/daily")
@login_required
def daily():
    user_id = session["user_id"]
    today   = date.today()
    word, category = get_daily_word()
    puzzle_number = today.toordinal() - date(2024, 1, 1).toordinal() + 1

    my_row = None
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM daily_results WHERE player_id=%s AND date=%s",
                (user_id, today),
            )
            my_row = cur.fetchone()
            cur.close()
    except Exception as e:
        print(e)

    prior_guesses = []
    prior_results = []
    if my_row and my_row.get("guesses"):
        prior_guesses = my_row["guesses"].split(",")
        prior_results = [check_guess(g, word) for g in prior_guesses]

    completed   = bool(my_row and (my_row["solved"] or my_row["guess_count"] >= 6))
    reveal_word = word if completed else None
    hint_letter = word[0] if (len(prior_guesses) >= 3 and not completed) else None

    lb = []
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                """SELECT p.username, dr.solved, dr.guess_count, dr.completed_at
                   FROM daily_results dr
                   JOIN players p ON dr.player_id = p.id
                   WHERE dr.date = %s
                   ORDER BY dr.solved DESC, dr.guess_count ASC, dr.completed_at ASC
                   LIMIT 50""",
                (today,),
            )
            lb = cur.fetchall()
            cur.close()
    except Exception as e:
        print(e)

    return render_template(
        "daily.html",
        today=today.strftime("%B %d, %Y"),
        puzzle_number=puzzle_number,
        category=category,
        prior_guesses=prior_guesses,
        prior_results=prior_results,
        completed=completed,
        reveal_word=reveal_word,
        hint_letter=hint_letter,
        lb=lb,
        username=session["username"],
    )


@app.route("/api/daily/guess", methods=["POST"])
@login_required
def api_daily_guess():
    user_id = session["user_id"]
    today   = date.today()
    word = get_daily_word()[0]

    data  = request.get_json() or {}
    guess = data.get("guess", "").upper().strip()

    if len(guess) != 5:
        return jsonify({"error": "Word must be 5 letters"}), 400
    if guess.lower() not in VALID_WORDS:
        return jsonify({"error": "Not in word list"}), 400

    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM daily_results WHERE player_id=%s AND date=%s",
                (user_id, today),
            )
            row = cur.fetchone()
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500

    if row and (row["solved"] or row["guess_count"] >= 6):
        return jsonify({"error": "Already completed today's challenge"}), 400

    result      = check_guess(guess, word)
    won         = all(r == "correct" for r in result)
    prev_list   = row["guesses"].split(",") if (row and row["guesses"]) else []
    prev_list.append(guess)
    guess_count = len(prev_list)
    completed   = won or guess_count >= 6

    try:
        with get_db() as db:
            cur = db.cursor()
            if row:
                cur.execute(
                    "UPDATE daily_results SET guesses=%s, guess_count=%s, solved=%s, "
                    "completed_at=NOW() WHERE player_id=%s AND date=%s",
                    (",".join(prev_list), guess_count, 1 if won else 0, user_id, today),
                )
            else:
                cur.execute(
                    "INSERT INTO daily_results (player_id, date, solved, guess_count, guesses, completed_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW())",
                    (user_id, today, 1 if won else 0, guess_count, ",".join(prev_list)),
                )
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500

    return jsonify({
        "result":       result,
        "won":          won,
        "guess_number": guess_count,
        "completed":    completed,
        "word":         word if completed else None,
        "hint_letter":  word[0] if (guess_count >= 3 and not completed) else None,
    })


# ── Friends HTTP API ─────────────────────────────────────────────────────────

@app.route("/api/friends")
@login_required
def api_friends():
    user_id = session["user_id"]
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                """SELECT p.id, p.username, p.elo
                   FROM friends f JOIN players p ON f.friend_id = p.id
                   WHERE f.player_id = %s AND f.status = 'accepted'
                   ORDER BY p.username""",
                (user_id,),
            )
            friends = cur.fetchall()
            cur.execute(
                """SELECT p.id, p.username, p.elo
                   FROM friends f JOIN players p ON f.player_id = p.id
                   WHERE f.friend_id = %s AND f.status = 'pending'
                   ORDER BY f.created_at DESC""",
                (user_id,),
            )
            incoming = cur.fetchall()
            cur.execute(
                """SELECT p.id, p.username, p.elo
                   FROM friends f JOIN players p ON f.friend_id = p.id
                   WHERE f.player_id = %s AND f.status = 'pending'
                   ORDER BY f.created_at DESC""",
                (user_id,),
            )
            outgoing = cur.fetchall()
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500

    for f in friends:
        f["online"] = bool(user_to_sids.get(f["id"]))
        f["rank_name"], f["rank_color"] = get_rank(f["elo"])

    return jsonify({"friends": friends, "incoming": incoming, "outgoing": outgoing})


@app.route("/api/users/search")
@login_required
def api_users_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"users": []})
    user_id = session["user_id"]
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                """SELECT p.id, p.username, p.elo,
                          f.status  AS friend_status,
                          f2.status AS reverse_status
                   FROM players p
                   LEFT JOIN friends f  ON f.player_id  = %s AND f.friend_id  = p.id
                   LEFT JOIN friends f2 ON f2.player_id = p.id AND f2.friend_id = %s
                   WHERE p.username LIKE %s AND p.id != %s
                   LIMIT 8""",
                (user_id, user_id, f"%{q}%", user_id),
            )
            users = cur.fetchall()
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500
    return jsonify({"users": users})


@app.route("/api/friends/request", methods=["POST"])
@login_required
def api_friend_request():
    user_id   = session["user_id"]
    data      = request.get_json() or {}
    target_id = data.get("user_id")
    if not target_id or target_id == user_id:
        return jsonify({"error": "Invalid user"}), 400
    try:
        with get_db() as db:
            cur = db.cursor()
            cur.execute(
                "INSERT IGNORE INTO friends (player_id, friend_id, status) VALUES (%s, %s, 'pending')",
                (user_id, target_id),
            )
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500

    for sid in user_to_sids.get(target_id, set()):
        socketio.emit("friend_request_received", {
            "from_id":       user_id,
            "from_username": session["username"],
        }, room=sid)

    return jsonify({"ok": True})


@app.route("/api/friends/accept", methods=["POST"])
@login_required
def api_friend_accept():
    user_id      = session["user_id"]
    data         = request.get_json() or {}
    requester_id = data.get("user_id")
    if not requester_id:
        return jsonify({"error": "Invalid user"}), 400
    try:
        with get_db() as db:
            cur = db.cursor()
            cur.execute(
                "UPDATE friends SET status='accepted' WHERE player_id=%s AND friend_id=%s AND status='pending'",
                (requester_id, user_id),
            )
            cur.execute(
                "INSERT IGNORE INTO friends (player_id, friend_id, status) VALUES (%s, %s, 'accepted')",
                (user_id, requester_id),
            )
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500
    return jsonify({"ok": True})


@app.route("/api/friends/decline", methods=["POST"])
@login_required
def api_friend_decline():
    user_id      = session["user_id"]
    data         = request.get_json() or {}
    requester_id = data.get("user_id")
    if not requester_id:
        return jsonify({"error": "Invalid user"}), 400
    try:
        with get_db() as db:
            cur = db.cursor()
            cur.execute(
                "DELETE FROM friends WHERE player_id=%s AND friend_id=%s AND status='pending'",
                (requester_id, user_id),
            )
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500
    return jsonify({"ok": True})


@app.route("/api/friends/remove", methods=["POST"])
@login_required
def api_friend_remove():
    user_id   = session["user_id"]
    data      = request.get_json() or {}
    friend_id = data.get("user_id")
    if not friend_id:
        return jsonify({"error": "Invalid user"}), 400
    try:
        with get_db() as db:
            cur = db.cursor()
            cur.execute(
                "DELETE FROM friends WHERE (player_id=%s AND friend_id=%s) OR (player_id=%s AND friend_id=%s)",
                (user_id, friend_id, friend_id, user_id),
            )
            cur.close()
    except Exception as e:
        print(e)
        return jsonify({"error": "Database error"}), 500
    return jsonify({"ok": True})


# ── SocketIO events ───────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    user_id = session.get("user_id")
    print(f"[CONNECT] sid={request.sid} user_id={user_id}")
    if not user_id:
        print("[CONNECT] Rejected — no session")
        return False
    sid_to_user[request.sid] = user_id
    if user_id not in user_to_sids:
        user_to_sids[user_id] = set()
    user_to_sids[user_id].add(request.sid)
    # Reconnect to active match
    match_id = player_to_match.get(user_id)
    if match_id and match_id in active_matches:
        match = active_matches[match_id]
        join_room(match_id)
        ps  = match["players"][str(user_id)]
        opp_id = str(ps["opponent_id"])
        opp = match["players"].get(opp_id, {})
        emit("reconnected", {
            "match_id":   match_id,
            "mode":       match["mode"],
            "duration":   match["duration"],
            "start_time": match["start_time"],
            "guesses":    ps["guesses"],
            "results":    ps["results"],
            "opponent":   ps["opponent_name"],
            "opponent_results": opp.get("results", []),
        })

@socketio.on("disconnect")
def on_disconnect():
    user_id = sid_to_user.pop(request.sid, None)
    if user_id:
        _remove_from_queue(user_id)
        post_match_rooms.pop(user_id, None)
        sids = user_to_sids.get(user_id, set())
        sids.discard(request.sid)
        if not sids:
            user_to_sids.pop(user_id, None)

@socketio.on("chat_message")
def on_chat_message(data):
    user_id  = session.get("user_id")
    username = session.get("username")
    if not user_id:
        return
    match_id = post_match_rooms.get(user_id)
    if not match_id:
        return
    message = str(data.get("message", "")).strip()[:200]
    if not message:
        return
    socketio.emit("chat_message", {
        "username": username,
        "message":  message,
    }, room=match_id)

@socketio.on("challenge_friend")
def on_challenge_friend(data):
    user_id  = session.get("user_id")
    username = session.get("username")
    if not user_id:
        return

    friend_id = data.get("friend_id")
    mode      = data.get("mode", "classic")
    category  = data.get("category", "general")

    if mode not in matchmaking_queues:
        mode = "classic"
    if category not in CATEGORIES:
        category = "general"

    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                "SELECT 1 FROM friends WHERE player_id=%s AND friend_id=%s AND status='accepted'",
                (user_id, friend_id),
            )
            ok = cur.fetchone()
            cur.execute("SELECT username FROM players WHERE id=%s", (friend_id,))
            friend_row = cur.fetchone()
            cur.close()
        if not ok:
            emit("challenge_error", {"message": "Not friends with this user"})
            return
        challenged_name = friend_row["username"] if friend_row else "Opponent"
    except Exception as e:
        print(e)
        emit("challenge_error", {"message": "Database error"})
        return

    if not user_to_sids.get(friend_id):
        emit("challenge_error", {"message": f"{challenged_name} is not online right now"})
        return

    cid       = f"c_{user_id}_{friend_id}_{int(time.time()*1000)}"
    match_key = f"pm_{user_id}_{friend_id}_{int(time.time()*1000)}"

    pending_challenges[cid] = {
        "challenger_id":    user_id,
        "challenger_name":  username,
        "challenged_id":    friend_id,
        "challenged_name":  challenged_name,
        "mode":             mode,
        "category":         category,
        "match_key":        match_key,
        "expires_at":       time.time() + 120,
    }
    private_waiting[match_key] = {
        "challenger_id":   user_id,
        "challenger_name": username,
        "challenged_id":   friend_id,
        "challenged_name": challenged_name,
        "mode":            mode,
        "category":        category,
        "players":         [],
        "expires_at":      time.time() + 120,
    }

    for sid in user_to_sids.get(friend_id, set()):
        socketio.emit("challenge_received", {
            "challenge_id":    cid,
            "challenger_name": username,
            "mode":            mode,
            "category":        category,
        }, room=sid)

    emit("challenge_sent", {
        "match_key":     match_key,
        "mode":          mode,
        "category":      category,
        "friend_name":   challenged_name,
    })


@socketio.on("accept_challenge")
def on_accept_challenge(data):
    user_id = session.get("user_id")
    if not user_id:
        return

    if player_to_match.get(user_id):
        emit("error", {"message": "You are already in a game"})
        return

    cid = data.get("challenge_id")
    ch  = pending_challenges.get(cid)

    if not ch or ch["challenged_id"] != user_id:
        emit("error", {"message": "Invalid or expired challenge"})
        return
    if time.time() > ch["expires_at"]:
        pending_challenges.pop(cid, None)
        emit("error", {"message": "Challenge expired"})
        return

    match_key = ch["match_key"]
    mode      = ch["mode"]
    category  = ch["category"]
    pending_challenges.pop(cid, None)

    for sid in user_to_sids.get(ch["challenger_id"], set()):
        socketio.emit("challenge_accepted_ack", {
            "match_key":   match_key,
            "mode":        mode,
            "category":    category,
            "accepted_by": session.get("username"),
        }, room=sid)

    emit("redirect_to_game", {
        "match_key": match_key,
        "mode":      mode,
        "category":  category,
    })


@socketio.on("decline_challenge")
def on_decline_challenge(data):
    user_id = session.get("user_id")
    if not user_id:
        return

    cid = data.get("challenge_id")
    ch  = pending_challenges.pop(cid, None)

    if ch:
        private_waiting.pop(ch.get("match_key"), None)
        for sid in user_to_sids.get(ch["challenger_id"], set()):
            socketio.emit("challenge_declined", {
                "declined_by": session.get("username"),
            }, room=sid)


@socketio.on("join_private_match")
def on_join_private_match(data):
    user_id  = session.get("user_id")
    username = session.get("username")
    if not user_id:
        return

    match_key = data.get("match_key")
    lobby     = private_waiting.get(match_key)

    if not lobby:
        emit("error", {"message": "Private match not found or expired"})
        return
    if time.time() > lobby["expires_at"]:
        private_waiting.pop(match_key, None)
        emit("error", {"message": "Private match expired"})
        return
    if user_id not in (lobby["challenger_id"], lobby["challenged_id"]):
        emit("error", {"message": "Not authorized for this match"})
        return

    match_mode = lobby["mode"]
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute("SELECT elo, elo_timed, elo_streak FROM players WHERE id=%s", (user_id,))
            row = cur.fetchone()
            cur.close()
        elo = (row[ELO_COL.get(match_mode, "elo")] if row else None) or 1000
    except Exception:
        elo = 1000

    player = {
        "user_id":   user_id,
        "username":  username,
        "elo":       elo,
        "sid":       request.sid,
        "joined_at": time.time(),
    }

    lobby["players"] = [p for p in lobby["players"] if p["user_id"] != user_id]
    lobby["players"].append(player)

    opp_name = lobby["challenged_name"] if user_id == lobby["challenger_id"] else lobby["challenger_name"]

    if len(lobby["players"]) == 2:
        p1, p2 = lobby["players"]
        del private_waiting[match_key]
        _create_match(p1, p2, lobby["mode"], lobby["category"])
    else:
        emit("private_match_waiting", {"waiting_for": opp_name})


@socketio.on("join_queue")
def on_join_queue(data):
    user_id  = session.get("user_id")
    username = session.get("username")
    print(f"[JOIN_QUEUE] sid={request.sid} user_id={user_id} username={username} data={data}")
    if not user_id:
        print("[JOIN_QUEUE] Rejected — no session")
        return

    mode = data.get("mode", "classic")
    if mode not in matchmaking_queues:
        mode = "classic"

    category = data.get("category", "general")
    if category not in CATEGORIES:
        category = "general"

    _remove_from_queue(user_id)
    post_match_rooms.pop(user_id, None)

    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute("SELECT elo, elo_timed, elo_streak FROM players WHERE id = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
        elo = (row[ELO_COL.get(mode, "elo")] if row else None) or 1000
    except Exception:
        elo = 1000

    joined_at = time.time()
    matchmaking_queues[mode][category].append({
        "user_id":   user_id,
        "username":  username,
        "elo":       elo,
        "sid":       request.sid,
        "joined_at": joined_at,
    })
    print(f"[QUEUE] {username} joined {mode}/{category} queue. Size: {len(matchmaking_queues[mode][category])}")
    emit("queue_joined", {"mode": mode, "category": category})
    _try_match(mode, category)
    socketio.start_background_task(_maybe_bot_match, user_id, mode, category, joined_at)

@socketio.on("forfeit")
def on_forfeit():
    user_id = session.get("user_id")
    if not user_id:
        return

    match_id = player_to_match.get(user_id)
    if not match_id or match_id not in active_matches:
        return

    match = active_matches[match_id]
    ps = match["players"].get(str(user_id))
    if not ps or ps["done"]:
        return

    ps["done"] = True
    ps["won"]  = False
    match["forfeited"] = True

    opp_id = str(ps["opponent_id"])
    opp_ps = match["players"].get(opp_id)
    if opp_ps and not opp_ps["done"]:
        opp_ps["done"] = True
        opp_ps["won"]  = True
        if not opp_ps["score"]:
            opp_ps["score"] = 100

    _end_match(match_id)

@socketio.on("leave_queue")
def on_leave_queue():
    user_id = session.get("user_id")
    if user_id:
        _remove_from_queue(user_id)
        emit("queue_left")

@socketio.on("submit_guess")
def on_submit_guess(data):
    user_id = session.get("user_id")
    if not user_id:
        return

    match_id = player_to_match.get(user_id)
    if not match_id or match_id not in active_matches:
        emit("error", {"message": "No active match"})
        return

    match = active_matches[match_id]
    ps = match["players"].get(str(user_id))
    if not ps or ps["done"] or ps.get("round_done"):
        return

    guess = data.get("guess", "").upper().strip()

    if len(guess) != 5:
        emit("invalid_guess", {"message": "Word must be 5 letters"})
        return
    if guess.lower() not in VALID_WORDS:
        emit("invalid_guess", {"message": "Not in word list"})
        return

    result       = check_guess(guess, match["word"])
    won          = all(r == "correct" for r in result)
    guess_number = len(ps["guesses"]) + 1

    ps["guesses"].append(guess)
    ps["results"].append(result)

    if match["mode"] == "streak":
        _handle_streak_guess(match_id, match, ps, guess, result, won, guess_number)
        return

    if won:
        ps["done"]       = True
        ps["won"]        = True
        ps["solve_time"] = time.time() - match["start_time"]
        ps["score"]      = calculate_score(guess_number, ps["solve_time"], True)
    elif guess_number >= 6:
        ps["done"] = True
        ps["won"]  = False

    emit("guess_result", {
        "guess":        guess,
        "result":       result,
        "guess_number": guess_number,
        "solved":       won,
        "game_over":    ps["done"],
        "score":        ps["score"],
    })

    # Notify opponent (color pattern only — no letters)
    opp_id = str(ps["opponent_id"])
    opp    = match["players"].get(opp_id)
    if opp and opp.get("sid"):  # skip if opponent is the bot (no socket)
        emit("opponent_progress", {
            "guesses_made":   guess_number,
            "solved":         won,
            "done":           ps["done"],
            "all_results":    ps["results"],
        }, room=opp["sid"])

    all_done = all(p["done"] for p in match["players"].values())
    if all_done or (won and match["mode"] == "classic"):
        _end_match(match_id)


def _handle_streak_guess(match_id, match, ps, guess, result, won, guess_number):
    opp_id = str(ps["opponent_id"])
    opp_ps = match["players"].get(opp_id)

    if won:
        ps["streak"]    += 1
        ps["round_done"] = True
        ps["round_won"]  = True

        emit("guess_result", {
            "guess":            guess,
            "result":           result,
            "guess_number":     guess_number,
            "solved":           True,
            "game_over":        False,
            "score":            ps["streak"] * 100,
            "streak_round_won": True,
            "streak":           ps["streak"],
        })

        if opp_ps and opp_ps.get("sid"):
            socketio.emit("opponent_progress", {
                "guesses_made": guess_number,
                "solved":       True,
                "done":         False,
                "all_results":  ps["results"],
            }, room=opp_ps["sid"])

        if all(p["round_done"] for p in match["players"].values()):
            if not match.get("round_transitioning"):
                match["round_transitioning"] = True
                socketio.start_background_task(_streak_next_round, match_id)

    elif guess_number >= 6:
        ps["done"]       = True
        ps["eliminated"] = True

        emit("guess_result", {
            "guess":        guess,
            "result":       result,
            "guess_number": guess_number,
            "solved":       False,
            "game_over":    True,
            "score":        0,
            "streak":       ps["streak"],
        })

        if opp_ps and opp_ps.get("sid"):
            socketio.emit("opponent_progress", {
                "guesses_made": guess_number,
                "solved":       False,
                "done":         True,
                "all_results":  ps["results"],
            }, room=opp_ps["sid"])

        if opp_ps and not opp_ps.get("eliminated"):
            opp_ps["done"]  = True
            opp_ps["won"]   = True
            opp_ps["score"] = opp_ps["streak"] * 100

        _end_match(match_id)

    else:
        emit("guess_result", {
            "guess":        guess,
            "result":       result,
            "guess_number": guess_number,
            "solved":       False,
            "game_over":    False,
            "score":        0,
        })

        if opp_ps and opp_ps.get("sid"):
            socketio.emit("opponent_progress", {
                "guesses_made": guess_number,
                "solved":       False,
                "done":         False,
                "all_results":  ps["results"],
            }, room=opp_ps["sid"])


def _streak_next_round(match_id):
    socketio.sleep(1.5)
    match = active_matches.get(match_id)
    if not match or match["ended"]:
        return

    match["current_round"] += 1
    idx = match["current_round"]

    if idx >= len(match.get("words") or []):
        _end_match(match_id)
        return

    match["word"]              = match["words"][idx]
    match["round_transitioning"] = False

    for ps in match["players"].values():
        ps["guesses"]    = []
        ps["results"]    = []
        ps["round_done"] = False
        ps["round_won"]  = False

    socketio.emit("streak_next_round", {"round": idx + 1}, room=match_id)


def _bot_play_streak(match_id):
    """Bot solves bot_target rounds then fails, ending the game."""
    bot_target = random.randint(1, 4)

    while True:
        # Wait for the start of a fresh round
        while True:
            match  = active_matches.get(match_id)
            if not match or match["ended"]:
                return
            bot_ps = match["players"].get(BOT_USER_ID)
            if not bot_ps or bot_ps.get("eliminated"):
                return
            if not bot_ps.get("round_done"):
                break
            socketio.sleep(0.5)

        current_streak = bot_ps.get("streak", 0)

        # Simulate thinking time
        socketio.sleep(random.uniform(BOT_DELAY_MIN, BOT_DELAY_MAX * 2))

        match  = active_matches.get(match_id)
        if not match or match["ended"]:
            return
        bot_ps = match["players"].get(BOT_USER_ID)
        if not bot_ps or bot_ps.get("round_done"):
            continue

        human_id = str(bot_ps["opponent_id"])
        human_ps = match["players"].get(human_id)

        if current_streak < bot_target:
            # Bot solves this round
            word   = match["word"]
            result = ["correct"] * 5
            bot_ps["guesses"].append(word)
            bot_ps["results"].append(result)
            bot_ps["streak"]    += 1
            bot_ps["round_done"] = True
            bot_ps["round_won"]  = True

            if human_ps and human_ps.get("sid"):
                socketio.emit("opponent_progress", {
                    "guesses_made": 1,
                    "solved":       True,
                    "done":         False,
                    "all_results":  [result],
                }, room=human_ps["sid"])

            if all(p["round_done"] for p in match["players"].values()):
                if not match.get("round_transitioning"):
                    match["round_transitioning"] = True
                    _streak_next_round(match_id)
        else:
            # Bot fails — make 6 wrong guesses
            word = match["word"]
            used = {word}
            for attempt in range(6):
                wrong = random.choice([w.upper() for w in VALID_WORDS if w.upper() not in used] or list(VALID_WORDS))
                used.add(wrong)
                r = check_guess(wrong, word)
                bot_ps["guesses"].append(wrong)
                bot_ps["results"].append(r)

                if human_ps and human_ps.get("sid"):
                    socketio.emit("opponent_progress", {
                        "guesses_made": attempt + 1,
                        "solved":       False,
                        "done":         attempt == 5,
                        "all_results":  bot_ps["results"],
                    }, room=human_ps["sid"])

                if attempt < 5:
                    socketio.sleep(random.uniform(2, 4))

                match = active_matches.get(match_id)
                if not match or match["ended"]:
                    return

            bot_ps["done"]       = True
            bot_ps["eliminated"] = True

            if human_ps and not human_ps.get("eliminated"):
                human_ps["done"]  = True
                human_ps["won"]   = True
                human_ps["score"] = human_ps.get("streak", 0) * 100

            _end_match(match_id)
            return

# ── Matchmaking helpers ───────────────────────────────────────────────────────
def _try_match(mode, category):
    queue = matchmaking_queues[mode][category]
    print(f"[MATCH] Trying to match in {mode}/{category}. Queue: {[p['username'] for p in queue]}")
    if len(queue) < 2:
        return

    best, min_diff = None, float("inf")
    for i in range(len(queue)):
        for j in range(i + 1, len(queue)):
            if queue[i]["user_id"] == queue[j]["user_id"]:
                continue
            diff      = abs(queue[i]["elo"] - queue[j]["elo"])
            wait      = max(time.time() - queue[i]["joined_at"], time.time() - queue[j]["joined_at"])
            threshold = 200 + wait * 10
            if diff < threshold and diff < min_diff:
                min_diff = diff
                best     = (i, j)

    if best is None:
        return

    i, j = best
    p2 = queue.pop(j)
    p1 = queue.pop(i)
    _create_match(p1, p2, mode, category)


def _maybe_bot_match(user_id, mode, category, joined_at):
    """After BOT_WAIT_TIME seconds, pair the still-waiting player with a bot."""
    socketio.sleep(BOT_WAIT_TIME)
    queue = matchmaking_queues[mode][category]
    for idx, p in enumerate(queue):
        if p["user_id"] == user_id and p["joined_at"] == joined_at:
            queue.pop(idx)
            _create_bot_match(p, mode, category)
            return


def _create_bot_match(player, mode, category="general"):
    """Pair a human player with the bot."""
    bot = {"user_id": BOT_USER_ID, "username": BOT_USERNAME,
           "elo": BOT_ELO, "sid": None, "joined_at": time.time()}

    cat_words = CATEGORY_WORDS.get(category, WORDS)
    if mode == "streak":
        words = [w.upper() for w in random.sample(cat_words, min(20, len(cat_words)))]
        word  = words[0]
    else:
        words = None
        word  = random.choice(cat_words).upper()

    match_id = f"m_{player['user_id']}_bot_{int(time.time()*1000)}"
    start    = time.time()
    duration = 120 if mode == "timed" else (STREAK_DURATION if mode == "streak" else None)

    match = {
        "id":                  match_id,
        "word":                word,
        "words":               words,
        "current_round":       0,
        "round_transitioning": False,
        "mode":                mode,
        "category":            category,
        "start_time":          start,
        "duration":            duration,
        "ended":               False,
        "bot_match":           True,
        "players": {
            str(player["user_id"]): _player_state(player, bot),
            BOT_USER_ID:            _player_state(bot, player),
        },
    }

    active_matches[match_id]           = match
    player_to_match[player["user_id"]] = match_id

    socketio.emit("match_found", {
        "match_id":     match_id,
        "mode":         mode,
        "category":     category,
        "opponent":     BOT_USERNAME,
        "opponent_elo": BOT_ELO,
        "duration":     duration,
        "start_time":   start,
    }, room=player["sid"])

    print(f"[BOT] Created bot match {match_id} for {player['username']}")

    if mode in ("timed", "streak") and duration:
        socketio.start_background_task(_timed_end, match_id, duration)

    if mode == "streak":
        socketio.start_background_task(_bot_play_streak, match_id)
    else:
        socketio.start_background_task(_bot_play, match_id)


def _bot_play(match_id):
    """Bot plays through the game asynchronously, guessing random valid words."""
    guess_pool = random.sample(list(VALID_WORDS), min(6, len(VALID_WORDS)))
    used       = set()

    for _ in range(6):
        match = active_matches.get(match_id)
        if not match or match["ended"]:
            return

        socketio.sleep(random.uniform(BOT_DELAY_MIN, BOT_DELAY_MAX))

        match = active_matches.get(match_id)
        if not match or match["ended"]:
            return

        bot_ps = match["players"].get(BOT_USER_ID)
        if not bot_ps or bot_ps["done"]:
            return

        guess = next((w.upper() for w in guess_pool if w.upper() not in used), None)
        if not guess:
            # fall back to any unused valid word
            guess = random.choice([w.upper() for w in VALID_WORDS if w.upper() not in used] or list(VALID_WORDS))
        used.add(guess)

        result       = check_guess(guess, match["word"])
        won          = all(r == "correct" for r in result)
        guess_number = len(bot_ps["guesses"]) + 1

        bot_ps["guesses"].append(guess)
        bot_ps["results"].append(result)

        if won:
            bot_ps["done"]       = True
            bot_ps["won"]        = True
            bot_ps["solve_time"] = time.time() - match["start_time"]
            bot_ps["score"]      = calculate_score(guess_number, bot_ps["solve_time"], True)
        elif guess_number >= 6:
            bot_ps["done"] = True
            bot_ps["won"]  = False

        human_id = str(bot_ps["opponent_id"])
        human_ps = match["players"].get(human_id)
        if human_ps and human_ps.get("sid"):
            socketio.emit("opponent_progress", {
                "guesses_made": guess_number,
                "solved":       won,
                "done":         bot_ps["done"],
                "all_results":  bot_ps["results"],
            }, room=human_ps["sid"])

        if bot_ps["done"]:
            if human_ps and human_ps["done"]:
                _end_match(match_id)
            elif match["mode"] == "classic" and won:
                _end_match(match_id)
            break

def _create_match(p1, p2, mode, category="general"):
    cat_words = CATEGORY_WORDS.get(category, WORDS)
    if mode == "streak":
        words = [w.upper() for w in random.sample(cat_words, min(20, len(cat_words)))]
        word  = words[0]
    else:
        words = None
        word  = random.choice(cat_words).upper()

    match_id  = f"m_{p1['user_id']}_{p2['user_id']}_{int(time.time()*1000)}"
    start     = time.time()
    duration  = 120 if mode == "timed" else (STREAK_DURATION if mode == "streak" else None)

    match = {
        "id":                  match_id,
        "word":                word,
        "words":               words,
        "current_round":       0,
        "round_transitioning": False,
        "mode":                mode,
        "category":            category,
        "start_time":          start,
        "duration":            duration,
        "ended":               False,
        "players": {
            str(p1["user_id"]): _player_state(p1, p2),
            str(p2["user_id"]): _player_state(p2, p1),
        },
    }

    active_matches[match_id]         = match
    player_to_match[p1["user_id"]]   = match_id
    player_to_match[p2["user_id"]]   = match_id

    join_room(match_id, sid=p1["sid"])
    join_room(match_id, sid=p2["sid"])

    for p, opp in [(p1, p2), (p2, p1)]:
        emit("match_found", {
            "match_id":     match_id,
            "mode":         mode,
            "category":     category,
            "opponent":     opp["username"],
            "opponent_elo": opp["elo"],
            "duration":     duration,
            "start_time":   start,
        }, room=p["sid"])

    if mode in ("timed", "streak") and duration:
        socketio.start_background_task(_timed_end, match_id, duration)

def _player_state(p, opp):
    return {
        "user_id":       p["user_id"],
        "username":      p["username"],
        "elo":           p["elo"],
        "sid":           p["sid"],
        "guesses":       [],
        "results":       [],
        "done":          False,
        "won":           False,
        "solve_time":    None,
        "score":         0,
        "opponent_id":   opp["user_id"],
        "opponent_name": opp["username"],
        # streak-mode fields (unused in other modes)
        "streak":        0,
        "eliminated":    False,
        "round_done":    False,
        "round_won":     False,
    }

def _timed_end(match_id, duration):
    socketio.sleep(duration)
    match = active_matches.get(match_id)
    if match and not match["ended"]:
        # Mark both undone players as done
        for ps in match["players"].values():
            ps["done"] = True
        _end_match(match_id)

def _end_match(match_id):
    match = active_matches.get(match_id)
    if not match or match["ended"]:
        return
    match["ended"] = True

    plist = list(match["players"].values())
    p1, p2 = plist[0], plist[1]

    # Determine winner
    winner_id = None
    if match["mode"] == "streak":
        p1_elim   = p1.get("eliminated", False)
        p2_elim   = p2.get("eliminated", False)
        p1_streak = p1.get("streak", 0)
        p2_streak = p2.get("streak", 0)
        p1["score"] = p1_streak * 100
        p2["score"] = p2_streak * 100
        if p1_elim and not p2_elim:
            winner_id = p2["user_id"]
        elif p2_elim and not p1_elim:
            winner_id = p1["user_id"]
        elif p1_streak > p2_streak:
            winner_id = p1["user_id"]
        elif p2_streak > p1_streak:
            winner_id = p2["user_id"]
        # else: draw (both eliminated on same round with equal streak)
    elif p1["won"] and not p2["won"]:
        winner_id = p1["user_id"]
    elif p2["won"] and not p1["won"]:
        winner_id = p2["user_id"]
    elif p1["won"] and p2["won"]:
        winner_id = p1["user_id"] if p1["solve_time"] < p2["solve_time"] else p2["user_id"]
    else:
        # Neither solved — whoever got more greens on last guess
        def last_greens(ps):
            return sum(1 for r in (ps["results"][-1] if ps["results"] else []) if r == "correct")
        g1, g2 = last_greens(p1), last_greens(p2)
        if g1 > g2:
            winner_id = p1["user_id"]
        elif g2 > g1:
            winner_id = p2["user_id"]

    elo_changes = {p1["user_id"]: 0, p2["user_id"]: 0}
    if winner_id:
        loser_id = p2["user_id"] if winner_id == p1["user_id"] else p1["user_id"]
        w = p1 if winner_id == p1["user_id"] else p2
        l = p2 if winner_id == p1["user_id"] else p1
        wd, ld = elo_delta(w["elo"], l["elo"])
        elo_changes[winner_id] = wd
        elo_changes[loser_id]  = ld

    is_bot_match = match.get("bot_match", False)

    if not is_bot_match:
        try:
            with get_db() as db:
                cur = db.cursor()
                cur.execute(
                    "INSERT INTO matches (player1_id, player2_id, status, game_mode, completed_at) "
                    "VALUES (%s, %s, 'completed', %s, NOW())",
                    (p1["user_id"], p2["user_id"], match["mode"]),
                )
                db_match_id = cur.lastrowid
                cur.execute(
                    "INSERT INTO match_results (match_id, winner_id, player1_score, player2_score) "
                    "VALUES (%s, %s, %s, %s)",
                    (db_match_id, winner_id, p1["score"], p2["score"]),
                )
                col = ELO_COL.get(match["mode"], "elo")
                for ps in plist:
                    pid       = ps["user_id"]
                    is_winner = pid == winner_id
                    is_draw   = winner_id is None
                    cur.execute(
                        f"""
                        UPDATE players SET
                            {col}        = GREATEST(100, {col} + %s),
                            games_played = games_played + 1,
                            wins         = wins   + %s,
                            losses       = losses + %s
                        WHERE id = %s
                        """,
                        (
                            elo_changes[pid],
                            1 if is_winner else 0,
                            1 if (not is_winner and not is_draw) else 0,
                            pid,
                        ),
                    )
                cur.close()
        except Exception as e:
            print(f"DB error in _end_match: {e}")
    elif is_bot_match and match.get("forfeited"):
        # Bot match forfeit — record the loss and ELO drop for the human player only
        human_ps = next((p for p in plist if p["user_id"] != BOT_USER_ID), None)
        if human_ps:
            _, ld = elo_delta(BOT_ELO, human_ps["elo"])
            try:
                with get_db() as db:
                    cur = db.cursor()
                    col = ELO_COL.get(match["mode"], "elo")
                    cur.execute(
                        f"""
                        UPDATE players SET
                            {col}        = GREATEST(100, {col} + %s),
                            games_played = games_played + 1,
                            losses       = losses + 1
                        WHERE id = %s
                        """,
                        (ld, human_ps["user_id"]),
                    )
                    cur.close()
            except Exception as e:
                print(f"DB error in bot forfeit: {e}")

    for ps in plist:
        pid = ps["user_id"]
        if pid == BOT_USER_ID or not ps.get("sid"):
            continue  # bot has no socket
        opp    = p2 if ps == p1 else p1
        result = "win" if pid == winner_id else ("draw" if not winner_id else "loss")
        elo_ch = 0 if is_bot_match else elo_changes.get(pid, 0)
        socketio.emit("game_over", {
            "result":            result,
            "word":              match["word"],
            "your_score":        ps["score"],
            "opponent_score":    opp["score"],
            "elo_change":        elo_ch,
            "your_guesses":      ps["guesses"],
            "your_results":      ps["results"],
            "opponent_guesses":  opp["guesses"],
            "opponent_results":  opp["results"],
            "your_streak":       ps.get("streak", 0),
            "opponent_streak":   opp.get("streak", 0),
            "mode":              match["mode"],
        }, room=ps["sid"])

    # Keep players in the Socket.IO room for post-match chat (real matches only)
    if not is_bot_match:
        for ps in plist:
            if ps["user_id"] != BOT_USER_ID:
                post_match_rooms[ps["user_id"]] = match_id

    for ps in plist:
        player_to_match.pop(ps["user_id"], None)
    active_matches.pop(match_id, None)


if __name__ == "__main__":
    socketio.run(app, debug=False, host="0.0.0.0", port=5001, allow_unsafe_werkzeug=True)
