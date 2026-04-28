(() => {
  const MODE     = INIT.mode;
  const MAX_ROWS = 6;
  const WORD_LEN = 5;

  // ── State ──────────────────────────────────────────────────────────────────
  const state = {
    currentRow: 0,
    currentCol: 0,
    currentGuess: [],
    done: false,
    matchId: null,
    opponent: null,
    timerInterval: null,
    matchStartTime: null,
    duration: null,
  };

  const keyState = {}; // letter → 'correct' | 'present' | 'absent'

  // ── DOM helpers ────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);

  function getTile(row, col) {
    return document.querySelector(`#board .board-row:nth-child(${row + 1}) .tile:nth-child(${col + 1})`);
  }
  function getOppTile(row, col) {
    return document.querySelector(`#opp-board .opp-row:nth-child(${row + 1}) .opp-tile:nth-child(${col + 1})`);
  }

  // ── Build board ────────────────────────────────────────────────────────────
  function buildBoard() {
    const board = $('board');
    board.innerHTML = '';
    for (let r = 0; r < MAX_ROWS; r++) {
      const row = document.createElement('div');
      row.className = 'board-row';
      for (let c = 0; c < WORD_LEN; c++) {
        const tile = document.createElement('div');
        tile.className = 'tile';
        row.appendChild(tile);
      }
      board.appendChild(row);
    }
  }

  function buildOppBoard() {
    const board = $('opp-board');
    board.innerHTML = '';
    for (let r = 0; r < MAX_ROWS; r++) {
      const row = document.createElement('div');
      row.className = 'opp-row';
      for (let c = 0; c < WORD_LEN; c++) {
        const tile = document.createElement('div');
        tile.className = 'opp-tile';
        row.appendChild(tile);
      }
      board.appendChild(row);
    }
  }

  // ── Build keyboard ─────────────────────────────────────────────────────────
  const ROWS = [
    ['Q','W','E','R','T','Y','U','I','O','P'],
    ['A','S','D','F','G','H','J','K','L'],
    ['ENTER','Z','X','C','V','B','N','M','⌫'],
  ];

  function buildKeyboard() {
    const kb = $('keyboard');
    kb.innerHTML = '';
    ROWS.forEach(letters => {
      const row = document.createElement('div');
      row.className = 'key-row';
      letters.forEach(letter => {
        const key = document.createElement('button');
        key.className = 'key' + (letter.length > 1 ? ' wide' : '');
        key.textContent = letter;
        key.dataset.key = letter;
        key.addEventListener('click', () => handleKey(letter));
        row.appendChild(key);
      });
      kb.appendChild(row);
    });
  }

  function updateKeyboard(guess, result) {
    const priority = { correct: 3, present: 2, absent: 1 };
    for (let i = 0; i < guess.length; i++) {
      const letter = guess[i];
      const status = result[i];
      if (!keyState[letter] || priority[status] > priority[keyState[letter]]) {
        keyState[letter] = status;
      }
    }
    document.querySelectorAll('.key').forEach(key => {
      const letter = key.dataset.key;
      if (keyState[letter]) {
        key.className = `key${letter.length > 1 ? ' wide' : ''} ${keyState[letter]}`;
      }
    });
  }

  // ── Input handling ─────────────────────────────────────────────────────────
  function handleKey(key) {
    if (state.done) return;
    if (key === 'ENTER') {
      submitGuess();
    } else if (key === '⌫' || key === 'Backspace') {
      deleteLetter();
    } else if (/^[A-Z]$/i.test(key) && key.length === 1) {
      addLetter(key.toUpperCase());
    }
  }

  document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key === 'Enter')     handleKey('ENTER');
    else if (e.key === 'Backspace') handleKey('⌫');
    else handleKey(e.key.toUpperCase());
  });

  function addLetter(letter) {
    if (state.currentCol >= WORD_LEN) return;
    const tile = getTile(state.currentRow, state.currentCol);
    if (!tile) return;
    tile.textContent = letter;
    tile.classList.add('filled');
    state.currentGuess.push(letter);
    state.currentCol++;
  }

  function deleteLetter() {
    if (state.currentCol <= 0) return;
    state.currentCol--;
    state.currentGuess.pop();
    const tile = getTile(state.currentRow, state.currentCol);
    if (!tile) return;
    tile.textContent = '';
    tile.classList.remove('filled');
  }

  function submitGuess() {
    if (state.currentCol < WORD_LEN) {
      shakeRow(state.currentRow);
      showMessage('Not enough letters');
      return;
    }
    const guess = state.currentGuess.join('');
    socket.emit('submit_guess', { guess });
  }

  // ── Row animations ─────────────────────────────────────────────────────────
  function shakeRow(row) {
    const rowEl = document.querySelector(`#board .board-row:nth-child(${row + 1})`);
    if (!rowEl) return;
    rowEl.querySelectorAll('.tile').forEach(t => {
      t.classList.remove('shake');
      void t.offsetWidth; // reflow
      t.classList.add('shake');
    });
  }

  function revealRow(row, guess, result, onDone) {
    const delay = 300; // ms between tile flips
    guess.split('').forEach((letter, col) => {
      const tile = getTile(row, col);
      if (!tile) return;
      setTimeout(() => {
        tile.classList.add('reveal');
        // Apply color at flip midpoint
        setTimeout(() => {
          tile.classList.remove('filled');
          tile.classList.add(result[col]);
          tile.textContent = letter;
        }, 250);
        if (col === WORD_LEN - 1 && onDone) {
          setTimeout(onDone, 300);
        }
      }, col * delay);
    });
  }

  function bounceRow(row) {
    const delay = 100;
    for (let c = 0; c < WORD_LEN; c++) {
      const tile = getTile(row, c);
      if (!tile) continue;
      setTimeout(() => {
        tile.classList.add('bounce');
        tile.addEventListener('animationend', () => tile.classList.remove('bounce'), { once: true });
      }, c * delay);
    }
  }

  // ── Opponent board ─────────────────────────────────────────────────────────
  function updateOppBoard(allResults) {
    allResults.forEach((result, row) => {
      result.forEach((status, col) => {
        const tile = getOppTile(row, col);
        if (!tile) return;
        tile.className = `opp-tile ${status}`;
      });
    });
  }

  // ── Timer ──────────────────────────────────────────────────────────────────
  function startTimer(serverStartTime, duration) {
    const timerEl  = $('timer-display');
    const timerTxt = $('timer-text');
    if (!timerEl || !timerTxt) return;

    timerEl.style.display = 'flex';
    if (MODE === 'timed') timerEl.style.display = 'flex';

    state.timerInterval = setInterval(() => {
      const elapsed   = (Date.now() / 1000) - serverStartTime;
      const remaining = Math.max(0, duration - elapsed);
      const mins = Math.floor(remaining / 60);
      const secs = Math.floor(remaining % 60);
      timerTxt.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
      if (remaining <= 30) timerEl.classList.add('warning');
      if (remaining <= 0) {
        clearInterval(state.timerInterval);
        timerTxt.textContent = '0:00';
      }
    }, 500);
  }

  // ── Flash message ──────────────────────────────────────────────────────────
  let msgTimeout = null;
  function showMessage(text, duration = 1800) {
    let el = document.querySelector('.game-message');
    if (!el) {
      el = document.createElement('div');
      el.className = 'game-message';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.classList.add('show');
    clearTimeout(msgTimeout);
    msgTimeout = setTimeout(() => el.classList.remove('show'), duration);
  }

  // ── Result modal ───────────────────────────────────────────────────────────
  function showResult(data) {
    clearInterval(state.timerInterval);
    const { result, word, your_score, opponent_score, elo_change, opponent_guesses, opponent_results } = data;

    const emojis = { win: '🏆', loss: '💀', draw: '🤝' };
    const titles = { win: 'You Win!', loss: 'You Lose', draw: 'Draw!' };
    $('result-emoji').textContent = emojis[result] || '🎮';
    $('result-title').textContent = titles[result] || result;
    $('result-word').textContent  = `The word was: ${word}`;
    $('your-score').textContent   = your_score;
    $('opp-score').textContent    = opponent_score;

    const eloEl = $('elo-change-val');
    eloEl.textContent = (elo_change >= 0 ? '+' : '') + elo_change;
    eloEl.classList.toggle('negative', elo_change < 0);

    // Opponent's board reveal
    const revContainer = $('opp-board-reveal');
    revContainer.innerHTML = '';
    if (opponent_guesses && opponent_guesses.length > 0) {
      opponent_guesses.forEach((guess, ri) => {
        const row = document.createElement('div');
        row.className = 'opp-rev-row';
        guess.split('').forEach((letter, ci) => {
          const tile = document.createElement('div');
          const status = (opponent_results[ri] || [])[ci] || 'absent';
          tile.className = `opp-rev-tile ${status}`;
          tile.textContent = letter;
          row.appendChild(tile);
        });
        revContainer.appendChild(row);
      });
    }

    $('rematch-btn').href = `/game?mode=${MODE}`;
    $('result-modal').style.display = 'flex';
  }

  // ── Restore state after reconnect ─────────────────────────────────────────
  function restoreBoard(guesses, results) {
    guesses.forEach((guess, row) => {
      guess.split('').forEach((letter, col) => {
        const tile = getTile(row, col);
        if (!tile) return;
        tile.textContent = letter;
        tile.classList.add(results[row][col]);
      });
      updateKeyboard(guess, results[row]);
    });
    state.currentRow = guesses.length;
    state.currentCol = 0;
    state.currentGuess = [];
  }

  // ── Socket.IO ──────────────────────────────────────────────────────────────
  const socket = io();

  let botCountdownInterval = null;

  function startBotCountdown(seconds) {
    const msgEl       = $('bot-fallback-msg');
    const defaultEl   = $('default-wait-msg');
    const countdownEl = $('bot-countdown');
    if (!msgEl || !countdownEl) return;
    let remaining = seconds;
    countdownEl.textContent = remaining;
    defaultEl.style.display = 'none';
    msgEl.style.display     = 'block';
    botCountdownInterval = setInterval(() => {
      remaining--;
      countdownEl.textContent = Math.max(0, remaining);
      if (remaining <= 0) clearInterval(botCountdownInterval);
    }, 1000);
  }

  socket.on('connect', () => {
    socket.emit('join_queue', { mode: MODE });
  });

  socket.on('queue_joined', () => {
    // Start the bot-fallback countdown after 5s of waiting
    setTimeout(() => startBotCountdown(12), 5000);
  });

  socket.on('match_found', data => {
    clearInterval(botCountdownInterval);
    state.matchId       = data.match_id;
    state.opponent      = data.opponent;
    state.matchStartTime = data.start_time;
    state.duration      = data.duration;

    $('waiting-overlay').style.display = 'none';
    $('game-ui').style.display         = 'block';

    $('opponent-name').textContent  = data.opponent;
    $('opp-name-label').textContent = data.opponent;

    const badge = $('mode-badge');
    if (MODE === 'timed') {
      badge.textContent = 'Timed Mode';
      badge.classList.add('timed');
    } else {
      badge.textContent = 'Classic PvP';
    }

    buildBoard();
    buildOppBoard();
    buildKeyboard();

    if (data.duration) {
      startTimer(data.start_time, data.duration);
    }
  });

  socket.on('reconnected', data => {
    clearInterval(botCountdownInterval);
    state.matchId        = data.match_id;
    state.opponent       = data.opponent;
    state.matchStartTime = data.start_time;
    state.duration       = data.duration;

    $('waiting-overlay').style.display = 'none';
    $('game-ui').style.display         = 'block';
    $('opponent-name').textContent      = data.opponent;
    $('opp-name-label').textContent     = data.opponent;

    buildBoard();
    buildOppBoard();
    buildKeyboard();

    if (data.guesses && data.guesses.length) {
      restoreBoard(data.guesses, data.results);
    }
    if (data.opponent_results && data.opponent_results.length) {
      updateOppBoard(data.opponent_results);
    }
    if (data.duration) {
      startTimer(data.start_time, data.duration);
    }
  });

  socket.on('guess_result', data => {
    const { guess, result, guess_number, solved, game_over } = data;
    const row = guess_number - 1;

    revealRow(row, guess, result, () => {
      updateKeyboard(guess, result);
      if (solved) {
        bounceRow(row);
        showMessage('Brilliant!', 2500);
      }
      if (game_over) {
        state.done = true;
        if (!solved) showMessage(`The word was: ${data.word || ''}`, 3000);
      }
    });

    state.currentRow++;
    state.currentCol   = 0;
    state.currentGuess = [];
  });

  socket.on('invalid_guess', data => {
    shakeRow(state.currentRow);
    showMessage(data.message);
  });

  socket.on('opponent_progress', data => {
    const { guesses_made, solved, done, all_results } = data;
    if (all_results) updateOppBoard(all_results);

    const statusEl = $('opp-status');
    if (solved) {
      statusEl.textContent = `Solved in ${guesses_made} guess${guesses_made > 1 ? 'es' : ''}!`;
      statusEl.classList.add('solved');
    } else if (done) {
      statusEl.textContent = `Failed after ${guesses_made} guesses`;
    } else {
      statusEl.textContent = `Guess ${guesses_made} of 6…`;
    }
  });

  socket.on('game_over', data => {
    state.done = true;
    // Small delay so last row animation can finish
    setTimeout(() => showResult(data), 1800);
  });

  socket.on('error', data => {
    showMessage(data.message || 'An error occurred');
  });

  // ── Init: show waiting overlay immediately ─────────────────────────────────
  $('waiting-overlay').style.display = 'flex';
})();
