import chess #Za generiranje legalnih poteza, uzimanja figure itd.
import chess.polyglot #Za generiranje ključa pozicije (zobrist hash)
from Polyglot import PolyglotBook #Za otvaranja; PolyglotBook klasa iz PolyGlot.py
import time
import sys
from Figura_polje_tablice import PIJUN_KONTROLA_CENTRA, PIJUN_RANG_BONUS, LOVAC_MOBILNOST #Za evaluaciju figura
#from Figura_polje_tablice import SKAKAC_MOBILNOST_20X ako ćemo htjeti koristiti mobilnost skakača koja ne ovisi o poziciji
from operator import add #Za zbrajanje tablica u evaluaciji figura
from Stacionarna_distribucija_skakaca import markovljeva_mobilnost_skakaca, postavi_vrijednosti_figura #Za evaluaciju figura

#TRANSPOZICIJSKE TABLICE
transpozicijska_tablica = {} #Rječnik koji mapira FEN stringove na tuple (evaluacija, dubina pretraživanja, najbolji potez)
TT_egzaktna = 0
TT_alfa = 1
TT_beta = 2
broj_cvorova = 0
broj_TT_pogodaka = 0
killer_potezi = {} #Rječnik poteza koji uzrokuju beta_odsijecanje, tzv. killer poteza

#GLOBALNE KONSTANTE
#Otvaranja
OTVARANJA_PATH = "C:/Users/domi1/Desktop/DIPLOMSKI/Otvaranja/Perfect2023.bin"
MAX_OTVARAJUCIH_POTEZA = 8
#Pretraživanje
MAX_VRIJEME_PRETRAZIVANJA = 3 #U sekundama
BROJ_NAJBOLJIH_POTEZA = 5 #Koliko najboljih poteza istražujemo dublje na svakoj dubini pretraživanja
SMANJENJE_NEBITNIH_POTEZA = 2 #Koliko duboko smanjujemo pretraživanje za poteze koji nisu među najboljima
MIN_DUBINA_SELEKTIVNOG_PRODUBLJIVANJA = 2
class vrijeme_isteklo(Exception):
    pass
#Bonusi i kazne
DVOSTRUKI_PIJUNI_KAZNA = 40
IZOLIRANI_PIJUN_KAZNA = 35
NAPREDNI_PIJUN_BONUS = 30
PAR_LOVACA_BONUS = 50
ROSADA_BONUS = 70
PIJUN_PRED_KRALJEM_BONUS = 30 #pojedinačni bonus
IZGUBLJENA_ROSADA_KAZNA = 40

#KNJIGE OTVARANJA I ZAVRŠNICA
book = PolyglotBook(OTVARANJA_PATH)
book.__enter__() #Inicijalizacija knjige otvaranja



#####################################################################################################
####################################### VRIJEDNOST FIGURA ###########################################
#####################################################################################################

pocetne_vrijednosti_figura = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 10000
}
postavi_vrijednosti_figura(pocetne_vrijednosti_figura)


#PIJUNI (alfa*kontrola_centra + beta*rang_nagrada)
ALFA_PIJUN = 8 #Kontrola centra
BETA_PIJUN = 3 #Nagrada za rang
bonus_pijuna = list(map(add, [x*ALFA_PIJUN for x in PIJUN_KONTROLA_CENTRA], [x*BETA_PIJUN for x in PIJUN_RANG_BONUS]))


#SKAKAČI (alfa*mobilnost)
ALFA_SKAKAC = 0.15 #Mobilnost ovisna o poziciji (stacionarna distribucija)
KAZNA_SKAKACA_ZAVRSNICA = 20 #Skakač gubi vrijednost tijekom igre


#LOVCI (alfa*mobilnost + beta*dobar_lovac)
ALFA_LOVAC = 5 #Mobilnost
BETA_LOVAC = 15 #Dobar lovac
BONUS_LOVCA_ZAVRSNICA = 20 #Lovac dobiva na vrijednosti tijekom igre
bonus_lovca = list(LOVAC_MOBILNOST)


def mobilnost_lovca(ploca: chess.Board, polje: chess.Square, figura: chess.Piece) -> int:
    napadnuta_polja = ploca.attacks_mask(polje)
    vlastite_figure = ploca.occupied_co[figura.color]
    return chess.popcount(napadnuta_polja & ~vlastite_figure & chess.BB_ALL)


def dobar_lovac(polje: chess.Square, vlastiti_pijuni) -> int:
    boja_polja_lovca = (chess.square_rank(polje) + chess.square_file(polje)) % 2 #0 za bijelo polje, 1 za crno polje
    broj_pijuna_na_istoj_boji = 0
    for polje2 in vlastiti_pijuni:
        if (chess.square_rank(polje2) + chess.square_file(polje2)) % 2 == boja_polja_lovca:
            broj_pijuna_na_istoj_boji += 1

    return -broj_pijuna_na_istoj_boji


def par_lovaca(ploca: chess.Board, boja: chess.Color) -> bool:
    return len(ploca.pieces(chess.BISHOP, boja)) >= 2


#TOPOVI
TOP_OTVORENI_STUPAC_BONUS = 40
TOP_POLUOTVORENI_STUPAC_BONUS = 20
TOP_SEDMI_RED_BONUS = 30
POVEZANI_TOPOVI_BONUS = 20


def stupci_s_pijunima(pijuni) -> set:
    return {chess.square_file(p) for p in pijuni}


def ocijeni_topov_stupac(polje: chess.Square, vlastiti_stupci: set, protivnicki_stupci: set) -> float:
    stupac = chess.square_file(polje)
    ima_vlastiti_pijun = stupac in vlastiti_stupci
    ima_protivnicki_pijun = stupac in protivnicki_stupci

    if not ima_vlastiti_pijun and not ima_protivnicki_pijun:
        return TOP_OTVORENI_STUPAC_BONUS
    elif not ima_vlastiti_pijun and ima_protivnicki_pijun:
        return TOP_POLUOTVORENI_STUPAC_BONUS
    elif ima_vlastiti_pijun and not ima_protivnicki_pijun:
        return TOP_POLUOTVORENI_STUPAC_BONUS
    else:
        return 0


def top_na_sedmom_redu(ploca: chess.Board, polje: chess.Square, boja: chess.Color) -> bool:
    red = chess.square_rank(polje)
    return red == 6 if boja == chess.WHITE else red == 1


def topovi_povezani(ploca: chess.Board, boja: chess.Color) -> bool:
    topovi = list(ploca.pieces(chess.ROOK, boja))
    if len(topovi) != 2:
        return False

    a, b = topovi
    if chess.square_rank(a) != chess.square_rank(b):
        return False

    red = chess.square_rank(a)
    niski_stupac, visoki_stupac = sorted([chess.square_file(a), chess.square_file(b)])

    #Provjeravamo ima li ijedna figura između dva topa na istom redu
    for stupac in range(niski_stupac+1, visoki_stupac):
        if ploca.piece_at(chess.square(stupac, red)) != None:
            return False

    return True


#KRALJICA
ALFA_KRALJICA = 5 #Mobilnost
KAZNA_ZA_RANO_POMICANJE = 20
BROJ_POTEZA_DO_KRAJA_KAZNE = 6 #Nakon ovoliko poteza KAZNA_ZA_RANO_POMICANJE postaje nula.


def mobilnost_kraljice(ploca: chess.Board, polje: chess.Square, figura: chess.Piece) -> int:
    napadnuta_polja = ploca.attacks_mask(polje)
    vlastite_figure = ploca.occupied_co[figura.color]
    return chess.popcount(napadnuta_polja & ~vlastite_figure & chess.BB_ALL)


def rani_izlazak_kraljice(ploca: chess.Board, polje: chess.Square, boja: chess.Color) -> bool:
    if ploca.fullmove_number > BROJ_POTEZA_DO_KRAJA_KAZNE:
        return False
    pocetno_polje = chess.D1 if boja == chess.WHITE else chess.D8
    return polje != pocetno_polje


#KRALJ
napravio_rosadu = {chess.WHITE: False, chess.BLACK: False} #Prati jesu li igrači napravili rošadu
AKTIVNOST_KRALJA = 15
DOPRINOS_KRAJU_PARTIJE = {chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4} #Proizvoljno
BROJ_FIGURA_NA_POCETKU = {chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}
max_udaljenost_od_kraja = sum(DOPRINOS_KRAJU_PARTIJE[figura] * BROJ_FIGURA_NA_POCETKU[figura] for figura in DOPRINOS_KRAJU_PARTIJE) * 2


def izgleda_rokirano(ploca: chess.Board, boja: chess.Color) -> bool:
    if boja == chess.WHITE:
        return not ploca.has_castling_rights(chess.WHITE) and ploca.king(chess.WHITE) in (chess.G1, chess.C1)
    else:
        return not ploca.has_castling_rights(chess.BLACK) and ploca.king(chess.BLACK) in (chess.G8, chess.C8)


def kljuc_pozicije(ploca: chess.Board) -> tuple:
    return (chess.polyglot.zobrist_hash(ploca), napravio_rosadu[chess.WHITE], napravio_rosadu[chess.BLACK])


def odigraj_potez(ploca: chess.Board, potez: chess.Move) -> bool:
    global napravio_rosadu
    je_rosada = ploca.is_castling(potez)
    boja = ploca.turn
    ploca.push(potez)
    if je_rosada:
        napravio_rosadu[boja] = True
    return je_rosada


def ponisti_potez(ploca: chess.Board, je_rosada: bool) -> None:
    global napravio_rosadu
    boja = not ploca.turn
    ploca.pop()
    if je_rosada:
        napravio_rosadu[boja] = False


def sigurnost_kralja(ploca: chess.Board) -> float:
    
    prednost = 0
    bijeli_pijuni = ploca.pawns & ploca.occupied_co[chess.WHITE]
    crni_pijuni = ploca.pawns & ploca.occupied_co[chess.BLACK]

    #Bijeli
    if napravio_rosadu[chess.WHITE]:
        prednost += ROSADA_BONUS
        kraljevo_polje = ploca.king(chess.WHITE)
        if kraljevo_polje == chess.G1:
            pijuni_pred_kraljem = chess.BB_SQUARES[chess.F2] | chess.BB_SQUARES[chess.G2] | chess.BB_SQUARES[chess.H2]
            prednost += PIJUN_PRED_KRALJEM_BONUS * chess.popcount(bijeli_pijuni & pijuni_pred_kraljem)
        elif kraljevo_polje == chess.C1:
            pijuni_pred_kraljem = chess.BB_SQUARES[chess.A2] | chess.BB_SQUARES[chess.B2] | chess.BB_SQUARES[chess.C2]
            prednost += PIJUN_PRED_KRALJEM_BONUS * chess.popcount(bijeli_pijuni & pijuni_pred_kraljem)
    elif not ploca.has_castling_rights(chess.WHITE):
        prednost -= IZGUBLJENA_ROSADA_KAZNA

    #Crni
    if napravio_rosadu[chess.BLACK]:
        prednost -= ROSADA_BONUS
        kraljevo_polje = ploca.king(chess.BLACK)
        if kraljevo_polje == chess.G8:
            pijuni_pred_kraljem = chess.BB_SQUARES[chess.F7] | chess.BB_SQUARES[chess.G7] | chess.BB_SQUARES[chess.H7]
            prednost -= PIJUN_PRED_KRALJEM_BONUS * chess.popcount(crni_pijuni & pijuni_pred_kraljem)
        elif kraljevo_polje == chess.C8:
            pijuni_pred_kraljem = chess.BB_SQUARES[chess.A7] | chess.BB_SQUARES[chess.B7] | chess.BB_SQUARES[chess.C7]
            prednost -= PIJUN_PRED_KRALJEM_BONUS * chess.popcount(crni_pijuni & pijuni_pred_kraljem)
    elif not ploca.has_castling_rights(chess.BLACK):
        prednost += IZGUBLJENA_ROSADA_KAZNA

    return prednost


def udaljenost_od_kraja_partije(mapa_figura: dict) -> float:
    udaljenost_od_kraja = 0
    for figura in mapa_figura.values():
        udaljenost_od_kraja += DOPRINOS_KRAJU_PARTIJE.get(figura.piece_type, 0)
    udaljenost_od_kraja = min(udaljenost_od_kraja, max_udaljenost_od_kraja)

    return udaljenost_od_kraja/max_udaljenost_od_kraja #0 za kraj partije, 1 za početak partije


def udaljenost_od_centra(polje: chess.Square) -> float:
    return max(abs(chess.square_file(polje) - 3.5), abs(chess.square_rank(polje) - 3.5)) #0 za centar, 3.5 za rub ploče


def aktivnost_kralja(ploca: chess.Board, boja: chess.Color) -> float:
    kralj = ploca.king(boja)
    if kralj != None:
        return (3.5 - udaljenost_od_centra(kralj)) * AKTIVNOST_KRALJA
    #Za upravljanje greškom kada kralj nije na ploči jer .king može vratiti None
    else:
        return 0



####################################################################################################
########################################### EVALUACIJA #############################################
####################################################################################################

def materijal(mapa_figura: dict) -> float:
    
    prednost = 0
    for figura in mapa_figura.values(): #.piece_map() vraća rječnik s ključevima kao poljima i vrijednostima kao figurama na tim poljima
        vrijednost = pocetne_vrijednosti_figura[figura.piece_type]
        if figura.color == chess.WHITE:
            prednost += vrijednost
        else:
            prednost -= vrijednost

    return prednost


def zrcaljenje_ploce(polje, boja):
    return polje if boja == chess.WHITE else chess.square_mirror(polje)


def pst(ploca: chess.Board,
        mapa_figura: dict,
        bijeli_pijuni,
        crni_pijuni,
        udaljenost_od_kraja: float,
        koristi_markovljevu_mobilnost: bool = True) -> float:

    stupci_s_bijelim_pijunima = stupci_s_pijunima(bijeli_pijuni)
    stupci_s_crnim_pijunima = stupci_s_pijunima(crni_pijuni)
    

    ukupni_bonus = 0
    for polje, figura in mapa_figura.items():

        if figura.piece_type == chess.PAWN: #Bonusi su pod #PIJUNI
            bonus = bonus_pijuna[zrcaljenje_ploce(polje, figura.color)]

        elif figura.piece_type == chess.KNIGHT: #Bonus je pod #SKAKAČI
            if koristi_markovljevu_mobilnost:
                bonus = ALFA_SKAKAC * markovljeva_mobilnost_skakaca(ploca, polje, figura.color)
            else:
                bonus = 0
            bonus -= KAZNA_SKAKACA_ZAVRSNICA * (1-udaljenost_od_kraja)

        elif figura.piece_type == chess.BISHOP: #Bonusi su pod #LOVCI
            vlastiti_pijuni = bijeli_pijuni if figura.color == chess.WHITE else crni_pijuni
            bonus = bonus_lovca[polje] + ALFA_LOVAC * mobilnost_lovca(ploca, polje, figura) + BETA_LOVAC * dobar_lovac(polje, vlastiti_pijuni) + BONUS_LOVCA_ZAVRSNICA * (1-udaljenost_od_kraja)

        elif figura.piece_type == chess.ROOK: #Bonusi su pod #TOPOVI
            if figura.color == chess.WHITE:
                bonus = ocijeni_topov_stupac(polje, stupci_s_bijelim_pijunima, stupci_s_crnim_pijunima)
            else:
                bonus = ocijeni_topov_stupac(polje, stupci_s_crnim_pijunima, stupci_s_bijelim_pijunima)
            if top_na_sedmom_redu(ploca, polje, figura.color):
                bonus += TOP_SEDMI_RED_BONUS

        elif figura.piece_type == chess.QUEEN: #Bonusi su pod #KRALJICA
            bonus = ALFA_KRALJICA * mobilnost_kraljice(ploca, polje, figura)
            if rani_izlazak_kraljice(ploca, polje, figura.color):
                bonus -= KAZNA_ZA_RANO_POMICANJE
        
        else:
            bonus = 0

        ukupni_bonus += bonus if figura.color == chess.WHITE else -bonus

    return ukupni_bonus


MASKE_PROLAZA_PIJUNA = {}
def izgradi_maske_prolaza_pijuna():
    for boja in (chess.WHITE, chess.BLACK):
        for polje in chess.SQUARES:
            stupac = chess.square_file(polje)
            red = chess.square_rank(polje)
            maska = 0
            for s in (stupac - 1, stupac, stupac + 1):
                if s < 0 or s > 7:
                    continue
                if boja == chess.WHITE:
                    redovi = range(red + 1, 8)
                else:
                    redovi = range(0, red)
                for r in redovi:
                    maska |= chess.BB_SQUARES[chess.square(s, r)]
            MASKE_PROLAZA_PIJUNA[(boja, polje)] = maska
    return MASKE_PROLAZA_PIJUNA
MASKE_PROLAZA_PIJUNA = izgradi_maske_prolaza_pijuna()


def evaluiraj_pijune(boja: chess.Color, pijuni, protivnicki_pijuni) -> float:
    
    prednost = 0
    broj_pijuna_po_stupcima = [0]*8

    for pijun in pijuni:
        broj_pijuna_po_stupcima[chess.square_file(pijun)] += 1

    #Dvostruki pijuni
    for stupac in broj_pijuna_po_stupcima:
        if stupac > 1:
            prednost -= DVOSTRUKI_PIJUNI_KAZNA*(stupac-1)

    #Izolirani pijuni
    for pijun in pijuni:
        stupac = chess.square_file(pijun)
        lijevi_stupac = stupac - 1
        desni_stupac = stupac + 1
        
        izoliran = True
        if lijevi_stupac >= 0 and broj_pijuna_po_stupcima[lijevi_stupac] > 0:
            izoliran = False
        if desni_stupac <= 7 and broj_pijuna_po_stupcima[desni_stupac] > 0:
            izoliran = False

        if izoliran:
            prednost -= IZOLIRANI_PIJUN_KAZNA

    #Napredni pijuni
    protivnicka_maska = int(protivnicki_pijuni)
    for pijun in pijuni:
        maska_prolaza = MASKE_PROLAZA_PIJUNA[(boja, pijun)]
        if not (protivnicka_maska & maska_prolaza):
            prednost += NAPREDNI_PIJUN_BONUS

    return prednost


def struktura_pijuna(bijeli_pijuni, crni_pijuni) -> float:
    return (evaluiraj_pijune(chess.WHITE, bijeli_pijuni, crni_pijuni) - evaluiraj_pijune(chess.BLACK, crni_pijuni, bijeli_pijuni))


def globalne_heuristike(ploca: chess.Board) -> float:
    prednost = 0
    if par_lovaca(ploca, chess.WHITE):
        prednost += PAR_LOVACA_BONUS
    if par_lovaca(ploca, chess.BLACK):
        prednost -= PAR_LOVACA_BONUS
    if topovi_povezani(ploca, chess.WHITE):
        prednost += POVEZANI_TOPOVI_BONUS
    if topovi_povezani(ploca, chess.BLACK):
        prednost -= POVEZANI_TOPOVI_BONUS
    return prednost


def evaluacija_pozicije(ploca: chess.Board, koristi_markovljevu_mobilnost: bool = True) -> float:
    mapa_figura = ploca.piece_map()
    bijeli_pijuni = ploca.pieces(chess.PAWN, chess.WHITE)
    crni_pijuni = ploca.pieces(chess.PAWN, chess.BLACK)
    udaljenost_od_kraja = udaljenost_od_kraja_partije(mapa_figura)
    razlika_aktivnosti = aktivnost_kralja(ploca, chess.WHITE) - aktivnost_kralja(ploca, chess.BLACK)

    prednost = 0
    prednost += materijal(mapa_figura)
    prednost += pst(ploca, mapa_figura, bijeli_pijuni, crni_pijuni, udaljenost_od_kraja, koristi_markovljevu_mobilnost)
    prednost += struktura_pijuna(bijeli_pijuni, crni_pijuni)
    prednost += globalne_heuristike(ploca)
    prednost += sigurnost_kralja(ploca) * udaljenost_od_kraja + razlika_aktivnosti * (1 - udaljenost_od_kraja)

    return prednost


def evaluacija(ploca: chess.Board) -> float:

    #Ako je na ploči mat, boja na potezu je izgubila
    if ploca.is_checkmate():
        return -1_000_000 if ploca.turn == chess.WHITE else 1_000_000

    #Ako je na ploči pat ili nedovoljno materijala za mat, pozicija je neriješena
    if ploca.is_stalemate() or ploca.is_insufficient_material():
        return 0
    
    return evaluacija_pozicije(ploca)



#############################################################################################
#################################### PRETRAŽIVANJE ##########################################
#############################################################################################

def prioritet_poteza(ploca: chess.Board,
                     potez: chess.Move,
                     najbolji_potez_prosle_iteracije: chess.Move | None = None,
                     killer_potezi_na_dubini: list | None = None) -> int:

    if potez == najbolji_potez_prosle_iteracije:
        return 10**6
    
    if ploca.is_capture(potez):
        napadac = ploca.piece_at(potez.from_square)
        if napadac is None:
            return 10**5
        zrtva = ploca.piece_at(potez.to_square)
        if zrtva is not None:
            vrijednost_zrtve = pocetne_vrijednosti_figura[zrtva.piece_type]
        else:
            vrijednost_zrtve = pocetne_vrijednosti_figura[chess.PAWN] #u slučaju en passanta
        vrijednost_napadaca = pocetne_vrijednosti_figura[napadac.piece_type]
        return 10**5 + vrijednost_zrtve - vrijednost_napadaca
    
    if potez.promotion is not None:
        return 10**4

    if killer_potezi_na_dubini != None and potez in killer_potezi_na_dubini:
        return 10**3
    
    if ploca.is_castling(potez):
        return 10**2

    return 0


def sortiraj_poteze(ploca: chess.Board, najbolji_potez_prosle_iteracije: chess.Move | None = None,
                    killer_potezi_na_dubini: list | None = None) -> list[chess.Move]:
    potezi = list(ploca.legal_moves)
    potezi.sort(key=lambda potez: prioritet_poteza(ploca, potez, najbolji_potez_prosle_iteracije, killer_potezi_na_dubini), reverse = True)
    return potezi


def azuriraj_killer_poteze(dubina: int, potez: chess.Move) -> None:
    lista = killer_potezi.setdefault(dubina, [])
    if potez in lista:
        return
    lista.insert(0, potez)
    if len(lista) > 2:
        lista.pop()


def nemirno_pretrazivanje(ploca: chess.Board, igrac_na_redu: bool, vrijeme_pocetka: float, alfa: float = float('-inf'),
                          beta: float = float('inf'), preskoci_provjeru_kraja: bool = False,
                          koristi_markovljevu_mobilnost: bool = False) -> tuple[float, chess.Move | None]:

    global broj_cvorova
    broj_cvorova += 1

    if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
        raise vrijeme_isteklo

    if not preskoci_provjeru_kraja and (ploca.is_checkmate() or ploca.is_stalemate() or ploca.is_insufficient_material()):
        return evaluacija(ploca), None

    trenutna_vrijednost = evaluacija_pozicije(ploca, koristi_markovljevu_mobilnost = koristi_markovljevu_mobilnost)

    # Stand-pat evaluacija:
    # Ako je pozicija dovoljno dobra bez izvođenja taktičkog poteza,
    # nema potrebe tražiti lošije nastavke.
    if igrac_na_redu:
        if trenutna_vrijednost >= beta:
            return trenutna_vrijednost, None
        alfa = max(alfa, trenutna_vrijednost)
    else:
        if trenutna_vrijednost <= alfa:
            return trenutna_vrijednost, None
        beta = min(beta, trenutna_vrijednost)

    najbolji_potez = None

    for potez in ploca.generate_legal_captures(): #uzimamo u obzir samo taktičke poteze

        if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
            raise vrijeme_isteklo

        stanje_rosade = odigraj_potez(ploca, potez)

        try:
            vrijednost, _ = nemirno_pretrazivanje(ploca, not igrac_na_redu, vrijeme_pocetka, alfa, beta)
        finally:
            ponisti_potez(ploca, stanje_rosade)

        #Minimax
        if igrac_na_redu:
            if vrijednost > trenutna_vrijednost:
                trenutna_vrijednost = vrijednost
                najbolji_potez = potez
            alfa = max(alfa, trenutna_vrijednost)
            if alfa >= beta:
                break
        else:
            if vrijednost < trenutna_vrijednost:
                trenutna_vrijednost = vrijednost
                najbolji_potez = potez
            beta = min(beta, trenutna_vrijednost)
            if alfa >= beta:
                break

    return trenutna_vrijednost, najbolji_potez


def pretrazivanje(ploca: chess.Board,
                  dubina: int,
                  igrac_na_redu: bool,
                  vrijeme_pocetka: float,
                  najbolji_potez_prosle_iteracije: chess.Move | None = None,     
                  alfa: float = float('-inf'),
                  beta: float = float('inf')) -> tuple[float, chess.Move | None]:
    
    global broj_cvorova, broj_TT_pogodaka
    broj_cvorova += 1

    if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
        raise vrijeme_isteklo

    if ploca.is_checkmate() or ploca.is_stalemate() or ploca.is_insufficient_material():
        return evaluacija(ploca), None

    #Početne alfa i beta ćemo koristiti kasnije za određivanje tipa TT unosa
    originalna_alfa = alfa
    originalni_beta = beta

    #Generiramo ključ trenutne pozicije
    kljuc = kljuc_pozicije(ploca)

    #Provjera postoji li trenutna pozicija već u TT-u
    unos = transpozicijska_tablica.get(kljuc)

    if unos != None:
        spremljena_dubina, spremljena_vrijednost, tip, spremljeni_potez = unos
        if spremljena_dubina >= dubina:
            # Egzaktna vrijednost
            if tip == TT_egzaktna:
                broj_TT_pogodaka += 1
                return spremljena_vrijednost, spremljeni_potez
            # Alfa-bound
            elif tip == TT_alfa and spremljena_vrijednost <= alfa:
                broj_TT_pogodaka += 1
                return spremljena_vrijednost, spremljeni_potez
            # Beta-bound
            elif tip == TT_beta and spremljena_vrijednost >= beta:
                broj_TT_pogodaka += 1
                return spremljena_vrijednost, spremljeni_potez

    if dubina == 0:
        return nemirno_pretrazivanje(ploca, igrac_na_redu, vrijeme_pocetka, alfa, beta,
                                     preskoci_provjeru_kraja = True, koristi_markovljevu_mobilnost = False)

    #Inicijalizacija minimax vrijednosti
    if igrac_na_redu:
        najbolja_vrijednost = float('-inf')
    else:
        najbolja_vrijednost = float('inf')

    najbolji_potez = None

    #Ako je pozicija pronađena u TT-u, spremljeni potez koristimo za move ordering
    TT_potez = None

    if unos is not None:
        spremljena_dubina, spremljena_vrijednost, tip, spremljeni_potez = unos
        TT_potez = spremljeni_potez

    #TT potez ima prioritet nad potezom iz prethodne iteracije
    najbolji_potez_za_sortiranje = najbolji_potez_prosle_iteracije

    if TT_potez is not None:
        najbolji_potez_za_sortiranje = TT_potez

    potezi = sortiraj_poteze(ploca, najbolji_potez_za_sortiranje, killer_potezi.get(dubina))

    for indeks, potez in enumerate(potezi):

        if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
            raise vrijeme_isteklo

        je_uzimanje = ploca.is_capture(potez)
        je_rosada = odigraj_potez(ploca, potez)
        je_sah = ploca.is_check()

        try:
            radi_smanjenje = (
                indeks >= BROJ_NAJBOLJIH_POTEZA
                and dubina >= MIN_DUBINA_SELEKTIVNOG_PRODUBLJIVANJA
                and not je_rosada
                and not je_uzimanje
                and not ploca.is_check()
            )

            if radi_smanjenje:
                smanjena_dubina = max(dubina - 1 - SMANJENJE_NEBITNIH_POTEZA, 0)
                vrijednost, _ = pretrazivanje(ploca, smanjena_dubina, not igrac_na_redu, vrijeme_pocetka,
                                              None, alfa, beta)
                #Ako smanjena pretraga izgleda obećavajuće, ponovi na punu dubinu
                if (igrac_na_redu and vrijednost > alfa) or (not igrac_na_redu and vrijednost < beta):
                    vrijednost, _ = pretrazivanje(ploca, dubina-1, not igrac_na_redu, vrijeme_pocetka,
                                                  None, alfa, beta)
            else:
                #Ako je potez šah, ne smanjujemo dubinu radi dubljeg pretraživanja
                sljedeca_dubina = dubina if je_sah else dubina - 1
                vrijednost, _ = pretrazivanje(ploca, sljedeca_dubina, not igrac_na_redu, vrijeme_pocetka,
                                              None, alfa, beta)
        finally:
            ponisti_potez(ploca, je_rosada)
        #Minimax
        if igrac_na_redu:
            if vrijednost > najbolja_vrijednost:
                najbolja_vrijednost = vrijednost
                najbolji_potez = potez

            alfa = max(alfa, najbolja_vrijednost)

            if alfa >= beta:
                if not je_uzimanje:
                    azuriraj_killer_poteze(dubina, potez)
                break
        else:
            if vrijednost < najbolja_vrijednost:
                najbolja_vrijednost = vrijednost
                najbolji_potez = potez

            beta = min(beta, najbolja_vrijednost)

            if alfa >= beta:
                if not je_uzimanje:
                    azuriraj_killer_poteze(dubina, potez)
                break

    #Određujemo tip rezultata za spremanje u TT
    #Bijeli
    if igrac_na_redu:
        if najbolja_vrijednost <= originalna_alfa:
            tip = TT_alfa
        elif najbolja_vrijednost >= originalni_beta:
            tip = TT_beta
        else:
            tip = TT_egzaktna
    #Crni
    else:
        if najbolja_vrijednost >= originalni_beta:
            tip = TT_beta
        elif najbolja_vrijednost <= originalna_alfa:
            tip = TT_alfa
        else:
            tip = TT_egzaktna

    if najbolji_potez == None:
        najbolji_potez = TT_potez

    #Spremamo rezultat u transpozicijsku tablicu
    transpozicijska_tablica[kljuc] = (dubina, najbolja_vrijednost, tip, najbolji_potez)

    return najbolja_vrijednost, najbolji_potez


def resetiraj_stanje() -> None:
    #Poziva se prije svake nove partije (za TT i rošade)
    global broj_cvorova, broj_tt_pogodaka
    transpozicijska_tablica.clear()
    killer_potezi.clear()
    napravio_rosadu[chess.WHITE] = False
    napravio_rosadu[chess.BLACK] = False
    broj_cvorova = 0
    broj_TT_pogodaka = 0


def vrati_najbolji_potez(ploca: chess.Board) -> chess.Move:

    global broj_cvorova, broj_TT_pogodaka

    #Prvo probamo s potezom iz knjige otvaranja
    najbolji_potez = book.odaberi_nasumicni_potez(ploca)
    if najbolji_potez != None and ploca.fullmove_number <= MAX_OTVARAJUCIH_POTEZA:
        return najbolji_potez

    vrijeme_pocetka = time.time()
    legalni_potezi = list(ploca.legal_moves)
    if not legalni_potezi:
        return chess.Move.null()

    #Forsirani potez možemo odmah odigrati
    if len(legalni_potezi) == 1:
        return legalni_potezi[0]

    najbolji_potez = legalni_potezi[0]
    najbolji_potez_prosle_iteracije = None

    dubina = 1
    broj_cvorova = 0
    broj_TT_pogodaka = 0
    killer_potezi.clear()

    #Posebno gledamo slučaj dubine 1 tako da možemo zapamtiti najbolji potez
    #ako stroj ne izvrši prvo pretraživanje do kraja
    try:
        sortirani_potezi = sortiraj_poteze(ploca)
        najbolja_vrijednost_prve_iteracije = float('-inf') if ploca.turn == chess.WHITE else float('inf')
        
        for potez in sortirani_potezi:
            if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
                raise vrijeme_isteklo
            stanje_rosade = odigraj_potez(ploca, potez)

            try:
                vrijednost, _ = nemirno_pretrazivanje(ploca, ploca.turn, vrijeme_pocetka, koristi_markovljevu_mobilnost = False)
            finally:
                ponisti_potez(ploca, stanje_rosade)

            #Bijeli max.
            if ploca.turn == chess.WHITE:
                if vrijednost > najbolja_vrijednost_prve_iteracije:
                    najbolja_vrijednost_prve_iteracije = vrijednost
                    najbolji_potez = potez
            #Crni min.
            else:
                if vrijednost < najbolja_vrijednost_prve_iteracije:
                    najbolja_vrijednost_prve_iteracije = vrijednost
                    najbolji_potez = potez

        najbolji_potez_prosle_iteracije = najbolji_potez
        #print("Završena dubina pretraživanja: 1") ZA PRIVATNO TESTIRANJE
        print("Završena dubina pretraživanja: 1", file = sys.stderr) #ZA UCI TESTIRANJE

        dubina = 2

        #Zaustavljamo pretraživanje ako je pronađen šah mat
        GRANICA_SIGURNOG_SAHMATA = 500000 #Proizvoljan broj, ali dovoljno velik
        while True:
            vrijednost, potez = pretrazivanje(ploca, dubina, ploca.turn, vrijeme_pocetka,
                                        najbolji_potez_prosle_iteracije)

            if potez is not None:
                najbolji_potez = potez
                najbolji_potez_prosle_iteracije = potez

            #Ispis završene dubine radi praćenja učinkovitosti
            #print(f"Završena dubina pretraživanja: {dubina}")
            print(f"Završena dubina pretraživanja: {dubina}", file = sys.stderr) #ZA UCI TESTIRANJE

            if abs(vrijednost) >= GRANICA_SIGURNOG_SAHMATA:
                break

            dubina += 1

    except vrijeme_isteklo:
        pass

    #print(f"Ukupan broj pretraženih čvorova: {broj_cvorova}")
    #print(f"TT pogodci: {broj_TT_pogodaka}")
    print(f"Ukupan broj pretraženih čvorova: {broj_cvorova}", file = sys.stderr) #ZA UCI TESTIRANJE
    print(f"TT pogodci: {broj_TT_pogodaka}", file = sys.stderr) #ZA UCI TESTIRANJE

    return najbolji_potez
