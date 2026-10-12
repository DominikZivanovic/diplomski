import chess
import chess.polyglot #Za generiranje ključa pozicije
from collections import deque
import numpy as np #Za rješavanje lin. sustava za stac. distr.


def postavi_vrijednosti_figura(vrijednosti: dict) -> None:
    global pocetne_vrijednosti_figura
    pocetne_vrijednosti_figura = vrijednosti


#TOPOLOGIJA SKAKAČEVIH POTEZA
#chess.BB_KNIGHT_ATTACKS je tablica koju Python-chess koristi za generiranje
#skakačevih poteza pa ju koristimo umjesto da ručno računamo pomake
SKAKAC_SUSJEDNA_POLJA = [list(chess.SquareSet(chess.BB_KNIGHT_ATTACKS[polje])) for polje in chess.SQUARES]

#Funkcija vraća riječnik s udaljenostima od polja_skakaca do svih polja koja su udaljena najviše 3 poteza skakača.
#Potrebna je za određivanje nagrada u ergodskom teoremu.
def polja_udaljenosti_do_3(polje_skakaca: chess.Square) -> dict:

    udaljenosti = {polje_skakaca: 0}
    red = deque([polje_skakaca])

    while red:
        trenutno = red.popleft()
        if udaljenosti[trenutno] == 3:
            continue
        for susjedno_polje in SKAKAC_SUSJEDNA_POLJA[trenutno]:
            if susjedno_polje not in udaljenosti:
                udaljenosti[susjedno_polje] = udaljenosti[trenutno] + 1
                red.append(susjedno_polje)

    return udaljenosti


#PROSTOR STANJA
#Prostor stanja konstruiramo koristeći samo polja koja skakač može dostići i koja zadovoljavaju uvjete: polje nije okupirano vlastitom figurom,
#polje nije kontrolirano protivničkom figurom manje vrijednosti i polje ne kontrolira više protivničkih figura od obrambenih.
#Ovakva konstrukcija garantira ireducibilnost jer se skakač iz svakog polja može vratiti u prethodno.

#Funkcija uzima polje i provjerava može li ga skakač dostići bez da bude u opasnosti
def provjeri_uvjete_prostora_stanja(ploca: chess.Board, polje: chess.Square, boja_igraca: chess.Color, vrijednost_skakaca: int) -> bool:

    #Provjera je li polje zauzeto vlastitom figurom
    figura = ploca.piece_at(polje)
    if figura != None and figura.color == boja_igraca:
        return False

    #Provjera napada li polje figura slabija od skakača
    boja_protivnika = not boja_igraca
    napadacka_polja_protivnika = ploca.attackers(boja_protivnika, polje)
    for napadacko_polje in napadacka_polja_protivnika:
        napadacka_figura = ploca.piece_at(napadacko_polje)
        if napadacka_figura != None and pocetne_vrijednosti_figura[napadacka_figura.piece_type] < vrijednost_skakaca:
            return False

    #Provjera napada li polje više protivničkih figura, nego što ga brani vlastitih figura
    #NAPOMENA: Iako bi bilo praktičnije uzeti u obzir tzv. X-ray napadače (npr. lovac i kraljica na istoj dijagonali) to je iznimno
    #skup račun u smislu vremena pa koristimo samo direktne napadače
    '''
    broj_napadaca = [0, 0] #Prvi broj je broj braniča, a drugi broj napadača
    i = 0 #Indeks za broj_napadaca
    for boja in [boja_igraca, boja_protivnika]:
        napadacka_polja = napadacka_polja_protivnika if boja == boja_protivnika else ploca.attackers(boja, polje) #Vraća polja s kojih branič/napadač direktno brani/napada dano polje
        broj_napadaca[i] = len(napadacka_polja)
        broj_Xray_napadaca = 0 #Broj figura koje brane/napadaju polje kroz druge braniče/napadače (npr. lovac i kraljica na istoj dijagonali)

        for napadacko_polje in napadacka_polja:
            napadacka_figura = ploca.piece_at(napadacko_polje)
            if napadacka_figura == None:
                continue
            vrijednost_napadaca = pocetne_vrijednosti_figura[napadacka_figura.piece_type]
            if i == 1 and vrijednost_napadaca < vrijednost_skakaca:
                return False
            #.pieces_mask omogućuje maskiranje figura na ploči kako bi se prepoznali X-ray napadači
            broj_Xray_napadaca += len(ploca.attackers(boja, polje, ploca.pieces_mask(napadacka_figura.piece_type, napadacka_figura.color)))
            
        broj_napadaca[i] += broj_Xray_napadaca
        i = 1
    '''

    broj_branica = len(ploca.attackers(boja_igraca, polje))
    broj_napadaca = len(napadacka_polja_protivnika)

    if broj_branica < broj_napadaca:
        return False
    
    return True

#Funkcija vraća listu s poljima koja skakač može doseći bez da bude u opasnosti
def odredi_skup_stanja(ploca: chess.Board, polje_skakaca: chess.Square, boja: chess.Color) -> list:

    vrijednost_skakaca = pocetne_vrijednosti_figura[chess.KNIGHT]
    posjeceno = set()
    red = deque()

    for susjed in SKAKAC_SUSJEDNA_POLJA[polje_skakaca]:
        if susjed not in posjeceno and provjeri_uvjete_prostora_stanja(ploca, susjed, boja, vrijednost_skakaca):
            posjeceno.add(susjed)
            red.append(susjed)

    while red:
        trenutno = red.popleft()
        for susjed in SKAKAC_SUSJEDNA_POLJA[trenutno]:
            if susjed not in posjeceno and provjeri_uvjete_prostora_stanja(ploca, susjed, boja, vrijednost_skakaca):
                posjeceno.add(susjed)
                red.append(susjed)

    return list(posjeceno)


#Rješavamo sustav pi * P = pi, sum(pi) = 1
def stacionarna_distribucija(polje_skakaca: chess.Square, stanja: list) -> dict:

    sva_stanja = [polje_skakaca] + stanja
    n = len(sva_stanja)
    if n == 0:
        return {}
    #Slučaj kada je skakač zarobljen (susjedna polja su nedostupna)
    if n == 1:
        return {stanja[0]: 1.0}

    skup_stanja = set(sva_stanja)
    indeks = {polje: i for i, polje in enumerate(sva_stanja)}

    susjedi_u_skupu_stanja = [
        [s for s in SKAKAC_SUSJEDNA_POLJA[polje] if s in skup_stanja]
        for polje in sva_stanja
    ]

    #Sustav (P^T - I)*pi = 0, uz zamjenu zadnjeg retka uvjetom normalizacije suma(pi) = 1
    A = np.zeros((n, n))
    for i in range(n):
        stupanj = len(susjedi_u_skupu_stanja[i])
        for susjedno_polje in susjedi_u_skupu_stanja[i]:
            j = indeks[susjedno_polje]
            #Uniformne vjerojatnosti prijelaza: P[i][j] = 1/stupanj
            A[j][i] += 1.0 / stupanj
        A[i][i] -= 1.0

    b = np.zeros(n)
    A[n-1] = 1.0
    b[n-1] = 1.0

    pi = np.linalg.solve(A, b)
    return dict(zip(stanja, pi))


#NAGRADE I KONAČNA OCJENA
UDALJENOST_TEZINE = {1:1.0, 2:2/3, 3:1/3}

#Bazna nagrada za bezopasno, dostupno polje, neovisno o tome nalazi li se na njemu protivnička figura
MOBILNOST_BAZA = 20

#Umjerena nagrada za polje na kojem se nalazi protivnički kralj (šah).
#Namjerno ne koristi punu vrijednost kralja jer je ona postavljena samo
#za uočavanje šah-mata. 
NAGRADA_ZA_SAH = 60


def nagrada_polja(ploca: chess.Board, polje: chess.Square, boja: chess.Color, udaljenost) -> float:

    if udaljenost is None or udaljenost not in UDALJENOST_TEZINE:
        return 0

    tezina = UDALJENOST_TEZINE[udaljenost]
    figura = ploca.piece_at(polje)

    if figura is None:
        return MOBILNOST_BAZA * tezina
    if figura.piece_type == chess.KING:
        return (MOBILNOST_BAZA + NAGRADA_ZA_SAH) * tezina

    return (MOBILNOST_BAZA + pocetne_vrijednosti_figura[figura.piece_type]) * tezina


mobilnost_cache = {} #Ovdje spremamo već izračunate mobilnosti

def markovljeva_mobilnost_skakaca(ploca: chess.Board, polje_skakaca: chess.Square, boja: chess.Color) -> float:

    kljuc = (chess.polyglot.zobrist_hash(ploca), polje_skakaca, boja)
    if kljuc in mobilnost_cache:
        return mobilnost_cache[kljuc]

    stanja = odredi_skup_stanja(ploca, polje_skakaca, boja)
    if not stanja:
        mobilnost_cache[kljuc] = 0
        return 0

    distribucija = stacionarna_distribucija(polje_skakaca, stanja)
    udaljenosti = polja_udaljenosti_do_3(polje_skakaca)

    bonus = 0
    for polje in stanja:
        nagrada = nagrada_polja(ploca, polje, boja, udaljenosti.get(polje))
        if nagrada:
            bonus += distribucija[polje] * nagrada

    mobilnost_cache[kljuc] = bonus
    return bonus