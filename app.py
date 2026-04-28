from flask import Flask, render_template, request, session, jsonify, url_for, redirect, flash
from flask_socketio import SocketIO, emit, join_room
import os, random, time
import mysql.connector.pooling
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps
from words import WORDS, VALID_WORDS

# Bot constants
BOT_WAIT_TIME = 12       # seconds before spawning a bot if no match found
BOT_USER_ID   = "bot"
BOT_USERNAME  = "WordBot"
BOT_ELO       = 1000
BOT_DELAY_MIN = 3        # min seconds between bot guesses
BOT_DELAY_MAX = 8        # max seconds between bot guesses

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
matchmaking_queues = {"classic": [], "timed": []}
active_matches  = {}   # match_id  → match dict
player_to_match = {}   # user_id   → match_id
sid_to_user     = {}   # socket id → user_id

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

def _remove_from_queue(user_id):
    for mode in matchmaking_queues:
        matchmaking_queues[mode] = [
            p for p in matchmaking_queues[mode] if p["user_id"] != user_id
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
                "SELECT id, username, elo, wins, losses, games_played FROM players WHERE id = %s",
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
            cur.close()
    except Exception as e:
        print(e)
        player = {"username": session["username"], "elo": 1000, "wins": 0, "losses": 0, "games_played": 0}
        recent = []

    rank_name, rank_color = get_rank(player["elo"] if player else 1000)
    return render_template(
        "dashboard.html",
        player=player,
        recent_matches=recent,
        user_id=user_id,
        rank_name=rank_name,
        rank_color=rank_color,
    )

@app.route("/game")
@login_required
def game():
    mode = request.args.get("mode", "classic")
    if mode not in ("classic", "timed"):
        mode = "classic"
    # Navigating to /game always starts fresh — drop any stale match reference
    player_to_match.pop(session["user_id"], None)
    return render_template("game.html", username=session["username"], mode=mode)

@app.route("/leaderboard")
@login_required
def leaderboard():
    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute(
                """
                SELECT username, elo, wins, losses, games_played,
                       ROUND(wins / NULLIF(games_played, 0) * 100, 1) AS win_rate
                FROM   players
                ORDER  BY elo DESC
                LIMIT  50
                """
            )
            players = cur.fetchall()
            cur.close()
    except Exception as e:
        print(e)
        players = []

    for i, p in enumerate(players):
        p["rank_name"], p["rank_color"] = get_rank(p["elo"])
        p["position"] = i + 1

    return render_template(
        "leaderboard.html",
        players=players,
        current_user=session["username"],
    )

# ── SocketIO events ───────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    user_id = session.get("user_id")
    print(f"[CONNECT] sid={request.sid} user_id={user_id}")
    if not user_id:
        print("[CONNECT] Rejected — no session")
        return False
    sid_to_user[request.sid] = user_id
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

    _remove_from_queue(user_id)

    try:
        with get_db() as db:
            cur = db.cursor(dictionary=True)
            cur.execute("SELECT elo FROM players WHERE id = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
        elo = row["elo"] if row else 1000
    except Exception:
        elo = 1000

    joined_at = time.time()
    matchmaking_queues[mode].append({
        "user_id":   user_id,
        "username":  username,
        "elo":       elo,
        "sid":       request.sid,
        "joined_at": joined_at,
    })
    print(f"[QUEUE] {username} joined {mode} queue. Queue size: {len(matchmaking_queues[mode])}")
    emit("queue_joined", {"mode": mode})
    _try_match(mode)
    # If still unmatched after BOT_WAIT_TIME, spawn a bot opponent
    socketio.start_background_task(_maybe_bot_match, user_id, mode, joined_at)

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
    if not ps or ps["done"]:
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

# ── Matchmaking helpers ───────────────────────────────────────────────────────
def _try_match(mode):
    queue = matchmaking_queues[mode]
    print(f"[MATCH] Trying to match in {mode}. Queue: {[p['username'] for p in queue]}")
    if len(queue) < 2:
        return

    best, min_diff = None, float("inf")
    for i in range(len(queue)):
        for j in range(i + 1, len(queue)):
            if queue[i]["user_id"] == queue[j]["user_id"]:
                continue  # prevent same user from matching themselves
            diff      = abs(queue[i]["elo"] - queue[j]["elo"])
            wait      = max(time.time() - queue[i]["joined_at"], time.time() - queue[j]["joined_at"])
            threshold = 200 + wait * 10
            if diff < threshold and diff < min_diff:
                min_diff = diff
                best     = (i, j)

    if best is None:
        return  # no eligible pair yet; bot fallback handles the timeout

    i, j = best
    p2 = queue.pop(j)
    p1 = queue.pop(i)
    _create_match(p1, p2, mode)


def _maybe_bot_match(user_id, mode, joined_at):
    """After BOT_WAIT_TIME seconds, pair the still-waiting player with a bot."""
    socketio.sleep(BOT_WAIT_TIME)
    queue = matchmaking_queues[mode]
    for idx, p in enumerate(queue):
        if p["user_id"] == user_id and p["joined_at"] == joined_at:
            queue.pop(idx)
            _create_bot_match(p, mode)
            return


def _create_bot_match(player, mode):
    """Pair a human player with the bot."""
    bot      = {"user_id": BOT_USER_ID, "username": BOT_USERNAME,
                "elo": BOT_ELO, "sid": None, "joined_at": time.time()}
    word     = random.choice(WORDS).upper()
    match_id = f"m_{player['user_id']}_bot_{int(time.time()*1000)}"
    start    = time.time()
    duration = 120 if mode == "timed" else None

    match = {
        "id":        match_id,
        "word":      word,
        "mode":      mode,
        "start_time": start,
        "duration":  duration,
        "ended":     False,
        "bot_match": True,
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
        "opponent":     BOT_USERNAME,
        "opponent_elo": BOT_ELO,
        "duration":     duration,
        "start_time":   start,
    }, room=player["sid"])

    print(f"[BOT] Created bot match {match_id} for {player['username']}")

    if mode == "timed" and duration:
        socketio.start_background_task(_timed_end, match_id, duration)
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

def _create_match(p1, p2, mode):
    word      = random.choice(WORDS).upper()
    match_id  = f"m_{p1['user_id']}_{p2['user_id']}_{int(time.time()*1000)}"
    start     = time.time()
    duration  = 120 if mode == "timed" else None

    match = {
        "id":         match_id,
        "word":       word,
        "mode":       mode,
        "start_time": start,
        "duration":   duration,
        "ended":      False,
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
            "opponent":     opp["username"],
            "opponent_elo": opp["elo"],
            "duration":     duration,
            "start_time":   start,
        }, room=p["sid"])

    if mode == "timed" and duration:
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
    if p1["won"] and not p2["won"]:
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
                for ps in plist:
                    pid       = ps["user_id"]
                    is_winner = pid == winner_id
                    is_draw   = winner_id is None
                    cur.execute(
                        """
                        UPDATE players SET
                            elo          = GREATEST(100, elo + %s),
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
        }, room=ps["sid"])

    for ps in plist:
        player_to_match.pop(ps["user_id"], None)
    active_matches.pop(match_id, None)


if __name__ == "__main__":
    socketio.run(app, debug=False, host="0.0.0.0", port=5001, allow_unsafe_werkzeug=True)
