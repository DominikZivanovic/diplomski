import chess #Za generiranje legalnih poteza, uzimanja figure itd.
import chess.polyglot
import time
import sys
import math
from Polyglot import PolyglotBook #Za otvaranja; PolyglotBook klasa iz PolyGlot.py
from Figura_polje_tablice import PIJUN_KONTROLA_CENTRA, PIJUN_RANG_BONUS, LOVAC_MOBILNOST, DAMA_MOBILNOST
from Stacionarna_distribucija_skakaca import markovljeva_mobilnost_skakaca, postavi_vrijednosti_figura
from operator import add #Za zbrajanje tablica u evaluaciji figura


#STROJ KORISTI:
#MINIMAX
#ALFA-BETA REZANJE
#ITERATIVNO PRODUBIVANJE
#TRANSPONZIJSKE TABLICE
#KILLER POTEZE (ONE KOJI SU UZROKOVALI ALFA-BETA REZANJE)
#LMR
#NEMIRNO PRETRAŽIVANJE
#KNJIGU OTVARANJA


#GLOBALNE KONSTANTE
OTVARANJA_PATH = "C:/Users/domi1/Desktop/DIPLOMSKI/Otvaranja/Perfect2023.bin"
MAX_POTEZA_OTVARANJA = 8
MAX_NEMIRNA_DUBINA = 6 #Koliko poteza maksimalno pretražujemo u nemirnom pretraživanju
NEMIRNI_POMAK_DUBINE = MAX_NEMIRNA_DUBINA+1 #Za prikaz nemirnih dubina kao negativnih brojeva
BROJ_NAJBOLJIH_POTEZA = 3 #Koliko najboljih poteza iz prethodne iteracije ne smanjujemo LMR-om
SMANJENJE_NEBITNIH_POTEZA = 2 #Koliko dubina smanjujemo u plićem pretraživanju za LMR
MIN_DUBINA_LMR = 2 #Od koje dubine se može provoditi LMR
MAX_SAH_PRODUZETAKA = 3 #Koliko puta produžujemo pretraživanje ako je šah


#ROKADA
ROKADA_BONUS = 70 #Nagrađujemo rokadu
PIJUN_PRED_KRALJEM_BONUS = 30 #Nagrađujemo netaknute pijune pred rokiranim kraljem
IZGUBLJENA_ROKADA_KAZNA = 40 #Kažnjavamo izgubljena prava na rokadu

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


#UPRAVLJANJE VREMENOM
MAX_VRIJEME_PRETRAZIVANJA = 4 #U sekundama
class vrijeme_isteklo(Exception):
    pass


#BROJANJE VRHOVA
broj_vrhova = 0 #Za brojanje pretraženih vrhova tijekom pretraživanja


#KILLER POTEZI
killer_potezi = {} #Rječnik za spremanje dubine i liste killer poteza


#KNJIGA OTVARANJA
book = PolyglotBook(OTVARANJA_PATH)
book.__enter__()


#PREOSTALI MATERIJAL (za sigurnost kralja)
DOPRINOS_KRAJU_PARTIJE = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9} #Proizvoljno
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
    #Poziva se prije svake nove partije (za resetiranje rokade)
    global broj_vrhova
    killer_potezi.clear()
    napravio_rokadu[chess.WHITE] = False
    napravio_rokadu[chess.BLACK] = False
    broj_vrhova = 0



#####################################################################################################
####################################### VRIJEDNOST FIGURA ###########################################
#####################################################################################################

pocetne_vrijednosti_figura = {
    chess.PAWN: 100,
    chess.KNIGHT: 310,
    chess.BISHOP: 320,
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
MOBILNOST_SKAKACA_TEZINA = 0.15


#LOVCI (alfa*mobilnost + beta*dobar_lovac + gama*par_lovaca)
ALFA_LOVAC = 5 #Mobilnost
BETA_LOVAC = 15 #Dobar lovac
GAMA_LOVAC = 20 #Bonus pojedinačnom lovcu za par lovaca

#Funkcija računa broj pijuna na istoj boji kao i lovac
def dobar_lovac(polje: chess.Square, vlastiti_pijuni) -> int:
    boja_polja_lovca = (chess.square_rank(polje) + chess.square_file(polje)) % 2 #0 za bijelo polje, 1 za crno polje
    broj_pijuna_na_istoj_boji = 0
    for polje2 in vlastiti_pijuni:
        if (chess.square_rank(polje2) + chess.square_file(polje2)) % 2 == boja_polja_lovca:
            broj_pijuna_na_istoj_boji += 1

    return -broj_pijuna_na_istoj_boji

#Funkcija provjerava jesu li na ploči oba lovca
def par_lovaca(ploca: chess.Board, boja: chess.Color) -> bool:
    return len(ploca.pieces(chess.BISHOP, boja)) >= 2


#TOPOVI
TOP_OTVORENI_STUPAC_BONUS = 40
TOP_POLUOTVORENI_STUPAC_BONUS = 20
TOP_SEDMI_RED_BONUS = 30
POVEZANI_TOPOVI_BONUS = 20

#Funkcija pamti sve stupce u kojima ima pijuna
def stupci_s_pijunima(pijuni) -> set:
    return {chess.square_file(p) for p in pijuni}

#Funkcija prebrojava broj pijuna u stupcu u kojem se top nalazi
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
AKTIVNOST_KRALJA = 15

#Funkcija kvantificira sigurnost kralja
def sigurnost_kralja(ploca: chess.Board, boja: chess.Color) -> float:

    #Inicijalizacija
    bonus = 0
    vlastiti_pijuni = ploca.pawns & ploca.occupied_co[boja]

    #Ako je bijeli rokirao, nagrađujemo napravljenu rokadu i netaknute pijune pred kraljem
    #ovisno o tome je li rokada bila duga ili kratka.
    if napravio_rokadu[boja]:
        bonus += ROKADA_BONUS
        kraljevo_polje = ploca.king(boja)

        #Bijeli
        if boja == chess.WHITE:
            #Bonus za kratku rokadu bijelog kralja
            if kraljevo_polje == chess.G1:
                pijuni_pred_kraljem = chess.BB_SQUARES[chess.F2] | chess.BB_SQUARES[chess.G2] | chess.BB_SQUARES[chess.H2]
                bonus += PIJUN_PRED_KRALJEM_BONUS * chess.popcount(vlastiti_pijuni & pijuni_pred_kraljem)
            #Bonus za dugu rokadu bijelog kralja
            elif kraljevo_polje == chess.C1:
                pijuni_pred_kraljem = chess.BB_SQUARES[chess.A2] | chess.BB_SQUARES[chess.B2] | chess.BB_SQUARES[chess.C2]
                bonus += PIJUN_PRED_KRALJEM_BONUS * chess.popcount(vlastiti_pijuni & pijuni_pred_kraljem)

        #Crni
        else:
            if kraljevo_polje == chess.G8:
                pijuni_pred_kraljem = chess.BB_SQUARES[chess.F7] | chess.BB_SQUARES[chess.G7] | chess.BB_SQUARES[chess.H7]
                bonus += PIJUN_PRED_KRALJEM_BONUS * chess.popcount(vlastiti_pijuni & pijuni_pred_kraljem)
            elif kraljevo_polje == chess.C8:
                pijuni_pred_kraljem = chess.BB_SQUARES[chess.A7] | chess.BB_SQUARES[chess.B7] | chess.BB_SQUARES[chess.C7]
                bonus += PIJUN_PRED_KRALJEM_BONUS * chess.popcount(vlastiti_pijuni & pijuni_pred_kraljem)

    #Ako je bijeli izgubio prava na rokadu, kažnjavamo ga
    elif not ploca.has_castling_rights(boja):
        bonus -= IZGUBLJENA_ROKADA_KAZNA

    return bonus

def udaljenost_od_centra(polje: chess.Square) -> float:
    return math.floor(max(abs(3.5 - chess.square_file(polje)), abs(3.5 - chess.square_rank(polje)))) #0 za centar, 3.5 za rub ploče

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

    stupci_s_bijelim_pijunima = stupci_s_pijunima(bijeli_pijuni)
    stupci_s_crnim_pijunima = stupci_s_pijunima(crni_pijuni)

    ukupni_bonus = 0
    for polje, figura in mapa_figura.items():

        if figura.piece_type == chess.PAWN: #Bonusi su pod #PIJUNI
            bonus = bonus_pijuna[zrcaljenje_ploce(polje, figura.color)]

        elif figura.piece_type == chess.KNIGHT: #Bonusi su pod #SKAKAČI
            if koristi_markovljevu_mobilnost:
                bonus = MOBILNOST_SKAKACA_TEZINA * markovljeva_mobilnost_skakaca(ploca, polje, figura.color)
            else:
                bonus = 0

        elif figura.piece_type == chess.BISHOP: #Bonusi su pod #LOVCI
            vlastiti_pijuni = bijeli_pijuni if figura.color == chess.WHITE else crni_pijuni
            bonus = ALFA_LOVAC * LOVAC_MOBILNOST[polje] + BETA_LOVAC * dobar_lovac(polje, vlastiti_pijuni) + GAMA_LOVAC

        elif figura.piece_type == chess.ROOK: #Bonusi su pod #TOPOVI
            stupci_s_vlastitim_pijunima = stupci_s_bijelim_pijunima if figura.color == chess.WHITE else stupci_s_crnim_pijunima
            stupci_s_protivnickim_pijunima = stupci_s_crnim_pijunima if figura.color == chess.WHITE else stupci_s_bijelim_pijunima
            bonus = ocijeni_topov_stupac(polje, stupci_s_vlastitim_pijunima, stupci_s_protivnickim_pijunima)
            if top_na_sedmom_redu(ploca, polje, figura.color):
                bonus += TOP_SEDMI_RED_BONUS

        elif figura.piece_type == chess.QUEEN: #Bonusi su pod #KRALJICA
            bonus = ALFA_KRALJICA * DAMA_MOBILNOST[polje]

        else: #Bonusi su pod #KRALJ
            bonus = (sigurnost_kralja(ploca, figura.color) * udaljenost_od_kraja + aktivnost_kralja(ploca, figura.color) * (1-udaljenost_od_kraja))

        if figura.color == chess.WHITE:
            ukupni_bonus += bonus
        else:
            ukupni_bonus -= bonus

    return ukupni_bonus




#Funkcija zbraja sve komponente koje ulaze u evaluaciju neke pozicije
def evaluacija_pozicije(ploca: chess.Board, koristi_markovljevu_mobilnost: bool = True) -> float:
    mapa_figura = ploca.piece_map()
    bijeli_pijuni = ploca.pieces(chess.PAWN, chess.WHITE)
    crni_pijuni = ploca.pieces(chess.PAWN, chess.BLACK)
    udaljenost_od_kraja = udaljenost_od_kraja_partije(mapa_figura)

    prednost = materijal(mapa_figura)
    prednost += pst(ploca, mapa_figura, bijeli_pijuni, crni_pijuni, udaljenost_od_kraja, koristi_markovljevu_mobilnost)

    return prednost


def evaluacija(ploca: chess.Board, koristi_markovljevu_mobilnost: bool = True) -> float:

    #Provjera je li na ploči šahmat ili pat/neriješeno
    if ploca.is_checkmate():
        return -1_000_000 if ploca.turn == chess.WHITE else 1_000_000
    if ploca.is_stalemate() or ploca.is_insufficient_material() or ploca.is_repetition(2):
        return 0

    #Ako igra nije gotova, vraćamo evaluaciju pozicije
    return evaluacija_pozicije(ploca, koristi_markovljevu_mobilnost)



########################################################################################################
########################################## PRETRAŽIVANJE ###############################################
########################################################################################################

#Funkcija određuje kojim redom pretražiti poteze u novoj iteraciji:
#najbolji potez iz prošle iteracije, uzimanja itd.
def prioritet_poteza(ploca: chess.Board, potez: chess.Move,
                     najbolji_potez_prosle_iteracije: chess.Move | None = None,
                     killer_potezi_na_dubini: list | None = None) -> int:

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
def sortiraj_poteze(ploca: chess.Board, najbolji_potez_prosle_iteracije: chess.Move | None = None,
                    killer_potezi_na_dubini: list | None = None) -> list[chess.Move]:
    potezi = list(ploca.legal_moves)
    potezi.sort(key=lambda potez: prioritet_poteza(ploca, potez, najbolji_potez_prosle_iteracije, killer_potezi_na_dubini), reverse=True)
    return potezi

#Funkcija ažurira killer_potezi
def azuriraj_killer_poteze(dubina: int, potez: chess.Move) -> None:

    #Ako ne postoji ključ dubina u killer_potezi, stvaramo ga i za vrijednost
    #stavljamo praznu listu.
    lista = killer_potezi.setdefault(dubina, [])

    #Ako je potez već u listi, izlazimo iz funkcije
    if potez in lista:
        return

    #FIFO princip, max. duljina liste je proizvoljna (ovdje je 3)
    #Listu ograničujemo jer relevantnost starijih poteza pada pa je poziv u
    #prioritet_poteza vremenski jeftiniji.
    lista.insert(0, potez)
    if len(lista) > 3:
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
                          nemirna_dubina = 0,
                          MAX_NEMIRNA_DUBINA = 8) -> tuple[float, chess.Move | None]:

    #Za brojanje pretraženih vrhova
    global broj_vrhova
    broj_vrhova += 1

    #Provjera je li vrijeme pretraživanja isteklo
    if time.time() - vrijeme_pocetka >= MAX_VRIJEME_PRETRAZIVANJA:
        raise vrijeme_isteklo

    #Ako je partija gotova, nema najboljeg poteza i vraćamo evaluaciju pozicije
    if not preskoci_provjeru_kraja and (ploca.is_checkmate() or ploca.is_stalemate() or ploca.is_insufficient_material()
                                        or ploca.is_repetition(3)):
        return evaluacija(ploca), None

    trenutna_vrijednost = evaluacija_pozicije(ploca, koristi_markovljevu_mobilnost = koristi_markovljevu_mobilnost)

    #Ako smo prešli maksimalnu dubinu nemirnog pretraživanja
    if nemirna_dubina >= MAX_NEMIRNA_DUBINA:
        return trenutna_vrijednost, None

    if igrac_na_redu:
        if trenutna_vrijednost >= beta:
            return trenutna_vrijednost, None
        alfa = max(alfa, trenutna_vrijednost)
    else:
        if trenutna_vrijednost <= alfa:
            return trenutna_vrijednost, None
        beta = min(beta, trenutna_vrijednost)

    najbolji_potez = None

    #Dodajemo tihe promocije kako bi nemirno pretraživanje i njih uzelo u obzir
    takticki_potezi = list(ploca.generate_legal_captures())
    if ploca.pawns & SEDMI_RANG:
        for potez in ploca.legal_moves:
            if potez.promotion != None and not ploca.is_capture(potez):
                takticki_potezi.append(potez)

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


def pretrazivanje(ploca: chess.Board, dubina: int, igrac_na_redu: bool, vrijeme_pocetka: float,
                  najbolji_potez_prosle_iteracije: chess.Move | None = None,
                  alfa: float = float('-inf'), beta: float = float('inf'),
                  dubina_od_korijena: int = 0, broj_sah_produzetaka: int = 0) -> tuple[float, chess.Move | None]:

    #Za brojanje pretraženih vrhova
    global broj_vrhova
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
        return nemirno_pretrazivanje(ploca, igrac_na_redu, vrijeme_pocetka, alfa, beta,
                                        preskoci_provjeru_kraja=True, koristi_markovljevu_mobilnost = True)

    #Inicijalizacija
    najbolja_vrijednost = float('-inf') if igrac_na_redu else float('inf')
    najbolji_potez = None

    #Sortiramo poteze po prioritetu (pogledaj prioritet_poteza)
    sortirani_potezi = sortiraj_poteze(ploca, najbolji_potez_prosle_iteracije, killer_potezi.get(dubina_od_korijena))

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
                indeks >= BROJ_NAJBOLJIH_POTEZA
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
            alfa = max(alfa, najbolja_vrijednost)
            if alfa >= beta:
                #Ako je rezanje uzrokovano potezom koji nije uzimanje, pamtimo ga
                #kao killer potez.
                if not je_uzimanje:
                    azuriraj_killer_poteze(dubina_od_korijena, potez)
                break
        else:
            if vrijednost < najbolja_vrijednost:
                najbolja_vrijednost = vrijednost
                najbolji_potez = potez
            beta = min(beta, najbolja_vrijednost)
            if alfa >= beta:
                if not je_uzimanje:
                    azuriraj_killer_poteze(dubina_od_korijena, potez)
                break

    return najbolja_vrijednost, najbolji_potez


def vrati_najbolji_potez(ploca: chess.Board) -> chess.Move:

 #Početak mjerenja vremena za pretraživanje
    vrijeme_pocetka = time.time()

    #Prvo probamo s potezom iz otvaranja
    if ploca.fullmove_number <= MAX_POTEZA_OTVARANJA:
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

    #Za praćenje broja pretraženih čvorova
    global broj_vrhova
    broj_vrhova = 0

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

            #Pamtimo alfa/beta poteza iz prve dubine
            if ploca.turn == chess.WHITE:
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
                vrijednost, _ = nemirno_pretrazivanje(ploca, ploca.turn, vrijeme_pocetka, alfa,
                                                      beta, koristi_markovljevu_mobilnost = True)
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
        GRANICA_SIGURNOG_SAHMATA = 500_000 #Proizvoljna granica za detekciju šahmata

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

    return najbolji_potez