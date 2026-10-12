
import chess
import chess.polyglot
import sys
import random
import atexit


class PolyglotBook:
    def __init__(self, path):
        self.path = path
        self.reader = None

    def __enter__(self):
        self.reader = chess.polyglot.open_reader(str(self.path))
        atexit.register(self.zatvori_knjigu)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.reader:
            self.reader.close()

    def zatvori_knjigu(self) -> None:
        if self.reader:
            self.reader.close()
            self.reader = None

    def odaberi_nasumicni_potez(self, ploca: chess.Board) -> chess.Move | None:
        if not self.reader:
            return None

        try:
            #Potezi s težinom 0 se po Polyglot konvenciji ne igraju
            unosi = [e for e in self.reader.find_all(ploca) if e.weight > 0]
        except Exception as greska:
            print(f"Greška pri čitanju knjige otvaranja: {greska}", file=sys.stderr)
            return None

        if not unosi:
            return None

        return random.choices(unosi, weights=[e.weight for e in unosi])[0].move