"""
enhanced_voice_tictactoe.py

Requirements:
    pip install customtkinter speechrecognition pyttsx3 pyaudio

If pyaudio installation fails on Windows:
    pip install pipwin
    pipwin install pyaudio

Run:
    python enhanced_voice_tictactoe.py
"""

import customtkinter as ctk
import threading
import speech_recognition as sr
import pyttsx3
import random
import copy
from functools import partial

# ---------------- CONFIG ----------------
ctk.set_appearance_mode("dark")   # "light" or "dark" or "system"
ctk.set_default_color_theme("dark-blue")

# ---------------- CONSTANTS ----------------
EMPTY = ""
PLAYER_X = "X"
PLAYER_O = "O"
DIFFICULTIES = ["Easy", "Medium", "Hard"]

# ---------------- TTS (single engine) ----------------
_tts_engine = pyttsx3.init()
_tts_engine.setProperty("rate", 160)

def speak(text):
    try:
        _tts_engine.say(text)
        _tts_engine.runAndWait()
    except Exception as e:
        print("TTS error:", e)

# ---------------- VOICE (recognizer shared) ----------------
_recognizer = sr.Recognizer()

# ---------- Helper: parse common move phrases ----------
word_to_num = {
    "one":1,"1":1,"two":2,"2":2,"three":3,"3":3,
    "first":1,"second":2,"third":3
}
pos_keywords = {
    "top left":0,"top middle":1,"top center":1,"top right":2,
    "middle left":3,"center left":3,"centre left":3,
    "center":4,"centre":4,"middle":4,"mid":4,
    "middle right":5,"center right":5,"centre right":5,
    "bottom left":6,"bottom middle":7,"bottom center":7,"bottom right":8,
    "a1":0,"a2":1,"a3":2,"b1":3,"b2":4,"b3":5,"c1":6,"c2":7,"c3":8
}

def parse_move_from_text(text):
    """
    Parse index 0..8 from spoken text like:
      - "top left", "center", "bottom right"
      - "row one column two", "one one", "1 2"
      - "A1", "B3"
    Returns integer 0..8 or None.
    """
    if not text:
        return None
    text = text.lower().replace("-", " ").replace(",", " ").strip()
    # direct keyword match
    for key, idx in pos_keywords.items():
        if key in text:
            return idx

    tokens = text.split()
    # row/col pattern
    if "row" in tokens or "column" in tokens or "col" in tokens:
        row = col = None
        for i, tok in enumerate(tokens):
            if tok == "row" and i+1 < len(tokens):
                row = word_to_num.get(tokens[i+1], None)
            if (tok == "column" or tok == "col") and i+1 < len(tokens):
                col = word_to_num.get(tokens[i+1], None)
        if row and col:
            return (row-1)*3 + (col-1)

    # look for two numbers or words
    conv = []
    for t in tokens:
        if t.isdigit():
            conv.append(int(t))
        elif t in word_to_num:
            conv.append(word_to_num[t])
    if len(conv) >= 2:
        r, c = conv[0], conv[1]
        if 1 <= r <= 3 and 1 <= c <= 3:
            return (r-1)*3 + (c-1)

    # A1 style token
    for t in tokens:
        clean = ''.join(ch for ch in t if ch.isalnum())
        if len(clean) == 2 and clean[0].isalpha() and clean[1].isdigit():
            col_letter = clean[0].lower()
            row_num = int(clean[1])
            col_map = {'a':1, 'b':2, 'c':3}
            if col_letter in col_map and 1 <= row_num <= 3:
                r = row_num; c = col_map[col_letter]
                return (r-1)*3 + (c-1)
    return None

# ---------------- GAME LOGIC ----------------
def check_winner(board):
    wins = [
        (0,1,2),(3,4,5),(6,7,8),
        (0,3,6),(1,4,7),(2,5,8),
        (0,4,8),(2,4,6)
    ]
    for a,b,c in wins:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    if all(cell != EMPTY for cell in board):
        return "Draw"
    return None

def available_moves(board):
    return [i for i, v in enumerate(board) if v == EMPTY]

# Minimax for Hard difficulty (AI maximizes for ai_mark)
def minimax(board, ai_mark, current_mark):
    winner = check_winner(board)
    if winner == ai_mark:
        return {'score': 1}
    elif winner == "Draw":
        return {'score': 0}
    elif winner is not None:
        return {'score': -1}

    moves = []
    for idx in available_moves(board):
        board[idx] = current_mark
        result = minimax(board, ai_mark, PLAYER_O if current_mark == PLAYER_X else PLAYER_X)
        moves.append({'index': idx, 'score': result['score']})
        board[idx] = EMPTY

    # choose max for ai_mark, choose min for opponent
    if current_mark == ai_mark:
        best = max(moves, key=lambda m: m['score'])
    else:
        best = min(moves, key=lambda m: m['score'])
    return best

def best_move_for_ai(board, ai_mark, difficulty):
    moves = available_moves(board)
    if not moves:
        return None
    # Easy: random
    if difficulty == "Easy":
        return random.choice(moves)
    # Medium: try win, then block, else random
    if difficulty == "Medium":
        # try to win
        for i in moves:
            tmp = board[:]; tmp[i] = ai_mark
            if check_winner(tmp) == ai_mark:
                return i
        # try to block opponent
        opponent = PLAYER_X if ai_mark == PLAYER_O else PLAYER_O
        for i in moves:
            tmp = board[:]; tmp[i] = opponent
            if check_winner(tmp) == opponent:
                return i
        return random.choice(moves)
    # Hard: minimax
    result = minimax(board, ai_mark, ai_mark)
    return result.get('index', random.choice(moves))

# ---------------- GUI ----------------
class EnhancedTicTacToe(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Enhanced Voice Tic-Tac-Toe")
        self.geometry("540x700")
        self.resizable(False, False)

        # game state
        self.board = [EMPTY]*9
        self.current_player = PLAYER_X
        self.game_mode = None   # "PVP" or "PVC"
        self.difficulty = "Easy"
        self.human_mark = PLAYER_X
        self.ai_mark = PLAYER_O

        # voice flags
        self.listening = False
        self.voice_thread = None

        self._create_main_menu()

    # ---------- Main menu ----------
    def _create_main_menu(self):
        for w in self.winfo_children():
            w.destroy()

        header = ctk.CTkLabel(self, text="🎯 Tic-Tac-Toe", font=ctk.CTkFont(size=28, weight="bold"))
        header.pack(pady=(28,6))

        subtitle = ctk.CTkLabel(self, text="Voice + Click — Choose a mode", font=ctk.CTkFont(size=13))
        subtitle.pack(pady=(0,18))

        btn_pvp = ctk.CTkButton(self, text="👥 Player vs Player",
                                width=300, height=48,
                                fg_color=("#3B82F6","#1E3A8A"),
                                command=lambda: self._choose_symbol("PVP"))
        btn_pvp.pack(pady=8)

        btn_pvc = ctk.CTkButton(self, text="🤖 Player vs Computer",
                                width=300, height=48,
                                fg_color=("#10B981","#047857"),
                                command=lambda: self._choose_difficulty())
        btn_pvc.pack(pady=8)

        btn_exit = ctk.CTkButton(self, text="Exit", width=200,
                                 fg_color=("#EF4444","#B91C1C"),
                                 command=self.destroy)
        btn_exit.pack(pady=(18,6))

        footer = ctk.CTkLabel(self, text="Tip: Use the 'Voice Move' button to speak moves\nTry phrases like 'top left', 'row one column two', 'A3', or 'center'.",
                              font=ctk.CTkFont(size=11), text_color="#94A3B8")
        footer.pack(pady=(24,6))

    # ---------- Choose difficulty (PVC) ----------
    def _choose_difficulty(self):
        for w in self.winfo_children():
            w.destroy()

        title = ctk.CTkLabel(self, text="Select Difficulty", font=ctk.CTkFont(size=22, weight="bold"))
        title.pack(pady=(28,8))

        for diff in DIFFICULTIES:
            btn = ctk.CTkButton(self, text=diff, width=260, height=46,
                                fg_color=("#06B6D4","#0891B2"),
                                command=lambda d=diff: self._choose_symbol("PVC", d))
            btn.pack(pady=8)

        back = ctk.CTkButton(self, text="← Back", width=160, command=self._create_main_menu)
        back.pack(pady=(22,6))

    # ---------- Choose symbol X/O ----------
    def _choose_symbol(self, mode, difficulty=None):
        for w in self.winfo_children():
            w.destroy()

        self.game_mode = mode
        if difficulty:
            self.difficulty = difficulty

        title = ctk.CTkLabel(self, text="Choose Your Symbol", font=ctk.CTkFont(size=22, weight="bold"))
        title.pack(pady=(28,8))

        btn_x = ctk.CTkButton(self, text="Play as X", width=240, height=46,
                              fg_color=("#F97316","#C2410C"),
                              command=lambda: self._start_game(player_symbol=PLAYER_X))
        btn_x.pack(pady=10)

        btn_o = ctk.CTkButton(self, text="Play as O", width=240, height=46,
                              fg_color=("#3B82F6","#1E40AF"),
                              command=lambda: self._start_game(player_symbol=PLAYER_O))
        btn_o.pack(pady=10)

        back = ctk.CTkButton(self, text="← Back", width=160, command=self._create_main_menu)
        back.pack(pady=(22,6))

    # ---------- Start game screen ----------
    def _start_game(self, player_symbol=PLAYER_X):
        for w in self.winfo_children():
            w.destroy()

        # set marks based on player's choice
        self.human_mark = player_symbol
        self.ai_mark = PLAYER_O if self.human_mark == PLAYER_X else PLAYER_X

        # reset board
        self.board = [EMPTY]*9
        self.current_player = PLAYER_X  # X always considered current marker in alternating order

        # top status
        top = ctk.CTkFrame(self, fg_color=("#0f172a","#071133"), corner_radius=12)
        top.pack(fill="x", padx=18, pady=(18,6))
        status_text = f"Mode: {'Player vs Computer' if self.game_mode == 'PVC' else 'Player vs Player'} | You: {self.human_mark} | Difficulty: {self.difficulty if self.game_mode=='PVC' else '—'}"
        self.status_label = ctk.CTkLabel(top, text=status_text, anchor="w", font=ctk.CTkFont(size=12))
        self.status_label.pack(padx=12, pady=12)

        # board frame
        board_frame = ctk.CTkFrame(self, fg_color=("#020617","#000814"), corner_radius=14)
        board_frame.pack(padx=18, pady=18)

        # create grid of buttons
        self.cell_buttons = []
        btn_size = 130
        for i in range(9):
            btn = ctk.CTkButton(board_frame, text="", width=btn_size, height=btn_size,
                                fg_color=("#0b1220","#071226"), hover_color=("#0ea5a4","#075b53"),
                                font=ctk.CTkFont(size=36, weight="bold"),
                                command=partial(self._on_cell_clicked, i))
            btn.grid(row=i//3, column=i%3, padx=8, pady=8)
            self.cell_buttons.append(btn)

        # bottom controls
        ctrl_frame = ctk.CTkFrame(self, fg_color=("#020617","#000814"), corner_radius=12)
        ctrl_frame.pack(fill="x", padx=18, pady=(6,18))

        voice_btn = ctk.CTkButton(ctrl_frame, text="🎙 Voice Move", width=160, command=self._start_listening)
        voice_btn.pack(side="left", padx=(12,8), pady=12)

        reset_btn = ctk.CTkButton(ctrl_frame, text="🔁 Reset", width=120, command=self._reset_game)
        reset_btn.pack(side="left", padx=8, pady=12)

        menu_btn = ctk.CTkButton(ctrl_frame, text="🏠 Menu", width=120, command=self._create_main_menu)
        menu_btn.pack(side="right", padx=12, pady=12)

        # if PVC and AI should go first (AI is X and human chose O), let AI move
        if self.game_mode == "PVC" and self.ai_mark == PLAYER_X:
            self.after(500, self._ai_make_move)

        # announce start
        speak(f"Game started. You are {self.human_mark}. {self.difficulty} difficulty." if self.game_mode == "PVC" else f"Two player mode started. {self.human_mark} plays first.")
        self._refresh_status()

    # ---------- UI helpers ----------
    def _refresh_status(self, extra_msg=""):
        winner = check_winner(self.board)
        if winner == "Draw":
            status = "Result: Draw"
        elif winner:
            status = f"Result: {winner} wins!"
        else:
            status = f"Turn: {self.current_player}"
            if self.game_mode == "PVC":
                if self.current_player == self.human_mark:
                    status += " (Your turn)"
                else:
                    status += " (Computer's turn)"
        if extra_msg:
            status += " — " + extra_msg
        self.status_label.configure(text=status)

    def _update_button_visual(self, idx):
        val = self.board[idx]
        if val == EMPTY:
            self.cell_buttons[idx].configure(text="", fg_color="transparent")
        else:
            # color per mark
            color = ("#FB923C" if val == PLAYER_X else "#60A5FA")
            self.cell_buttons[idx].configure(text=val, fg_color=color)

    # ---------- Player actions ----------
    def _on_cell_clicked(self, index):
        winner = check_winner(self.board)
        if winner:
            speak("Game is over. Reset to play again.")
            return
        if self.board[index] != EMPTY:
            speak("Cell already occupied.")
            return
        # if PVC ensure it's human's turn
        if self.game_mode == "PVC" and self.current_player != self.human_mark:
            speak("It's not your turn.")
            return

        self._place_mark(index, self.current_player)
        self._after_move_actions()

    def _place_mark(self, index, mark):
        self.board[index] = mark
        self._update_button_visual(index)

    def _after_move_actions(self):
        winner = check_winner(self.board)
        if winner:
            if winner == "Draw":
                speak("It's a draw.")
            else:
                speak(f"{winner} wins.")
            self._refresh_status()
            return

        # switch current player
        self.current_player = PLAYER_O if self.current_player == PLAYER_X else PLAYER_X
        self._refresh_status()

        # if PVC and it's AI's turn, schedule AI move
        if self.game_mode == "PVC" and self.current_player == self.ai_mark:
            self.after(450, self._ai_make_move)

    # ---------- AI ----------
    def _ai_make_move(self):
        move = best_move_for_ai(self.board, self.ai_mark, self.difficulty)
        if move is not None:
            self._place_mark(move, self.ai_mark)
        self._after_move_actions()

    # ---------- Reset ----------
    def _reset_game(self):
        self.board = [EMPTY]*9
        self.current_player = PLAYER_X
        for i in range(9):
            self.cell_buttons[i].configure(text="", fg_color="transparent")
        self._refresh_status()
        speak("Board reset.")

    # ---------- Voice listening (non-blocking) ----------
    def _start_listening(self):
        if self.listening:
            speak("Already listening.")
            return
        self.listening = True
        self.voice_thread = threading.Thread(target=self._listen_worker, daemon=True)
        self.voice_thread.start()
        self._refresh_status("Listening...")

    def _listen_worker(self):
        # Uses the shared recognizer
        try:
            with sr.Microphone() as source:
                _recognizer.adjust_for_ambient_noise(source, duration=0.6)
                speak("Listening for your move. Speak now.")
                try:
                    audio = _recognizer.listen(source, timeout=5, phrase_time_limit=5)
                except sr.WaitTimeoutError:
                    self._listening_done("Timed out. Try again.")
                    return
        except Exception as e:
            print("Microphone error:", e)
            self._listening_done("Microphone error.")
            return

        try:
            transcript = _recognizer.recognize_google(audio)
            print("Transcript:", transcript)
        except sr.UnknownValueError:
            self._listening_done("I didn't understand. Try again.")
            return
        except sr.RequestError as e:
            print("Speech API error:", e)
            self._listening_done("Speech recognition service error.")
            return

        # parse move
        idx = parse_move_from_text(transcript)
        if idx is None:
            # also try single digit in transcript
            tokens = transcript.split()
            found = None
            for t in tokens:
                if t.isdigit():
                    v = int(t)
                    if 1 <= v <= 9:
                        found = v - 1
                        break
            idx = found

        if idx is None:
            self._listening_done("Could not parse move. Try again.")
            return

        # validate and place
        if check_winner(self.board):
            self._listening_done("Game over. Reset to play again.")
            return
        if self.board[idx] != EMPTY:
            self._listening_done("That cell is occupied. Try another move.")
            return
        if self.game_mode == "PVC" and self.current_player != self.human_mark:
            self._listening_done("It's not your turn.")
            return

        # Place mark on main UI thread
        self.after(0, lambda: self._place_mark(idx, self.current_player))
        self.after(0, self._after_move_actions)
        self._listening_done("Move placed.")

    def _listening_done(self, msg):
        speak(msg)
        self.listening = False
        self._refresh_status(msg)

# ---------------- Run ----------------
if __name__ == "__main__":
    app = EnhancedTicTacToe()
    app.mainloop()
