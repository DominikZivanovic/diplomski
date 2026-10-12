import tkinter as tk
from tkinter import messagebox
import chess
from Stroj_0 import vrati_najbolji_potez
from PIL import Image, ImageTk
import random



SQUARE_SIZE = 64
BOARD_COLOR_1 = "#FFCD95"
BOARD_COLOR_2 = "#8E430A"
LAST_MOVE_COLOR_1 = "#FFF025"

class ChessGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Chess")

        self.board = chess.Board()
        self.player_color = random.choice([chess.WHITE, chess.BLACK])
        self.selected_square = None
        self.last_move = None

        self.PIECE_SCALE = 0.8
        self.img_size = int(SQUARE_SIZE * self.PIECE_SCALE)
        self.piece_images = {}
        for name in ["wP","wN","wB","wR","wQ","wK","bP","bN","bB","bR","bQ","bK"]:
            img = Image.open(f"../Slike figura/{name}.png")
            img = img.resize((self.img_size, self.img_size))
            self.piece_images[name] = ImageTk.PhotoImage(img)

        self.canvas = tk.Canvas(root, width=8*SQUARE_SIZE, height=8*SQUARE_SIZE)
        self.canvas.pack()

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.undo_button = tk.Button(root, text="Undo", command=self.undo_move)
        self.undo_button.pack()

        self.dragging_piece = None
        self.drag_start_square = None
        self.drag_item = None

        self.draw_board()
        if self.board.turn != self.player_color:
            self.root.after(100, self.computer_move)

    #Funkcija vraća (file, rank) za crtanje na ekranu
    def polje_do_prikaza(self, polje):
        file = chess.square_file(polje)
        rank = chess.square_rank(polje)
        if self.player_color == chess.WHITE:
            return file, 7-rank
        else:
            return 7-file, rank

    #Funkcija vraća chess.Square iz koordinata klika, ovisno o boji igrača
    def polje_sa_ekrana(self, x, y):
        file = x // SQUARE_SIZE
        rank = y // SQUARE_SIZE
        if self.player_color == chess.WHITE:
            return chess.square(file, 7-rank)
        else:
            return chess.square(7-file, rank)


    # ================= CRTANJE PLOČE =================
    def draw_board(self):
        self.canvas.delete("all")

        for rank in range(8):
            for file in range(8):
                x1 = file * SQUARE_SIZE
                y1 = rank * SQUARE_SIZE
                x2 = x1 + SQUARE_SIZE
                y2 = y1 + SQUARE_SIZE

                color = BOARD_COLOR_1 if (rank + file) % 2 == 0 else BOARD_COLOR_2
                square = self.polje_sa_ekrana(x1, y1)

                if self.last_move != None and square in (self.last_move.from_square, self.last_move.to_square):
                    color = LAST_MOVE_COLOR_1

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color)
                piece = self.board.piece_at(square)

                if piece:
                    image_name = (("w" if piece.color == chess.WHITE else "b") + piece.symbol().upper())
                    offset = (SQUARE_SIZE - self.img_size) // 2

                    self.canvas.create_image(x1 + offset,y1 + offset,image=self.piece_images[image_name],anchor="nw")

    # ================= GAME OVER ================= 
    def check_game_over(self):
        if not self.board.is_game_over():
            return False
        result = self.board.result()

        if result == "1-0":
            message = "White wins!"
        elif result == "0-1":
            message = "Black wins!"
        else: message = "Draw!"

        if self.board.is_checkmate():
            message += "\nCheckmate."
        elif self.board.is_stalemate():
            message += "\nStalemate."
        elif self.board.is_insufficient_material():
            message += "\nInsufficient material."
        elif self.board.is_fifty_moves():
            message += "\nFifty-move rule."
        elif self.board.is_fivefold_repetition():
            message += "\nFivefold repetition."

        messagebox.showinfo("Game Over", message)

        return True

    # ================= CLICK & DRAG HANDLER =================
    def on_click(self, event):
        square = self.polje_sa_ekrana(event.x, event.y)
        if self.selected_square is None:
            piece = self.board.piece_at(square)
            if piece and piece.color == self.board.turn and self.board.turn == self.player_color:
                self.selected_square = square
        else:
            move = chess.Move(self.selected_square, square)

            if move in self.board.legal_moves:
                self.board.push(move)
                self.last_move = move
                self.selected_square = None
                self.draw_board()
                self.root.update()

                if not self.board.is_game_over():
                    self.computer_move()
            else:
                self.selected_square = None

        self.draw_board()

    def on_press(self, event):
        square = self.polje_sa_ekrana(event.x, event.y)
        piece = self.board.piece_at(square)

        if piece and piece.color == self.board.turn and self.board.turn == self.player_color:
            self.dragging_piece = piece
            self.drag_start_square = square

            image_name = (("w" if piece.color == chess.WHITE else "b") + piece.symbol().upper())
            self.drag_item = self.canvas.create_image(event.x,event.y,image=self.piece_images[image_name],tags="drag")
        
        self.legal_targets = [
        move.to_square
        for move in self.board.legal_moves
        if move.from_square == square
        ]

    def on_drag(self, event):
        if self.drag_item:
            self.canvas.coords(self.drag_item, event.x, event.y)


    def on_release(self, event):
        if self.drag_start_square is None:
            return

        target_square = self.polje_sa_ekrana(event.x, event.y)
        piece = self.board.piece_at(self.drag_start_square)

        move = chess.Move(self.drag_start_square, target_square)

        #Za promocije
        if piece and piece.piece_type == chess.PAWN:
            if chess.square_rank(target_square) in (0, 7):
                promo = self.ask_promotion_piece(piece.color)
                move = chess.Move(
                    self.drag_start_square,
                    target_square,
                    promotion=promo
                )

        #Brisanje slike pomaknute figure s početnog polja
        if self.drag_item:
            self.canvas.delete(self.drag_item)

        self.drag_item = None

        if move in self.board.legal_moves:
            self.board.push(move)
            self.last_move = move
            self.draw_board()
            self.root.update()

            if self.check_game_over():
                self.drag_start_square = None
                self.dragging_piece = None
                return

            self.computer_move()

        self.drag_start_square = None
        self.dragging_piece = None

        self.draw_board()


    def ask_promotion_piece(self, color):
        popup = tk.Toplevel(self.root)
        popup.title("Choose promotion")
        popup.resizable(False, False)
        popup.grab_set()

        choice = {"piece": None}

        pieces = ["Q", "R", "B", "N"]

        def select(p):
            choice["piece"] = p
            popup.destroy()

        for i, p in enumerate(pieces):
            name = ("w" if color == chess.WHITE else "b") + p

            btn = tk.Button(
                popup,
                image=self.piece_images[name],
                command=lambda p=p: select(p)
            )
            btn.grid(row=0, column=i)

        self.root.wait_window(popup)

        mapping = {
            "Q": chess.QUEEN,
            "R": chess.ROOK,
            "B": chess.BISHOP,
            "N": chess.KNIGHT
        }

        piece = choice.get("piece")
        if piece is None:
            return chess.QUEEN

        return mapping.get(piece, chess.QUEEN)

    # ================= COMPUTER =================
    def computer_move(self):
        move = self.get_best_move()
        if move:
            self.board.push(move)
            self.last_move = move
            self.draw_board()

        self.check_game_over()

    def get_best_move(self):
        return vrati_najbolji_potez(self.board)

    # ================= UNDO =================
    def undo_move(self):
        if len(self.board.move_stack) >= 2:
            self.board.pop()
            self.board.pop()
        elif len(self.board.move_stack) == 1:
            self.board.pop()

        self.last_move = self.board.peek() if self.board.move_stack else None

        self.draw_board()


# ================= RUN =================
if __name__ == "__main__":
    root = tk.Tk()
    app = ChessGUI(root)
    root.mainloop()