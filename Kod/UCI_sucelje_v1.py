import sys
import chess
import Stroj_0 as engine


def obradi_poziciju(dijelovi: list) -> chess.Board:

    if dijelovi[1] == "startpos":
        ploca = chess.Board()
        preostalo = dijelovi[2:]
    else:
        #dijelovi[1] == "fen", FEN zauzima iducih 6 polja
        fen = " ".join(dijelovi[2:8])
        ploca = chess.Board(fen)
        preostalo = dijelovi[8:]

    if preostalo and preostalo[0] == "moves":
        for uci_potez in preostalo[1:]:
            ploca.push_uci(uci_potez)

    return ploca


def glavna_petlja() -> None:

    ploca = chess.Board()
    engine.resetiraj_stanje() #Cisto stanje prije prve partije

    while True:
        linija = sys.stdin.readline()
        if not linija:
            break
        linija = linija.strip()
        if not linija:
            continue

        if linija == "uci":
            print("id name diplomski")
            print("id author Dominik")
            print("uciok")
            sys.stdout.flush()

        elif linija == "isready":
            print("readyok")
            sys.stdout.flush()

        elif linija == "ucinewgame":
            ploca = chess.Board()
            engine.resetiraj_stanje() #Bitno - sprjecava curenje TT/rosade iz prosle partije

        elif linija.startswith("position"):
            dijelovi = linija.split()
            ploca = obradi_poziciju(dijelovi)

        elif linija.startswith("go"):
            dijelovi_go = linija.split()

            if "movetime" in dijelovi_go:
                indeks = dijelovi_go.index("movetime")
                movetime_ms = int(dijelovi_go[indeks + 1])
                #Malo rezerve ispod stvarnog ogranicenja da izbjegnemo gubitak na vrijeme
                #zbog vremena potrebnog za samu UCI komunikaciju
                engine.MAX_VRIJEME_PRETRAZIVANJA = min(4.0, max(movetime_ms / 1000.0 - 0.5, 0.05))
            #Ako "movetime" nije poslan (npr. koristi se wtime/btime umjesto fiksnog
            #vremena po potezu), zadrzava se postojeca vrijednost MAX_VRIJEME_PRETRAZIVANJA

            potez = engine.vrati_najbolji_potez(ploca)
            print(f"bestmove {potez.uci()}")
            sys.stdout.flush()

        elif linija == "quit":
            break

        #Sve ostale UCI naredbe (npr. "stop", "setoption") se trenutno ignoriraju


if __name__ == "__main__":
    glavna_petlja()