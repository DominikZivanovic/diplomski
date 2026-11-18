import chess #Za generiranje legalnih poteza, uzimanja figure itd.
import chess.polyglot
import time
import sys
import math
import os #Za put do knjige otvaranja
from Polyglot import PolyglotBook #Za otvaranja; PolyglotBook klasa iz PolyGlot.py
from Figura_polje_tablice import PIJUN_KONTROLA_CENTRA, PIJUN_RANG_BONUS, LOVAC_MOBILNOST, DAMA_MOBILNOST
from Stacionarna_distribucija_skakaca import markovljeva_mobilnost_skakaca, postavi_vrijednosti_figura
from operator import add #Za zbrajanje tablica u evaluaciji figura

#STROJ KORISTI:
#MINIMAX
#ALFA-BETA REZANJE
#ITERATIVNO PRODUBIVANJE
#TRANSPOZICIJSKE TABLICE
#KILLER POTEZE (ONE KOJI SU UZROKOVALI ALFA-BETA REZANJE NA NEKOJ DUBINI)
#LMR
#NEMIRNO PRETRAŽIVANJE
#KNJIGU OTVARANJA

#BOOLEOVE VARIJABLE ZA VERZIJU STROJA
KORISTI_ALFA_BETA = True #False => BezAB: nema alfa-beta rezanja (pa nema ni alfa/beta unosa u TT niti killer poteza)
KORISTI_SORTIRANJE = True #False => BezSORT: poteze ne sortiramo za alfa-beta rezanje (pa nema ni LMR-a)
KORISTI_TT = True #False => BezTT: nema čitanja ni pisanja u transpozicijsku tablicu
KORISTI_NEMIRNO = True #False => BezNP: na horizontu se koristi statička evaluacija
KORISTI_SDS = False #False => BezSDS: bonus za skakače ne ovisi o drugim figurama (ne računamo stac. distr.)

#VARIJABLE ZA PRETRAŽIVANJE
MAX_POTEZA_OTVARANJA = 8 #Koliko poteza maksimalno koristimo iz knjige otvaranja (ako je dostupna)
MAX_NEMIRNA_DUBINA = 6 #Koliko poteza maksimalno pretražujemo u nemirnom pretraživanju
NEMIRNI_POMAK_DUBINE = MAX_NEMIRNA_DUBINA + 1 #Za prikaz nemirnih dubina kao negativnih brojeva
BROJ_NAJBOLJIH_POTEZA = 3 #Koliko najboljih poteza iz prethodne iteracije ne smanjujemo LMR-om
SMANJENJE_NEBITNIH_POTEZA = 2 #Koliko dubina smanjujemo u plićem pretraživanju za LMR
MIN_DUBINA_LMR = 2 #Od koje dubine se može provoditi LMR
MAX_SAH_PRODUZETAKA = 3 #Koliko puta produžujemo pretraživanje ako je šah
MAX_KILLER_POTEZA_PO_DUBINI = 3 #Koliko killer poteza po dubini pamtimo (ako je više, brišemo najstarije)
VRIJEDNOST_SAHMATA = 1_000_000
GRANICA_SIGURNOG_SAHMATA = 500_000 #Iznad ove vrijednosti prekidamo produbljivanje


#TRANSPOZICIJSKE TABLICE (TT)
MAX_VELICINA_TT = 5*10**5 #Max veličina transpozicijske tablice
transpozicijska_tablica = {} #Hash tablica sa Zobristovim ključevima i
#uređenim obilježjima pozicije (evaluacija, dubina pretraživanja, najbolji potez).
TT_egzaktna = 0 #Ovdje pamtimo poziciju ako znamo njenu egzaktnu evaluaciju
TT_alfa = 1 #Vrijednost je gornja granica prave vrijednosti (pretraživanje nije poboljšalo alfu, V <= alfa)
TT_beta = 2 #Vrijednost je donja granica prave vrijednosti (dogodilo se beta rezanje, V >= beta)
broj_TT_pogodaka = 0 #Za provjeru učinkovitosti transpozicijskih tablica

#Funkcija pamti poziciju s ploče i je li rokada odigrana kao tuple
def kljuc_pozicije(ploca: chess.Board) -> tuple | None:
    if not KORISTI_TT:
        return None
    return (chess.polyglot.zobrist_hash(ploca), napravio_rokadu.get(chess.WHITE), napravio_rokadu.get(chess.BLACK))

#Funkcija pohranjuje unos u TT
def pohrani_TT(kljuc: tuple | None, dubina: int, vrijednost: float, tip: int, potez: chess.Move | None) -> None:
    if not KORISTI_TT:
        return

    postojeci = transpozicijska_tablica.get(kljuc)

    #Ako je pozicija već u tablici, ne mijenjamo ju istom pozicijom koja je plića
    if postojeci != None and dubina < postojeci[0]:
        return

    #Ako dodajemo novu poziciju u punu tablicu, brišemo najplići unos
    if postojeci == None and len(transpozicijska_tablica) >= MAX_VELICINA_TT:
        najplici_kljuc = min(transpozicijska_tablica, key=lambda k: transpozicijska_tablica[k][0])
        del transpozicijska_tablica[najplici_kljuc]

    transpozicijska_tablica[kljuc] = (dubina, vrijednost, tip, potez)


#UPRAVLJANJE VREMENOM
MAX_VRIJEME_PRETRAZIVANJA = 4 #U sekundama
class vrijeme_isteklo(Exception):
    pass


#BROJANJE VRHOVA
broj_vrhova = 0 #Za brojanje pretraženih vrhova tijekom pretraživanja


#KILLER POTEZI
killer_potezi = {} #Rječnik za spremanje dubine i liste killer poteza


#KNJIGA OTVARANJA
#Za lokalni path do knjige otvaranja
OTVARANJA_PATH = os.environ.get("OTVARANJA_PATH_LOKALNO", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                     "Otvaranja", "Perfect2023.bin"))
book = None
if os.path.isfile(OTVARANJA_PATH):
    book = PolyglotBook(OTVARANJA_PATH)
    book.__enter__()
else:
    print(f"Knjiga otvaranja nije pronađena ({OTVARANJA_PATH}), stroj igra bez nje.", file=sys.stderr)


#PREOSTALI MATERIJAL (za sigurnost kralja)
DOPRINOS_KRAJU_PARTIJE = {chess.KNIGHT: 300, chess.BISHOP: 300, chess.ROOK: 500, chess.QUEEN: 900}
BROJ_FIGURA_NA_POCETKU = {chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}
max_udaljenost_od_kraja = sum(DOPRINOS_KRAJU_PARTIJE[figura] * BROJ_FIGURA_NA_POCETKU[figura] for figura in DOPRINOS_KRAJU_PARTIJE) * 2

#Funkcija određuje koliko smo daleko od završnice (1 ako smo na početku, 0 ako smo na kraju)
def udaljenost_od_kraja_partije(mapa_figura: dict) -> float:
    udaljenost_od_kraja = 0
    for figura in mapa_figura.values():
        udaljenost_od_kraja += DOPRINOS_KRAJU_PARTIJE.get(figura.piece_type, 0)
    udaljenost_od_kraja = min(udaljenost_od_kraja, max_udaljenost_od_kraja)

    return udaljenost_od_kraja/max_udaljenost_od_kraja


#ZRCALJENJE PLOČE
def zrcaljenje_ploce(polje, boja):
    return polje if boja == chess.WHITE else chess.square_mirror(polje)


#IGRA PROTIV SAMOG SEBE
def resetiraj_stanje() -> None:
    #Poziva se prije svake nove partije (za resetiranje TT-a i rokade)
    global broj_vrhova, broj_TT_pogodaka
    transpozicijska_tablica.clear()
    killer_potezi.clear()
    napravio_rokadu[chess.WHITE] = False
    napravio_rokadu[chess.BLACK] = False
    broj_vrhova = 0
    broj_TT_pogodaka = 0



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


#PIJUNI
ALFA_PIJUN = 8 #Kontrola centra
BETA_PIJUN = 3 #Nagrada za rang
bonus_pijuna = list(map(add, [x*ALFA_PIJUN for x in PIJUN_KONTROLA_CENTRA], [x*BETA_PIJUN for x in PIJUN_RANG_BONUS]))


#SKAKAČ
ALFA_SKAKAC = 0.15 #Mobilnost skakača


#LOVCI (alfa*mobilnost + beta*dobar_lovac + gama*par_lovaca)
ALFA_LOVAC = 5 #Mobilnost
BETA_LOVAC = 15 #Dobar lovac
GAMA_LOVAC = 20 #Bonus pojedinačnom lovcu za par lovaca

#Funkcija vraća izraz (1 - n/8) iz bonusa lovca gdje n broj vlastitih pijuna na polji iste boje kao i lovčevo
def dobar_lovac(polje: chess.Square, vlastiti_pijuni) -> float:
    boja_polja_lovca = (chess.square_rank(polje) + chess.square_file(polje)) % 2 #0 za bijelo polje, 1 za crno polje
    broj_pijuna_na_istoj_boji = 0
    for polje2 in vlastiti_pijuni:
        if (chess.square_rank(polje2) + chess.square_file(polje2)) % 2 == boja_polja_lovca:
            broj_pijuna_na_istoj_boji += 1

    return 1 - broj_pijuna_na_istoj_boji / 8

#Funkcija provjerava jesu li na ploči oba lovca
def par_lovaca(ploca: chess.Board, boja: chess.Color) -> bool:
    return len(ploca.pieces(chess.BISHOP, boja)) >= 2


#TOPOVI
ALFA_TOP = 40 #Bonus pojedinačnom topu za otvoreni stupac (alfa'_T)
ALFA_TOP_POLA = 20 #Bonus pojedinačnom topu za poluotvoreni stupac (alfa'_T / 2)
BETA_TOP = 20 #Bonus pojedinačnom topu za povezanost
GAMA_TOP = 30 #Bonus pojedinačnom topu ako je na sedmom rangu

#Funkcija provjerava je li topov stupac otvoren, poluotvoren ili zatvoren i vraća odgovarajući bonus
def ocijeni_topov_stupac(ploca: chess.Board, polje: chess.Square) -> float:
    broj_pijuna_u_stupcu = chess.popcount(ploca.pawns & chess.BB_FILES[chess.square_file(polje)])

    if broj_pijuna_u_stupcu == 0:
        return ALFA_TOP
    elif broj_pijuna_u_stupcu == 1:
        return ALFA_TOP_POLA
    else:
        return 0

#Funkcija provjerava nalazi li se top na sedmom rangu
def top_na_sedmom_redu(ploca: chess.Board, polje: chess.Square, boja: chess.Color) -> bool:
    red = chess.square_rank(polje)
    return red == 6 if boja == chess.WHITE else red == 1

#Funkcija provjerava ima li figura između topova na istom redu
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


#KRALJ
ALFA_KRALJ = 70 #Rokirani kralj
BETA_KRALJ = 15 #Kraljeva aktivnost
GAMA_KRALJ = 30 #Netaknuti pijun pred rokiranim kraljem

#Ovdje pamtimo je li neki igrač napravio rokadu
napravio_rokadu = {chess.WHITE: False, chess.BLACK: False}

#Funkcija igra potez na ploči i ažurira napravio_rokadu.
#Korištena je isključivo hipotetski u pretraživanju.
def potez_je_rokada(ploca: chess.Board, potez: chess.Move) -> bool:
    global napravio_rokadu
    je_rokada = ploca.is_castling(potez)
    boja = ploca.turn
    ploca.push(potez)
    if je_rokada:
        napravio_rokadu[boja] = True
    return je_rokada

#Funkcija poništava prošli potez i vraća napravio_rokadu na prethodnu vrijednost.
#Korištena je isključivo hipotetski u pretraživanju.
def ponisti_potez(ploca: chess.Board, je_rokada: bool) -> None:
    global napravio_rokadu
    boja = not ploca.turn
    ploca.pop()
    if je_rokada:
        napravio_rokadu[boja] = False

#Funkcija služi za praćenje stvarne rokade na ploči
def izgleda_rokirano(ploca: chess.Board, boja: chess.Color) -> bool:
    if boja == chess.WHITE:
        return not ploca.has_castling_rights(chess.WHITE) and ploca.king(chess.WHITE) in (chess.G1, chess.C1)
    else:
        return not ploca.has_castling_rights(chess.BLACK) and ploca.king(chess.BLACK) in (chess.G8, chess.C8)

#Bitboard pijuna pred rokiranim kraljem
def bitboard_polja(polja: list) -> int:
    rezultat = 0
    for p in polja:
        rezultat = rezultat + chess.BB_SQUARES[p]
    return rezultat

#Prilagodba bitboarda pojedinom igraču
PIJUNI_PRED_ROKIRANIM_KRALJEM_POLJA = {
    chess.WHITE: {
        chess.G1: bitboard_polja([chess.F2, chess.G2, chess.H2]),
        chess.C1: bitboard_polja([chess.B2, chess.C2, chess.D2]),
    },
    chess.BLACK: {
        chess.G8: bitboard_polja([chess.F7, chess.G7, chess.H7]),
        chess.C8: bitboard_polja([chess.B7, chess.C7, chess.D7]),
    },
}

def rokirani_kralj_bool(ploca: chess.Board, boja: chess.Color) -> float:
    return 1 if napravio_rokadu[boja] else 0

def broj_pijuna_pred_kraljem(ploca: chess.Board, boja: chess.Color) -> int:
    if not napravio_rokadu[boja]:
        return 0
    kralj = ploca.king(boja)
    if kralj == None:
        return 0
    maska = PIJUNI_PRED_ROKIRANIM_KRALJEM_POLJA[boja].get(kralj)
    if maska == None:
        return 0
    vlastiti_pijuni = ploca.pawns & ploca.occupied_co[boja]
    return chess.popcount(vlastiti_pijuni & maska)

def udaljenost_od_centra(polje: chess.Square) -> float:
    return math.floor(max(abs(3.5 - chess.square_file(polje)), abs(3.5 - chess.square_rank(polje))))

def aktivnost_kralja(ploca: chess.Board, boja: chess.Color) -> float:
    kralj = ploca.king(boja)
    if kralj != None:
        return (3 - udaljenost_od_centra(kralj))
    #Za upravljanje greškom kada kralj nije na ploči jer .king može vratiti None
    else:
        return 0



####################################################################################################
########################################### EVALUACIJA #############################################
####################################################################################################

#Funkcija vraća evaluciju pozicije isključivo po početnim vrijednostima figura
def materijal(mapa_figura: dict) -> float:
    prednost = 0
    for figura in mapa_figura.values():
        vrijednost = pocetne_vrijednosti_figura[figura.piece_type]
        prednost += vrijednost if figura.color == chess.WHITE else -vrijednost
    return prednost

#Funkcija vraća razliku u bonusima figura dva igrača
def pst(ploca: chess.Board,
        mapa_figura: dict,
        bijeli_pijuni,
        crni_pijuni,
        udaljenost_od_kraja: float,
        koristi_markovljevu_mobilnost: bool = True) -> float:

    ukupni_bonus = 0
    for polje, figura in mapa_figura.items():

        if figura.piece_type == chess.PAWN: #Bonusi su pod #PIJUNI
            bonus = bonus_pijuna[zrcaljenje_ploce(polje, figura.color)]

        elif figura.piece_type == chess.KNIGHT: #Bonusi su pod #SKAKAČI
            if koristi_markovljevu_mobilnost:
                bonus = ALFA_SKAKAC * markovljeva_mobilnost_skakaca(ploca, polje, figura.color)
            else:
                bonus = 0

        elif figura.piece_type == chess.BISHOP: #Bonusi su pod #LOVCI
            vlastiti_pijuni = bijeli_pijuni if figura.color == chess.WHITE else crni_pijuni
            bonus = ALFA_LOVAC * LOVAC_MOBILNOST[polje] + BETA_LOVAC * dobar_lovac(polje, vlastiti_pijuni) + (GAMA_LOVAC if par_lovaca(ploca, figura.color) else 0)

        elif figura.piece_type == chess.ROOK: #Bonusi su pod #TOPOVI
            bonus = ocijeni_topov_stupac(ploca, polje)
            if topovi_povezani(ploca, figura.color):
                bonus += BETA_TOP
            if top_na_sedmom_redu(ploca, polje, figura.color):
                bonus += GAMA_TOP

        elif figura.piece_type == chess.QUEEN: #Bonusi su pod #KRALJICA
            bonus = ALFA_KRALJICA * DAMA_MOBILNOST[polje]

        else: #Bonusi su pod #KRALJ
            bonus = (ALFA_KRALJ * rokirani_kralj_bool(ploca, figura.color)
                     + BETA_KRALJ * (1 - udaljenost_od_kraja) * aktivnost_kralja(ploca, figura.color)
                     + GAMA_KRALJ * udaljenost_od_kraja * broj_pijuna_pred_kraljem(ploca, figura.color))

        if figura.color == chess.WHITE:
            ukupni_bonus += bonus
        else:
            ukupni_bonus -= bonus

    return ukupni_bonus

#Funkcija zbraja sve komponente koje ulaze u evaluaciju neke pozicije
def evaluacija_pozicije(ploca: chess.Board, koristi_markovljevu_mobilnost: bool = KORISTI_SDS) -> float:
    mapa_figura = ploca.piece_map()
    bijeli_pijuni = ploca.pieces(chess.PAWN, chess.WHITE)
    crni_pijuni = ploca.pieces(chess.PAWN, chess.BLACK)
    udaljenost_od_kraja = udaljenost_od_kraja_partije(mapa_figura)

    prednost = materijal(mapa_figura)
    prednost += pst(ploca, mapa_figura, bijeli_pijuni, crni_pijuni, udaljenost_od_kraja, koristi_markovljevu_mobilnost)

    return prednost


def evaluacija(ploca: chess.Board, koristi_markovljevu_mobilnost: bool = KORISTI_SDS) -> float:

    #Provjera je li na ploči šahmat ili pat/neriješeno
    if ploca.is_checkmate():
        return -VRIJEDNOST_SAHMATA if ploca.turn == chess.WHITE else VRIJEDNOST_SAHMATA
    #Koristimo ponavljanje nakon dva puta da stroj ranije vidi neriješeni ishod
    if ploca.is_stalemate() or ploca.is_insufficient_material() or ploca.is_repetition(2):
        return 0
    #Ako igra nije gotova, vraćamo evaluaciju pozicije
    return evaluacija_pozicije(ploca, koristi_markovljevu_mobilnost)



########################################################################################################
########################################## PRETRAŽIVANJE ###############################################
########################################################################################################

#Funkcija određuje kojim redom pretražiti poteze u novoj iteraciji: poznati TT_potez,
#najbolji potez iz prošle iteracije, uzimanja itd.
def prioritet_poteza(ploca: chess.Board, potez: chess.Move, TT_potez = None,
                     najbolji_potez_prosle_iteracije: chess.Move | None = None,
                     killer_potezi_na_dubini: list | None = None) -> int:

    if TT_potez != None and potez == TT_potez:
        return 10**7

    if potez == najbolji_potez_prosle_iteracije:
        return 10**6

    if ploca.is_capture(potez):
        napadac = ploca.piece_at(potez.from_square)
        zrtva = ploca.piece_at(potez.to_square)

        #Provjera za poziv napadac.piece_type koji ne smije biti None
        if napadac == None:
            return 10**5

        #MVV-LVA (most valuable victim - least valuable attacker)
        #zrtva može biti None u slučaju en passanta pa je tada vrijednost_zrtve jednaka vrijednosti pijuna
        vrijednost_zrtve = pocetne_vrijednosti_figura[zrtva.piece_type] if zrtva != None else pocetne_vrijednosti_figura[chess.PAWN]
        vrijednost_napadaca = pocetne_vrijednosti_figura[napadac.piece_type]
        return 10**5 + vrijednost_zrtve - vrijednost_napadaca

    if potez.promotion != None:
        return 10**4

    if killer_potezi_na_dubini != None and potez in killer_potezi_na_dubini:
        return 10**3

    if ploca.is_castling(potez):
        return 10**2

    return 0

#Funkcija sortira legalne poteze po željenom prioritetu
def sortiraj_poteze(ploca: chess.Board, TT_potez = None, najbolji_potez_prosle_iteracije: chess.Move | None = None,
                    killer_potezi_na_dubini: list | None = None) -> list[chess.Move]:
    potezi = list(ploca.legal_moves)
    # >>>>>> IZMJENA 9: BezSORT, poteze vraćamo bez sortiranja <<<<<<
    if not KORISTI_SORTIRANJE:
        return potezi
    potezi.sort(key=lambda potez: prioritet_poteza(ploca, potez, TT_potez, najbolji_potez_prosle_iteracije, killer_potezi_na_dubini), reverse=True)
    return potezi

#Funkcija ažurira killer_potezi
def azuriraj_killer_poteze(dubina: int, potez: chess.Move) -> None:

    #Ako ne postoji ključ dubina u killer_potezi, stvaramo ga i za vrijednost
    #stavljamo praznu listu.
    lista = killer_potezi.setdefault(dubina, [])

    #Ako je potez već u listi, izlazimo iz funkcije
    if potez in lista:
        return

    #FIFO princip, max. duljina liste je proizvoljna (MAX_KILLER_POTEZA_PO_DUBINI)
    #Listu ograničujemo jer relevantnost starijih poteza pada pa je poziv u
    #prioritet_poteza vremenski jeftiniji.
    lista.insert(0, potez)
    if len(lista) > MAX_KILLER_POTEZA_PO_DUBINI:
        lista.pop()

#Za prepoznavanje skore promocije u nemirnom pretraživanju
SEDMI_RANG = chess.BB_RANK_7 | chess.BB_RANK_2

#Funkcija produbljuje pretraživanje taktički agresivnih nizova poteza
def nemirno_pretrazivanje(ploca: chess.Board,
                          igrac_na_redu: bool,
                          vrijeme_pocetka: float,
                          alfa: float = float('-inf'),
                          beta: float = float('inf'),
                          preskoci_provjeru_kraja: bool = False,
                          koristi_markovljevu_mobilnost: bool = False,
                          nemirna_dubina = 0) -> tuple[float, chess.Move | None]:

    #Za brojanje pretraženih vrhova i TT pogodaka
    global broj_vrhova, broj_TT_pogodaka
    broj_vrhova += 1

    #Provjera je li vrijeme pretraživanja isteklo
    if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
        raise vrijeme_isteklo

    #Ako je partija gotova, nema najboljeg poteza i vraćamo evaluaciju pozicije
    if not preskoci_provjeru_kraja and (ploca.is_checkmate() or ploca.is_stalemate() or ploca.is_insufficient_material()
                                        or ploca.is_repetition(3)):
        return evaluacija(ploca), None

    #Pamtimo početne alfa/beta za klasifikaciju TT unosa
    originalna_alfa = alfa
    originalni_beta = beta

    #Ključ pozicije isti je kao u glavnom pretraživanju. Dubine nemirnog
    #pretraživanja za TT pohranu pamtimo kao negativan cijeli broj (<=-1), a dubine
    #glavnog pretraživanja za TT pohranu kao pozitivan (>= 1). Na taj način unosi nemirnog pretraživanja
    #ne mogu zadovoljiti pretragu glavnog pretraživanja, a obrnuto može.
    kljuc = kljuc_pozicije(ploca)
    dubina_za_TT = (MAX_NEMIRNA_DUBINA - nemirna_dubina) - NEMIRNI_POMAK_DUBINE

    #Provjera postoji li trenutna pozicija već u TT-u
    unos = transpozicijska_tablica.get(kljuc)
    TT_potez = None
    if unos != None:
        TT_dubina, TT_vrijednost, TT_tip, TT_potez = unos
        if TT_dubina >= dubina_za_TT:
            if TT_tip == TT_egzaktna:
                broj_TT_pogodaka += 1
                return TT_vrijednost, TT_potez
            elif TT_tip == TT_alfa and TT_vrijednost <= alfa:
                broj_TT_pogodaka += 1
                return TT_vrijednost, TT_potez
            elif TT_tip == TT_beta and TT_vrijednost >= beta:
                broj_TT_pogodaka += 1
                return TT_vrijednost, TT_potez

    trenutna_vrijednost = evaluacija_pozicije(ploca, koristi_markovljevu_mobilnost = koristi_markovljevu_mobilnost)

    #Ako smo prešli maksimalnu dubinu nemirnog pretraživanja, spremamo trenutnu vrijednost u TT i vraćamo je
    if nemirna_dubina >= MAX_NEMIRNA_DUBINA:
        pohrani_TT(kljuc, dubina_za_TT, trenutna_vrijednost, TT_egzaktna, None)
        return trenutna_vrijednost, None

    if igrac_na_redu:
        if trenutna_vrijednost >= beta:
            pohrani_TT(kljuc, dubina_za_TT, trenutna_vrijednost, TT_beta, None)
            return trenutna_vrijednost, None
        #Ako stroj koristi alfa-beta rezanje, ažuriramo alfa vrijednost za TT pohranu
        if KORISTI_ALFA_BETA:
            alfa = max(alfa, trenutna_vrijednost)
    else:
        if trenutna_vrijednost <= alfa:
            pohrani_TT(kljuc, dubina_za_TT, trenutna_vrijednost, TT_alfa, None)
            return trenutna_vrijednost, None
        if KORISTI_ALFA_BETA:
            beta = min(beta, trenutna_vrijednost)

    najbolji_potez = None

    #Dodajemo tihe promocije kako bi nemirno pretraživanje i njih uzelo u obzir
    takticki_potezi = list(ploca.generate_legal_captures())
    if ploca.pawns & SEDMI_RANG:
        for potez in ploca.legal_moves:
            if potez.promotion != None and not ploca.is_capture(potez):
                takticki_potezi.append(potez)

    #Ako TT_potez postoji i taktički je (nalazi se u takticki_potezi), stavljamo
    #ga na prvo mjesto radi boljeg poretka poteza i ranijih alfa-beta rezanja.
    if KORISTI_SORTIRANJE and TT_potez != None and TT_potez in takticki_potezi:
        takticki_potezi.remove(TT_potez)
        takticki_potezi.insert(0, TT_potez)

    #Za sve taktičke poteze, pokrećemo nemirno pretraživanje
    for potez in takticki_potezi:

        #Provjera je li vrijeme pretraživanja isteklo
        if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
            raise vrijeme_isteklo

        je_rokada = potez_je_rokada(ploca, potez)
        try:
            vrijednost, _ = nemirno_pretrazivanje(ploca, not igrac_na_redu, vrijeme_pocetka,
                                                  alfa, beta, koristi_markovljevu_mobilnost = koristi_markovljevu_mobilnost,
                                                  nemirna_dubina = nemirna_dubina+1)
        finally:
            ponisti_potez(ploca, je_rokada)

        #Alfa-beta rezanje
        if igrac_na_redu:
            if vrijednost > trenutna_vrijednost:
                trenutna_vrijednost = vrijednost
                najbolji_potez = potez
            if KORISTI_ALFA_BETA:
                alfa = max(alfa, trenutna_vrijednost)
                if alfa >= beta:
                    break
        else:
            if vrijednost < trenutna_vrijednost:
                trenutna_vrijednost = vrijednost
                najbolji_potez = potez
            if KORISTI_ALFA_BETA:
                beta = min(beta, trenutna_vrijednost)
                if alfa >= beta:
                    break
        # >>>>>> IZMJENA 9 (kraj) <<<<<<

    #Određujemo tip rezultata za spremanje u TT
    if trenutna_vrijednost <= originalna_alfa:
        TT_tip = TT_alfa
    elif trenutna_vrijednost >= originalni_beta:
        TT_tip = TT_beta
    else:
        TT_tip = TT_egzaktna

    pohrani_TT(kljuc, dubina_za_TT, trenutna_vrijednost, TT_tip, najbolji_potez)

    return trenutna_vrijednost, najbolji_potez


def pretrazivanje(ploca: chess.Board, dubina: int, igrac_na_redu: bool, vrijeme_pocetka: float,
                  najbolji_potez_prosle_iteracije: chess.Move | None = None,
                  alfa: float = float('-inf'), beta: float = float('inf'),
                  dubina_od_korijena: int = 0, broj_sah_produzetaka: int = 0) -> tuple[float, chess.Move | None]:

    #Za brojanje pretraženih vrhova
    global broj_vrhova, broj_TT_pogodaka
    broj_vrhova += 1

    #Provjera je li vrijeme pretraživanja isteklo
    if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
        raise vrijeme_isteklo

    #Ako je partija gotova, nema najboljeg poteza i vraćamo evaluaciju pozicije
    if ploca.is_checkmate() or ploca.is_stalemate() or ploca.is_insufficient_material() or ploca.is_repetition(3):
        return evaluacija(ploca), None

    #Ako smo došli do dubine nula, ulazimo u nemirno pretraživanje koje
    #dublje pretražuje poteze koji su uzimanja.
    if dubina == 0:
        if not KORISTI_NEMIRNO:
            return evaluacija_pozicije(ploca, koristi_markovljevu_mobilnost = KORISTI_SDS), None
        return nemirno_pretrazivanje(ploca, igrac_na_redu, vrijeme_pocetka, alfa, beta,
                                        preskoci_provjeru_kraja=True, koristi_markovljevu_mobilnost = KORISTI_SDS)

    #Početne alfa i beta ćemo koristiti kasnije za određivanje tipa unosa za TT
    originalna_alfa = alfa
    originalni_beta = beta

    #Generiramo ključ trenutne pozicije za TT
    kljuc = kljuc_pozicije(ploca)

    #Provjera postoji li trenutna pozicija već u TT-u
    unos = transpozicijska_tablica.get(kljuc)

    #Ako imamo već spremljenu poziciju, vraćamo poznatu vrijednost i najbolji potez
    TT_potez = None
    if unos != None:
        TT_dubina, TT_vrijednost, TT_tip, TT_potez = unos
        #Rezanje se vrši samo ako je spremljena dubina jednaka ili veća od trenutne i ne u korijenu
        if TT_dubina >= dubina and dubina_od_korijena > 0:
            #Egzaktna TT
            if TT_tip == TT_egzaktna:
                broj_TT_pogodaka += 1
                return TT_vrijednost, TT_potez
            #Alfa TT
            elif TT_tip == TT_alfa and TT_vrijednost <= alfa:
                broj_TT_pogodaka += 1
                return TT_vrijednost, TT_potez
            #Beta TT
            elif TT_tip == TT_beta and TT_vrijednost >= beta:
                broj_TT_pogodaka += 1
                return TT_vrijednost, TT_potez

    #Inicijalizacija
    najbolja_vrijednost = float('-inf') if igrac_na_redu else float('inf')
    najbolji_potez = None

    #Sortiramo poteze po prioritetu (pogledaj prioritet_poteza)
    sortirani_potezi = sortiraj_poteze(ploca, TT_potez, najbolji_potez_prosle_iteracije, killer_potezi.get(dubina_od_korijena))

    #U petlji pamtimo poteze i njihove indekse u sortirani_potezi
    for indeks, potez in enumerate(sortirani_potezi):

        #Provjera je li vrijeme pretraživanja isteklo
        if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
            raise vrijeme_isteklo

        #Pamtimo je li potez uzimanje, rokada ili šah
        je_uzimanje = ploca.is_capture(potez)
        je_rokada = potez_je_rokada(ploca, potez)
        je_sah = ploca.is_check()

        #LMR (late move reduction) pliće pretražuje poteze manjeg prioriteta.
        #Broj poteza i minimalnu dubinu postavljamo proizvoljno.
        try:
            #Uvjeti za pliće pretraživanje
            radi_plice_pretrazivanje = (
                KORISTI_SORTIRANJE #IZMJENA 9: LMR ovisi o sortiranju poteza (BezSORT isključuje i LMR)
                and indeks >= BROJ_NAJBOLJIH_POTEZA
                and dubina >= MIN_DUBINA_LMR
                and not je_rokada
                and not je_uzimanje
                and not je_sah
            )

            #Ako je potez manjeg prioriteta, probamo napraviti pliće pretraživanje
            if radi_plice_pretrazivanje:
                smanjena_dubina = max(dubina-1-SMANJENJE_NEBITNIH_POTEZA, 0)
                vrijednost, _ = pretrazivanje(ploca, smanjena_dubina, not igrac_na_redu, vrijeme_pocetka, None, alfa, beta,
                                              dubina_od_korijena+1, 0)
                if (igrac_na_redu and vrijednost > alfa) or (not igrac_na_redu and vrijednost < beta):
                    vrijednost, _ = pretrazivanje(ploca, dubina-1, not igrac_na_redu, vrijeme_pocetka, None, alfa, beta,
                                                  dubina_od_korijena+1, 0)

            else:
                #Produžujemo dubinu kroz šah, ali najviše MAX_SAH_PRODUZETAKA puta
                #zaredom, kako dug niz šahova ne bi potrošio nerazmjeran dio vremena.
                if je_sah and broj_sah_produzetaka < MAX_SAH_PRODUZETAKA:
                    sljedeca_dubina = dubina
                    sljedeci_broj_produzetaka = broj_sah_produzetaka + 1
                else:
                    sljedeca_dubina = dubina - 1
                    sljedeci_broj_produzetaka = 0
                vrijednost, _ = pretrazivanje(ploca, sljedeca_dubina, not igrac_na_redu, vrijeme_pocetka, None, alfa, beta,
                                              dubina_od_korijena+1, sljedeci_broj_produzetaka)
        finally:
            ponisti_potez(ploca, je_rokada)

        #Minimax
        if igrac_na_redu:
            if vrijednost > najbolja_vrijednost:
                najbolja_vrijednost = vrijednost
                najbolji_potez = potez
            if KORISTI_ALFA_BETA:
                alfa = max(alfa, najbolja_vrijednost)
                if alfa >= beta:
                    #Ako je rezanje uzrokovano potezom koji nije uzimanje, pamtimo ga
                    #kao killer potez.
                    if not je_uzimanje and KORISTI_SORTIRANJE:
                        azuriraj_killer_poteze(dubina_od_korijena, potez)
                    break
        else:
            if vrijednost < najbolja_vrijednost:
                najbolja_vrijednost = vrijednost
                najbolji_potez = potez
            if KORISTI_ALFA_BETA:
                beta = min(beta, najbolja_vrijednost)
                if alfa >= beta:
                    if not je_uzimanje and KORISTI_SORTIRANJE:
                        azuriraj_killer_poteze(dubina_od_korijena, potez)
                    break

    #Određujemo tip rezultata za spremanje u TT
    if najbolja_vrijednost <= originalna_alfa:
        TT_tip = TT_alfa
    elif najbolja_vrijednost >= originalni_beta:
        TT_tip = TT_beta
    else:
        TT_tip = TT_egzaktna

    pohrani_TT(kljuc, dubina, najbolja_vrijednost, TT_tip, najbolji_potez)

    return najbolja_vrijednost, najbolji_potez


def vrati_najbolji_potez(ploca: chess.Board) -> chess.Move:

    #Početak mjerenja vremena za pretraživanje
    vrijeme_pocetka = time.time()

    #Prvo probamo s potezom iz otvaranja
    if book != None and ploca.fullmove_number <= MAX_POTEZA_OTVARANJA:
        najbolji_potez = book.odaberi_nasumicni_potez(ploca)
        if najbolji_potez != None and ploca.fullmove_number <= MAX_POTEZA_OTVARANJA:
            return najbolji_potez

    napravio_rokadu[chess.WHITE] = izgleda_rokirano(ploca, chess.WHITE)
    napravio_rokadu[chess.BLACK] = izgleda_rokirano(ploca, chess.BLACK)

    #Ako nema legalnih poteza, vraćamo null potez (partija je gotova)
    legalni_potezi = list(ploca.legal_moves)
    if not legalni_potezi:
        return chess.Move.null()

    #Ako postoji samo jedan legalan potez, vraćamo ga bez pretraživanja
    if len(legalni_potezi) == 1:
        return legalni_potezi[0]

    #Inicijalizacija varijabli za iterativno produbljivanje
    sortirani_potezi = sortiraj_poteze(ploca) #Pretražujemo poteze po prioritetu (pogledaj prioritet_poteza())
    najbolji_potez = sortirani_potezi[0]
    najbolji_potez_prosle_iteracije = None

    #Odvajamo prvu dubinu od ostalih jer pretraživanje rekurzivno smanjuje dubinu
    dubina = 1

    #Za praćenje broja pretraženih čvorova i TT pogodaka
    global broj_vrhova, broj_TT_pogodaka
    broj_vrhova = 0
    broj_TT_pogodaka = 0

    #Brisanje killer poteza prije početka pretraživanja
    killer_potezi.clear()

    #Try except blok pokreće kod ako vrijeme za pretraživanje nije isteklo
    try:

        #Inicijalizacija varijable za najbolju vrijednost prve iteracije
        najbolja_vrijednost_prve_iteracije = float('-inf') if ploca.turn == chess.WHITE else float('inf')

        #Ova for petlja pretražuje poteze u prvoj iteraciji, kasnije je while petlja za dubinu >= 2
        for potez in sortirani_potezi:

            #Provjera je li vrijeme pretraživanja isteklo
            if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
                raise vrijeme_isteklo

            #Pamtimo alfu/betu poteza iz prve dubine
            if not KORISTI_ALFA_BETA:
                alfa = float('-inf')
                beta = float('inf')
            elif ploca.turn == chess.WHITE:
                alfa = najbolja_vrijednost_prve_iteracije
                beta = float('inf')
            else:
                alfa = float('-inf')
                beta = najbolja_vrijednost_prve_iteracije

            #potez_je_rokada igra potez i sprema je li on rokada u je_rokada
            je_rokada = potez_je_rokada(ploca, potez)

            #Na prvoj dubini radimo nemirno pretraživanje jer normalno pretraživanje
            #poziva nemirno kada je dubina nula.
            try:
                if KORISTI_NEMIRNO:
                    vrijednost, _ = nemirno_pretrazivanje(ploca, ploca.turn, vrijeme_pocetka, alfa,
                                                          beta, koristi_markovljevu_mobilnost = KORISTI_SDS)
                else:
                    vrijednost = evaluacija(ploca, KORISTI_SDS)
            finally:
                ponisti_potez(ploca, je_rokada)

            #Ažuriramo najbolju vrijednost prve iteracije i odgovarajući potez
            if ploca.turn == chess.WHITE:
                if vrijednost > najbolja_vrijednost_prve_iteracije:
                    najbolja_vrijednost_prve_iteracije = vrijednost
                    najbolji_potez = potez

            #Analogno za Crnog
            else:
                if vrijednost < najbolja_vrijednost_prve_iteracije:
                    najbolja_vrijednost_prve_iteracije = vrijednost
                    najbolji_potez = potez

        #Pamtimo najbolji potez prve iteracije
        najbolji_potez_prosle_iteracije = najbolji_potez
        print("Završena dubina pretraživanja: 1", file=sys.stderr)

        dubina = 2 #Povećavamo dubinu s 1 na 2

        #Normalno pretraživanje s iterativnim produbljivanjem
        while True:
            vrijednost, potez = pretrazivanje(ploca, dubina, ploca.turn, vrijeme_pocetka, najbolji_potez_prosle_iteracije)

            if potez != None:
                najbolji_potez = potez
                najbolji_potez_prosle_iteracije = potez

            print(f"Završena dubina pretraživanja: {dubina}", file=sys.stderr)

            #Ako potez sigurno vodi šahmatu, ne trebamo dalje pretraživati
            if abs(vrijednost) >= GRANICA_SIGURNOG_SAHMATA:
                break

            dubina += 1

    except vrijeme_isteklo:
        pass

    print(f"Ukupan broj pretraženih vrhova: {broj_vrhova}", file=sys.stderr)
    print(f"TT pogodci: {broj_TT_pogodaka}", file = sys.stderr)

    return najbolji_potez
